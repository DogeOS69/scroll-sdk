"""Offline AWS-primary profile checks; manual fallback, never provision resources."""
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
PROFILE = ROOT / 'examples/values/capacity-manager-devnet-aws-a10g.yaml'
RTX_PROFILE = ROOT / 'examples/values/capacity-manager-devnet-rtx3090.yaml'


class CapacityManagerAwsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = yaml.safe_load(PROFILE.read_text())
        cls.rtx = yaml.safe_load(RTX_PROFILE.read_text())
        result = subprocess.run([
            'helm', 'template', 'devnet-capacity-manager-active',
            str(ROOT / 'charts/capacity-manager'), '--namespace', 'dstack-system',
            '-f', str(PROFILE),
        ], capture_output=True, text=True, check=True)
        cls.docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        cls.deployment = next(d for d in cls.docs if d['kind'] == 'Deployment')
        cls.pod = cls.deployment['spec']['template']['spec']
        cls.container = cls.pod['containers'][0]
        cls.args = cls.container['args']

    def test_primary_and_fallback_reuse_one_allocator_identity_and_external_state(self):
        self.assertEqual(self.deployment['metadata']['name'], self.rtx['fullnameOverride'])
        self.assertEqual(self.deployment['spec']['replicas'], 1)
        self.assertEqual(self.deployment['spec']['strategy']['type'], 'Recreate')
        self.assertEqual(self.values['manager']['workerIdPrefix'],
                         self.rtx['manager']['workerIdPrefix'])
        self.assertEqual(self.values['serviceAccount'], self.rtx['serviceAccount'])
        self.assertEqual(self.values['persistence'], self.rtx['persistence'])
        self.assertEqual(self.pod['serviceAccountName'], 'devnet-capacity-manager-active')
        self.assertFalse(self.pod['automountServiceAccountToken'])
        self.assertFalse(any(d['kind'] in (
            'Secret', 'ServiceAccount', 'PersistentVolumeClaim', 'Service', 'Ingress',
            'Role', 'RoleBinding', 'ClusterRole', 'ClusterRoleBinding',
        ) for d in self.docs))

    def test_provider_and_paid_gpu_limits_are_explicit(self):
        policy = tomllib.loads(self.values['manager']['policy'])
        self.assertEqual(policy['global']['max_workers'], 1)
        self.assertEqual(policy['pool']['provider'], 'aws')
        self.assertEqual(policy['pool']['gpu_class'], 'A10G')
        self.assertEqual(policy['pool']['vram_gib'], 22)
        self.assertEqual(policy['pool']['max_workers'], 1)
        self.assertEqual(policy['pool']['hourly_cost_usd_per_worker'], 1.75)
        self.assertEqual(policy['pool']['max_hourly_cost_usd'], 1.75)
        for family in policy['families'].values():
            self.assertLessEqual(family['max_workers'], 1)
            self.assertEqual(family['min_vram_gib'], 16)
        self.assertEqual(set(policy['families']), {
            'scroll_chunk', 'scroll_batch', 'l2_range_aggregation', 'bridge_state',
        })
        # One provider/project/fleet is selected; fallback is an operator handoff.
        self.assertEqual(self.values['manager']['dstack']['fleets'],
                         ['devnet-capacity-manager-active-aws-a10g'])
        for flag, value in {
            '--dstack-project': 'devnet-provers-aws',
            '--dstack-fleet': 'devnet-capacity-manager-active-aws-a10g',
            '--dstack-region': 'us-east-1',
            '--dstack-instance-type': 'g5.4xlarge',
            '--dstack-max-price-usd': '1.75',
        }.items():
            self.assertEqual(self.args.count(flag), 1)
            self.assertEqual(self.args[self.args.index(flag) + 1], value)

    def test_crypto_and_execution_contract_are_preserved(self):
        self.assertEqual(self.values['image'], self.rtx['image'])
        for key in ('workerImage', 'workerCommand', 'workerReadinessFile'):
            self.assertEqual(self.values['manager'][key], self.rtx['manager'][key])
        command = self.args[self.args.index('--dstack-worker-command') + 1]
        self.assertEqual(hashlib.sha256(command.encode()).hexdigest(),
                         '81b537df1660ac50e4d64142b63f9b99afd537b1a906b7589e00873d4cfbbec0')
        self.assertIn('--scale-down-on-shutdown', self.args)
        self.assertEqual(self.pod['terminationGracePeriodSeconds'], 1800)

    def test_credentials_remain_references_without_provider_or_api_credentials(self):
        self.assertEqual(self.values['wpAuth'], self.rtx['wpAuth'])
        self.assertEqual(self.values['dstackAuth'], self.rtx['dstackAuth'])
        self.assertIn('DOGEOS_PROVER_WORKER_TOKEN=${{ secrets.cm_active_worker_token_1013 }}',
                      self.args)
        env = {v['name']: v for v in self.container['env']}
        self.assertEqual(set(env), {'RUST_LOG', 'DOGEOS_PROOF_WORK_BEARER_TOKEN'})
        self.assertEqual(env['DOGEOS_PROOF_WORK_BEARER_TOKEN']['valueFrom']['secretKeyRef'],
                         {'name': 'devnet-capacity-manager-active-wp-token',
                          'key': 'proof-work-token'})
        self.assertFalse(any('projected' in v or 'hostPath' in v for v in self.pod['volumes']))
        volume = next(v for v in self.pod['volumes'] if v['name'] == 'dstack-token')
        self.assertEqual(volume['secret']['secretName'], 'dstack-controller-auth')
        self.assertEqual(volume['secret']['items'], [{'key': 'admin-token', 'path': 'token'}])


if __name__ == '__main__':
    unittest.main()
