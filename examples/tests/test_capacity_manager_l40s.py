"""Offline L40S candidate gates and architecture/ownership contract checks."""
import hashlib
import pathlib
import subprocess
import unittest

import yaml

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'examples/values/capacity-manager-devnet-aws-l40s.yaml'
REFERENCE = ROOT / 'examples/values/capacity-manager-devnet-rtx3090.yaml'
WORKER_IMAGE = ('dogeos69/prover-worker-cuda@sha256:'
                '5f170b2150877b66ce8c3daa1c467d8ac60947c1f229f913cab1247e79efb2b9')


def render(prepared=False, regions=None):
    args = ['helm', 'template', 'devnet-capacity-manager-active',
            str(ROOT / 'charts/capacity-manager'), '--namespace', 'dstack-system',
            '-f', str(PROFILE)]
    if prepared:
        args.extend(['--set', 'prepared=true'])
    if regions is not None:
        for index, region in enumerate(regions):
            args.extend(['--set', f'manager.dstack.regions[{index}]={region}'])
    return subprocess.run(args, capture_output=True, text=True)


class CapacityManagerL40sTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = yaml.safe_load(PROFILE.read_text())
        cls.reference = yaml.safe_load(REFERENCE.read_text())
        result = render(prepared=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        cls.deployment = next(d for d in cls.docs if d['kind'] == 'Deployment')
        cls.pod = cls.deployment['spec']['template']['spec']
        cls.container = cls.pod['containers'][0]
        cls.args = cls.container['args']

    def test_candidate_requires_explicit_preparation_before_install(self):
        self.assertFalse(self.values['prepared'])
        result = render()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('prepare before installing', result.stderr)

    def test_same_owner_state_auth_without_provider_credentials(self):
        for key in ('fullnameOverride', 'serviceAccount', 'persistence', 'wpAuth', 'dstackAuth'):
            self.assertEqual(self.values[key], self.reference[key])
        self.assertEqual(self.values['manager']['workerIdPrefix'],
                         self.reference['manager']['workerIdPrefix'])
        self.assertEqual(self.deployment['spec']['replicas'], 1)
        self.assertEqual(self.deployment['spec']['strategy']['type'], 'Recreate')
        self.assertFalse(self.pod['automountServiceAccountToken'])
        self.assertEqual(self.pod['terminationGracePeriodSeconds'], 1800)
        self.assertFalse(any(d['kind'] in (
            'Secret', 'ServiceAccount', 'PersistentVolumeClaim', 'Role', 'RoleBinding',
            'ClusterRole', 'ClusterRoleBinding', 'Service', 'Ingress',
        ) for d in self.docs))
        env = {v['name']: v for v in self.container['env']}
        self.assertEqual(set(env), {'RUST_LOG', 'DOGEOS_PROOF_WORK_BEARER_TOKEN'})
        self.assertEqual(env['DOGEOS_PROOF_WORK_BEARER_TOKEN']['valueFrom']['secretKeyRef'],
                         {'name': 'devnet-capacity-manager-active-wp-token', 'key': 'proof-work-token'})
        self.assertIn('DOGEOS_PROVER_WORKER_TOKEN=${{ secrets.cm_active_worker_token_1013 }}',
                      self.args)

    def test_single_aws_l40s_with_explicit_price_and_unrestricted_run_regions(self):
        policy = tomllib.loads(self.values['manager']['policy'])
        self.assertEqual(policy['global']['max_workers'], 1)
        self.assertEqual(policy['pool']['provider'], 'aws')
        self.assertEqual(policy['pool']['gpu_class'], 'L40S')
        self.assertEqual(policy['pool']['vram_gib'], 44)
        self.assertEqual(policy['pool']['max_workers'], 1)
        self.assertEqual(policy['pool']['max_hourly_cost_usd'], 3.1)
        self.assertEqual(policy['pool']['hourly_cost_usd_per_worker'], 3.1)
        self.assertEqual(set(policy['families']), {
            'scroll_chunk', 'scroll_batch', 'l2_range_aggregation', 'bridge_state',
        })
        for family in policy['families'].values():
            self.assertLessEqual(family['max_workers'], 1)
            self.assertEqual(family['min_vram_gib'], 16)
        for flag, value in {
            '--dstack-project': 'devnet-provers-aws',
            '--dstack-fleet': 'devnet-capacity-manager-active-aws-l40s',
            '--dstack-instance-type': 'g6e.4xlarge',
            '--dstack-max-price-usd': '3.1',
        }.items():
            self.assertEqual(self.args.count(flag), 1)
            self.assertEqual(self.args[self.args.index(flag) + 1], value)

    def test_region_filter_is_optional_and_can_be_explicitly_overridden(self):
        self.assertEqual(self.values['manager']['dstack']['regions'], [])
        self.assertNotIn('--dstack-region', self.args)
        result = render(prepared=True, regions=['eu-central-1', 'eu-north-1'])
        self.assertEqual(result.returncode, 0, result.stderr)
        deployment = next(d for d in yaml.safe_load_all(result.stdout)
                          if d and d['kind'] == 'Deployment')
        args = deployment['spec']['template']['spec']['containers'][0]['args']
        selected = [args[index + 1] for index, flag in enumerate(args)
                    if flag == '--dstack-region']
        self.assertEqual(selected, ['eu-central-1', 'eu-north-1'])
        # Restricting regions must not alter the qualified worker or budget.
        for flag in ('--dstack-worker-image', '--dstack-worker-command',
                     '--dstack-max-price-usd', '--dstack-fleet'):
            self.assertEqual(args[args.index(flag) + 1],
                             self.args[self.args.index(flag) + 1])

    def test_truthful_89_image_preserves_all_other_crypto_execution_arguments(self):
        self.assertEqual(self.values['image'], self.reference['image'])
        self.assertEqual(self.values['manager']['workerImage'], WORKER_IMAGE)
        self.assertEqual(self.args[self.args.index('--dstack-worker-image') + 1], WORKER_IMAGE)
        expected = self.reference['manager']['workerCommand'].replace("= '86';", "= '89';", 1)
        command = self.args[self.args.index('--dstack-worker-command') + 1]
        self.assertEqual(command, expected)
        self.assertEqual(hashlib.sha256(command.encode()).hexdigest(),
                         '8e4fd7192a23915c62eaef8e8e7438ed9b0fc568678d7c4019fecbeec78d0f97')
        self.assertIn('--scale-down-on-shutdown', self.args)
        self.assertFalse(any(arg.startswith('DOGEOS_CUDA_ARCHS=') for arg in self.args))


if __name__ == '__main__':
    unittest.main()
