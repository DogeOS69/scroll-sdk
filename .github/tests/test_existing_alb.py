"""Render real application releases and verify their existing-ALB ownership."""
import copy
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
# Binding key -> (ingress path, actual default Service name, Service port).
CHARTS = {
    'blockscout': {
        'blockscout-api': ('blockscout-stack.blockscout.ingress', 'blockscout-blockscout-svc', 80),
        'blockscout-frontend': ('blockscout-stack.frontend.ingress', 'blockscout-frontend-svc', 80),
    },
    'frontends': {'frontends': ('ingress.main', 'frontends', 80)},
    'l2-reth': {
        'l2-reth-rpc-public': ('ingress.main', 'l2-reth', 8545),
        'l2-reth-rpc-public-ws': ('ingress.websocket', 'l2-reth', 8546),
    },
    'proof-coordinator': {'proof-coordinator': ('ingress.main', 'proof-coordinator', 7788)},
    'tso-service': {'tso-service': ('ingress.main', 'tso-service', 3000)},
}


def ingress(values, path):
    for part in path.split('.'):
        values = values.setdefault(part, {})
    return values


def values_for(chart):
    values = {'targetGroupBindings': {}}
    if chart == 'proof-coordinator':
        values['service'] = {'main': {'enabled': True}}
    for index, (name, (path, service, port)) in enumerate(CHARTS[chart].items()):
        ingress(values, path)['enabled'] = False
        values['targetGroupBindings'][name] = {
            'targetGroupARN': f'arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/fixture-{index}/{index:016x}',
            'targetType': 'ip', 'serviceRef': {'name': service, 'port': port},
        }
    return values


class ExistingAlbTests(unittest.TestCase):
    def render(self, chart, values):
        return subprocess.run(
            ['helm', 'template', chart, str(ROOT / 'charts' / chart), '-n', 'operator', '-f', '-'],
            input=yaml.safe_dump(values), text=True, capture_output=True, check=False,
        )

    def documents(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    def test_each_application_release_owns_its_bindings_and_services(self):
        for chart in CHARTS:
            with self.subTest(chart=chart):
                values = values_for(chart)
                docs = self.documents(self.render(chart, values))
                self.assertFalse(any(d['kind'] == 'Ingress' for d in docs))
                bindings = [d for d in docs if d['kind'] == 'TargetGroupBinding']
                self.assertEqual(len(bindings), len(CHARTS[chart]))
                services = {d['metadata']['name']: d for d in docs if d['kind'] == 'Service'}
                for binding in bindings:
                    metadata = binding['metadata']
                    self.assertEqual(metadata['namespace'], 'operator')
                    self.assertEqual(metadata['labels']['app.kubernetes.io/instance'], chart)
                    self.assertEqual(metadata['labels']['app.kubernetes.io/managed-by'], 'Helm')
                    self.assertLessEqual(len(metadata['name']), 63)
                    # No keep policy or deletion hooks: normal application uninstall removes TGBs.
                    self.assertNotIn('annotations', metadata)
                    self.assertNotIn('ownerReferences', metadata)
                    self.assertIn(binding['spec'], values['targetGroupBindings'].values())
                    ref = binding['spec']['serviceRef']
                    service = services[ref['name']]['spec']
                    self.assertEqual(service.get('type', 'ClusterIP'), 'ClusterIP')
                    self.assertTrue(service['selector'])
                    self.assertIn(ref['port'], [p['port'] for p in service['ports']])

    def test_bindings_are_opt_in_for_every_application(self):
        for chart in CHARTS:
            with self.subTest(chart=chart):
                docs = self.documents(self.render(chart, {}))
                self.assertFalse(any(d['kind'] == 'TargetGroupBinding' for d in docs))

    def test_managed_ingress_cannot_coexist_with_bindings(self):
        for chart, entries in CHARTS.items():
            for path, _, _ in entries.values():
                with self.subTest(chart=chart, ingress=path):
                    values = values_for(chart)
                    ingress(values, path).update(enabled=True, hosts=[])
                    result = self.render(chart, values)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('disable Ingress', result.stderr)

    def test_invalid_bindings_fail_before_install(self):
        for chart in CHARTS:
            for field, value in [('targetType', 'instance'), ('targetGroupARN', 'REPLACE_WITH_ARN'), ('port', 0), ('port', 65536), ('port', '80'), ('port', 80.5)]:
                with self.subTest(chart=chart, field=field, value=value):
                    values = values_for(chart)
                    binding = next(iter(values['targetGroupBindings'].values()))
                    (binding['serviceRef'] if field == 'port' else binding)[field] = value
                    self.assertNotEqual(self.render(chart, values).returncode, 0)

    def test_rejects_foreign_bindings_and_duplicate_target_groups(self):
        for chart in CHARTS:
            with self.subTest(chart=chart):
                values = values_for(chart)
                values['targetGroupBindings']['unrelated'] = copy.deepcopy(next(iter(values['targetGroupBindings'].values())))
                self.assertIn('unsupported targetGroupBindings key', self.render(chart, values).stderr)
        for chart in ['blockscout', 'l2-reth']:
            values = values_for(chart)
            first, second = values['targetGroupBindings'].values()
            second['targetGroupARN'] = first['targetGroupARN']
            self.assertIn('distinct', self.render(chart, values).stderr)

    def test_tso_binding_requires_network_policy_edge_peers(self):
        values = values_for('tso-service')
        values['networkPolicy'] = {'enabled': True, 'allowFrom': {
            'edge': [],
            'withdrawalProcessor': [{'podSelector': {'matchLabels': {'app': 'withdrawal-processor'}}}],
            'signers': [{'podSelector': {'matchLabels': {'app': 'signer'}}}],
        }}
        self.assertIn('networkPolicy.allowFrom.edge', self.render('tso-service', values).stderr)
        values['networkPolicy']['allowFrom']['edge'] = [{'ipBlock': {'cidr': '192.0.2.0/24'}}]
        self.documents(self.render('tso-service', values))


if __name__ == '__main__':
    unittest.main()
