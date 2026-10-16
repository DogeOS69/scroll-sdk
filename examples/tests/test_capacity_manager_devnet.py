"""Offline checks for the qualified DevNet contract and Helm handoff boundaries."""
import hashlib
import pathlib
import subprocess
import tempfile
import unittest
import yaml

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'examples/values/capacity-manager-devnet-rtx3090.yaml'


def render(values, chart='capacity-manager'):
    with tempfile.TemporaryDirectory() as directory:
        file = pathlib.Path(directory) / 'values.yaml'
        file.write_text(yaml.safe_dump(values))
        result = subprocess.run([
            'helm', 'template', 'devnet-capacity-manager-active',
            str(ROOT / 'charts' / chart), '--namespace', 'dstack-system',
            '-f', str(file),
        ], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return [d for d in yaml.safe_load_all(result.stdout) if d]


class DevNetCapacityManagerTests(unittest.TestCase):
    def setUp(self):
        self.values = yaml.safe_load(PROFILE.read_text())

    def test_external_state_account_and_credentials_are_preserved(self):
        docs = render(self.values)
        self.assertFalse(any(d['kind'] in (
            'Secret', 'ServiceAccount', 'PersistentVolumeClaim', 'Service', 'Ingress',
            'Role', 'RoleBinding', 'ClusterRole', 'ClusterRoleBinding',
        ) for d in docs))
        deployment = next(d for d in docs if d['kind'] == 'Deployment')
        self.assertEqual(deployment['spec']['strategy']['type'], 'Recreate')
        self.assertEqual(deployment['spec']['replicas'], 1)
        pod = deployment['spec']['template']['spec']
        self.assertEqual(pod['serviceAccountName'], 'devnet-capacity-manager-active')
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertEqual(pod['terminationGracePeriodSeconds'], 1800)
        volumes = {v['name']: v for v in pod['volumes']}
        self.assertEqual(volumes['state']['persistentVolumeClaim']['claimName'],
                         'devnet-capacity-manager-active-state')
        self.assertEqual(volumes['dstack-token']['secret']['secretName'], 'dstack-controller-auth')
        self.assertEqual(volumes['dstack-token']['secret']['items'],
                         [{'key': 'admin-token', 'path': 'token'}])
        self.assertFalse(any('projected' in v or 'hostPath' in v for v in pod['volumes']))
        container = pod['containers'][0]
        env = {v['name']: v for v in container['env']}
        self.assertEqual(set(env), {'RUST_LOG', 'DOGEOS_PROOF_WORK_BEARER_TOKEN'})
        self.assertEqual(env['DOGEOS_PROOF_WORK_BEARER_TOKEN']['valueFrom']['secretKeyRef'],
                         {'name': 'devnet-capacity-manager-active-wp-token', 'key': 'proof-work-token'})

    def test_paid_gpu_ceiling_placement_and_readiness_are_explicit(self):
        policy = tomllib.loads(self.values['manager']['policy'])
        self.assertEqual(policy['global']['max_workers'], 1)
        self.assertEqual(policy['pool']['max_workers'], 1)
        self.assertEqual(policy['pool']['gpu_class'], 'RTX3090')
        self.assertEqual(policy['pool']['max_hourly_cost_usd'], 0.8)
        self.assertEqual(policy['families']['scroll_chunk']['runtime_seconds'], 240)
        for family in policy['families'].values():
            self.assertLessEqual(family['max_workers'], 1)
        docs = render(self.values)
        container = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']['containers'][0]
        args = container['args']
        for key, expected in {
            '--provisioner': 'dstack', '--dstack-project': 'main',
            '--worker-id-prefix': 'devnet-capacity-manager-active',
            '--dstack-instance-type': '55816748', '--dstack-region': 'nl-thenetherlands',
            '--dstack-fleet': 'devnet-capacity-manager-active-rtx3090',
            '--dstack-max-price-usd': '0.8',
        }.items():
            self.assertEqual(args[args.index(key) + 1], expected)
        self.assertIn('--scale-down-on-shutdown', args)
        self.assertIn('DOGEOS_PROVER_WORKER_READY_FILE=/dogeos/artifacts/prover-worker-ready-v1.json', args)
        self.assertIn('DOGEOS_PROVER_WORKER_TOKEN=${{ secrets.cm_active_worker_token_1013 }}', args)

    def test_verified_worker_contract_is_not_rewritten_by_rendering(self):
        command = self.values['manager']['workerCommand']
        # Independent receipt from the already tested DevNet manifest.
        self.assertEqual(hashlib.sha256(command.encode()).hexdigest(),
                         '81b537df1660ac50e4d64142b63f9b99afd537b1a906b7589e00873d4cfbbec0')
        docs = render(self.values)
        args = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']['containers'][0]['args']
        self.assertEqual(args[args.index('--dstack-worker-command') + 1], command)
        self.assertNotIn('X-Amz-Credential=', command)
        self.assertNotIn('X-Amz-Signature=', command)

    def test_fresh_install_uses_an_unannotated_dedicated_account_and_retained_claim(self):
        self.values['serviceAccount'] = {'create': True, 'name': 'isolated-manager'}
        self.values['persistence']['existingClaim'] = ''
        docs = render(self.values)
        account = next(d for d in docs if d['kind'] == 'ServiceAccount')
        self.assertEqual(account['metadata']['name'], 'isolated-manager')
        self.assertFalse(account['automountServiceAccountToken'])
        self.assertFalse(account['metadata'].get('annotations'))
        pod = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']
        self.assertEqual(pod['serviceAccountName'], 'isolated-manager')
        claim = next(d for d in docs if d['kind'] == 'PersistentVolumeClaim')
        self.assertEqual(claim['metadata']['annotations']['helm.sh/resource-policy'], 'keep')

    def test_cross_namespace_manager_peer_only_reaches_proof_work(self):
        values = yaml.safe_load((ROOT / 'examples/values/withdrawal-processor-production.yaml').read_text())
        overlay = yaml.safe_load((ROOT / 'examples/values/capacity-manager-devnet-wp-peer.yaml').read_text())
        peers = overlay['networkPolicy']['allowFrom']['capacityManager']
        values['networkPolicy']['allowFrom']['capacityManager'] = peers
        docs = render(values, 'withdrawal-processor')
        policy = next(d for d in docs if d['kind'] == 'NetworkPolicy')
        matching = [rule for rule in policy['spec']['ingress'] if any(peer in rule['from'] for peer in peers)]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['ports'], [{'port': 9300, 'protocol': 'TCP'}])
        self.assertEqual(peers[0]['namespaceSelector']['matchLabels'],
                         {'kubernetes.io/metadata.name': 'dstack-system'})


if __name__ == '__main__':
    unittest.main()
