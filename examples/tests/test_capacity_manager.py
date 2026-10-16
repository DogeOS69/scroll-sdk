"""Render isolated capacity-manager and the WP peer without cluster access."""
import pathlib
import subprocess
import tempfile
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def config():
    return {'prepared': True, 'image': {'digest': 'sha256:' + 'a' * 64},
            'manager': {'workerIdPrefix': 'test-provers',
                        'workerImage': 'example.invalid/worker@sha256:' + 'b' * 64,
                        'workerCommand': 'exec prover-worker --worker-id {worker_id}',
                        'policy': '[global]\nmax_workers = 2\n',
                        'dstack': {'project': 'test-project', 'fleets': ['test-fleet'],
                                   'regions': ['us-east-1'], 'instanceTypes': ['g6.4xlarge']}}}


def render(chart, values):
    with tempfile.TemporaryDirectory() as directory:
        file = pathlib.Path(directory) / 'values.yaml'
        file.write_text(yaml.safe_dump(values))
        return subprocess.run(['helm', 'template', chart, str(ROOT / 'charts' / chart), '-f', str(file)],
                              capture_output=True, text=True)


class CapacityManagerTests(unittest.TestCase):
    def test_manager_is_single_writer_with_secret_references_and_no_public_listener(self):
        result = render('capacity-manager', config())
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        self.assertFalse(any(d['kind'] in ('Ingress', 'Service', 'Secret') for d in docs))
        deploy = next(d for d in docs if d['kind'] == 'Deployment')
        self.assertEqual(deploy['spec']['strategy']['type'], 'Recreate')
        self.assertEqual(deploy['spec']['replicas'], 1)
        pod = deploy['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        container = pod['containers'][0]
        self.assertIn('--dstack-max-price-usd', container['args'])
        self.assertEqual(container['args'][container['args'].index('--worker-credential-master-file') + 1],
                         '/run/secrets/worker-credential-master/master')
        self.assertFalse(any(arg.startswith('DOGEOS_PROVER_WORKER_TOKEN=') for arg in container['args']))
        self.assertNotIn('--scale-down-on-shutdown', container['args'])
        # The master comes from the coordinator Secret as a file, never as worker env.
        master = next(v for v in pod['volumes'] if v['name'] == 'worker-credential-master')
        self.assertEqual(master['secret'], {'secretName': 'proof-coordinator-secrets', 'defaultMode': 0o440,
                                            'items': [{'key': 'prover-worker-token', 'path': 'master'}]})
        self.assertIn('secretKeyRef', container['env'][0]['valueFrom'])
        pvc = next(d for d in docs if d['kind'] == 'PersistentVolumeClaim')
        self.assertEqual(pvc['metadata']['annotations']['helm.sh/resource-policy'], 'keep')

    def test_refuses_unprepared_mutable_or_multiple_writer_deployment(self):
        for change in [{'prepared': False}, {'replicaCount': 2}, {'image': {'digest': 'latest'}}]:
            values = config()
            values.update(change)
            result = render('capacity-manager', values)
            self.assertNotEqual(result.returncode, 0)

    def test_wp_manager_peer_can_only_reach_the_proof_work_port(self):
        values = yaml.safe_load((ROOT / 'examples/values/withdrawal-processor-production.yaml').read_text())
        peer = {'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'capacity-manager'}}}
        values['networkPolicy']['allowFrom']['capacityManager'] = [peer]
        result = render('withdrawal-processor', values)
        self.assertEqual(result.returncode, 0, result.stderr)
        policy = next(d for d in yaml.safe_load_all(result.stdout) if d and d['kind'] == 'NetworkPolicy')
        rules = policy['spec']['ingress']
        self.assertNotIn(peer, rules[0]['from'])
        self.assertIn(peer, rules[1]['from'])
        self.assertEqual(rules[1]['ports'], [{'port': 9300, 'protocol': 'TCP'}])


if __name__ == '__main__':
    unittest.main()
