"""Render the actual chart; no Kubernetes or registry access is required."""
import pathlib
import subprocess
import unittest

import yaml

CHART = pathlib.Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]


def render(*args, success=True):
    result = subprocess.run(['helm', 'template', 'dogecoin-testnet', str(CHART),
                             '--namespace', 'test', *args], capture_output=True, text=True)
    if not success:
        return result
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def deployment(docs):
    return next(doc for doc in docs if doc['kind'] == 'Deployment')


class DogecoinChartTests(unittest.TestCase):
    def test_single_writer_and_existing_pvc_names_are_preserved(self):
        docs = render()
        spec = deployment(docs)['spec']
        self.assertEqual(spec['strategy'], {'type': 'Recreate'})
        self.assertEqual(spec['replicas'], 1)
        self.assertEqual(spec['template']['spec']['terminationGracePeriodSeconds'], 300)
        volume = spec['template']['spec']['volumes'][-1]
        self.assertEqual(volume['persistentVolumeClaim']['claimName'], 'dogecoin-testnet-data')
        pvc = next(doc for doc in docs if doc['kind'] == 'PersistentVolumeClaim')
        self.assertEqual(pvc['metadata']['name'], 'dogecoin-testnet-data')
        self.assertEqual(pvc['metadata']['annotations']['helm.sh/resource-policy'], 'keep')
        self.assertEqual(pvc['spec']['resources']['requests']['storage'], '50Gi')
        reused = render('--set', 'storage.existingClaim=already-synced', '--set', 'storage.size=123Gi')
        self.assertFalse(any(doc['kind'] == 'PersistentVolumeClaim' for doc in reused))
        self.assertEqual(deployment(reused)['spec']['template']['spec']['volumes'][-1]
                         ['persistentVolumeClaim']['claimName'], 'already-synced')

    def test_all_networks_start_probing_immediately_with_correct_local_rpc_port(self):
        for filename, rpc in [(None, 44555), ('values-mainnet.yaml', 22555), ('values-regtest.yaml', 18332)]:
            with self.subTest(network=filename):
                docs = render(*(['-f', str(CHART / filename)] if filename else []))
                container = deployment(docs)['spec']['template']['spec']['containers'][0]
                for kind in ['startupProbe', 'readinessProbe']:
                    probe = container[kind]
                    self.assertEqual(probe['initialDelaySeconds'], 0)
                    self.assertEqual(probe['periodSeconds'], 5)
                    command = probe['exec']['command']
                    self.assertIn('-conf=/tmp/dogecoin.conf', command)
                    self.assertIn('-rpcconnect=127.0.0.1', command)
                    self.assertIn(f'-rpcport={rpc}', command)
                    self.assertEqual(command[-1], 'getblockchaininfo')
                    self.assertNotIn('-rpcwait', command)
                    self.assertFalse(any('rpcpassword' in arg for arg in command))
                # Long startup budget imposes no minimum delay once RPC succeeds.
                startup = container['startupProbe']
                self.assertEqual(startup['periodSeconds'] * startup['failureThreshold'], 3600)
                # Sync progress or an overloaded RPC method must not restart the node.
                self.assertEqual(container['livenessProbe']['tcpSocket'], {'port': 'rpc'})
                self.assertNotIn('exec', container['livenessProbe'])
                stop = container['lifecycle']['preStop']['exec']['command']
                self.assertIn(f'-rpcport={rpc}', stop)
                self.assertIn('-rpcclienttimeout=5', stop)
                self.assertEqual(stop[-1], 'stop')

    def test_operator_probe_and_shutdown_overrides_are_respected(self):
        docs = render('--set', 'probes.startup.failureThreshold=2160',
                      '--set', 'probes.readiness.periodSeconds=2',
                      '--set', 'terminationGracePeriodSeconds=900')
        pod = deployment(docs)['spec']['template']['spec']
        self.assertEqual(pod['terminationGracePeriodSeconds'], 900)
        self.assertEqual(pod['containers'][0]['startupProbe']['failureThreshold'], 2160)
        self.assertEqual(pod['containers'][0]['readinessProbe']['periodSeconds'], 2)

    def test_config_and_managed_secret_changes_trigger_restart_without_changing_pvc(self):
        def template(*args):
            return deployment(render(*args))['spec']['template']
        before = template()
        same = template()
        config = template('--set', 'dogecoinConf.txindex=1')
        secret = template('--set', 'rpcPassword.value=another-fixture-password')
        annotations = before['metadata']['annotations']
        self.assertEqual(annotations, same['metadata']['annotations'])
        self.assertNotEqual(annotations['checksum/config'], config['metadata']['annotations']['checksum/config'])
        self.assertNotEqual(annotations['checksum/rpc-secret'], secret['metadata']['annotations']['checksum/rpc-secret'])
        self.assertEqual(before['spec']['volumes'][-1], config['spec']['volumes'][-1])

    def test_external_secret_references_change_rollout_checksum(self):
        args = ['-f', str(CHART / 'values/production.yaml')]
        first = deployment(render(*args))['spec']['template']['metadata']['annotations']
        second = deployment(render(*args, '--set', 'externalSecrets.dogecoin-secret-env.refreshInterval=5m'))['spec']['template']['metadata']['annotations']
        self.assertNotIn('checksum/rpc-secret', first)
        self.assertNotEqual(first['checksum/external-secret-spec'], second['checksum/external-secret-spec'])

    def test_invalid_replica_and_probe_settings_are_rejected(self):
        for setting in ['replicaCount=2', 'replicaCount=0', 'probes.startup.periodSeconds=0',
                        'probes.readiness.timeoutSeconds=0', 'probes.liveness.failureThreshold=0',
                        'terminationGracePeriodSeconds=0', 'probes.startup.tcpSocket.port=rpc']:
            with self.subTest(setting=setting):
                result = render('--set', setting, success=False)
                self.assertNotEqual(result.returncode, 0)
        # Template guard is useful for callers that bypass JSON schema checks.
        result = render('--skip-schema-validation', '--set', 'replicaCount=2', success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('all Pods share one datadir PVC', result.stderr)

    def test_production_examples_share_lifecycle_defaults_and_preserve_storage(self):
        source = yaml.safe_load((CHART / 'values/production.yaml').read_text())
        example = yaml.safe_load((ROOT / 'examples/values/dogecoin-production.yaml').read_text())
        for key in ['replicaCount', 'terminationGracePeriodSeconds', 'probes']:
            self.assertEqual(source[key], example[key])
        docs = render('-f', str(CHART / 'values/production.yaml'))
        container = deployment(docs)['spec']['template']['spec']['containers'][0]
        self.assertEqual(container['readinessProbe']['initialDelaySeconds'], 0)
        self.assertEqual(container['startupProbe']['failureThreshold'], 720)
        self.assertEqual(next(doc for doc in docs if doc['kind'] == 'PersistentVolumeClaim')
                         ['spec']['resources']['requests']['storage'], source['storage']['size'])
        example_docs = render('-f', str(ROOT / 'examples/values/dogecoin-production.yaml'))
        self.assertEqual(next(doc for doc in example_docs if doc['kind'] == 'PersistentVolumeClaim')
                         ['spec']['resources']['requests']['storage'], example['storage']['size'])


if __name__ == '__main__':
    unittest.main()
