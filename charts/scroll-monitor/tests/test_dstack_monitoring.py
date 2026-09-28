"""Cross-chart monitoring contract: discovery, auth, dashboards and alert routing."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

SDK = Path(__file__).resolve().parents[3]
MONITOR = SDK / 'charts/scroll-monitor'
CONTROLLER = SDK / 'charts/dstack-controller'


def render(chart, values=None):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as f:
        yaml.safe_dump(values or {}, f)
        f.flush()
        result = subprocess.run(['helm', 'template', 'monitor' if chart == MONITOR else 'gpu',
                                 str(chart), '--namespace', 'monitoring' if chart == MONITOR else 'gpu-system',
                                 '-f', f.name], text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return [d for d in yaml.safe_load_all(result.stdout) if d]


def one(docs, kind, name=None):
    return next(d for d in docs if d['kind'] == kind and (name is None or d['metadata']['name'] == name))


def rules(docs):
    config = one(docs, 'ConfigMap', 'monitor-grafana-alerts')['data']['rules.json']
    return [r for g in json.loads(config)['groups'] for r in g['rules'] if r['alert'].startswith('Dstack')]


class DstackMonitoringTests(unittest.TestCase):
    def test_opt_in_native_metrics_with_separate_secret_and_exact_service_selector(self):
        default = render(CONTROLLER)
        self.assertFalse(any(d['kind'] == 'ServiceMonitor' for d in default))
        docs = render(CONTROLLER, {'fullnameOverride': 'custom-dstack', 'monitoring': {
            'enabled': True, 'auth': {'existingSecret': 'metrics', 'key': 'bearer'}, 'interval': '60s'}})
        service = one(docs, 'Service')
        monitor = one(docs, 'ServiceMonitor')
        for k, v in monitor['spec']['selector']['matchLabels'].items():
            self.assertEqual(service['metadata']['labels'][k], v)
        self.assertEqual(monitor['metadata']['namespace'], 'gpu-system')
        self.assertEqual(monitor['spec']['namespaceSelector']['matchNames'], ['gpu-system'])
        endpoint = monitor['spec']['endpoints'][0]
        self.assertEqual(endpoint['authorization']['credentials'], {'name': 'metrics', 'key': 'bearer'})
        self.assertEqual(endpoint['interval'], '60s')
        deployment = one(docs, 'Deployment')
        containers = deployment['spec']['template']['spec']['containers']
        self.assertEqual(len(containers), 1)  # native path has no extra process/pod
        env = {e['name']: e for e in containers[0]['env']}
        self.assertEqual(env['DSTACK_PROMETHEUS_AUTH_TOKEN']['valueFrom']['secretKeyRef'], endpoint['authorization']['credentials'])
        self.assertEqual(env['DSTACK_OTEL_METRICS_EXPORTERS']['value'], 'prometheus')
        self.assertFalse(any(d['kind'] == 'Secret' for d in docs))

    def test_auth_bypass_and_invalid_interval_are_rejected(self):
        for values in [
            {'monitoring': {'enabled': True, 'auth': {'existingSecret': 'dstack-controller-auth'}}},
            {'monitoring': {'enabled': True, 'interval': '5s', 'scrapeTimeout': '10s'}},
            {'monitoring': {'enabled': True, 'sampleLimit': 0}},
            {'extraEnv': [{'name': 'DSTACK_PROMETHEUS_AUTH_TOKEN', 'value': 'unsafe'}]},
            {'extraEnv': [{'name': 'DSTACK_ENABLE_PROMETHEUS_METRICS', 'value': 'false'}]},
        ]:
            with self.subTest(values=values), self.assertRaises(AssertionError):
                render(CONTROLLER, values)

    def test_monitor_overlay_discovers_both_namespaces_and_provisions_dashboard(self):
        values = yaml.safe_load((MONITOR / 'values/dstack.yaml').read_text())
        docs = render(MONITOR, values)
        selector = one(docs, 'Prometheus')['spec']['serviceMonitorNamespaceSelector']
        self.assertFalse(selector.get('matchLabels'))
        self.assertEqual(selector['matchExpressions'][0]['values'], ['monitoring', 'dstack-system'])
        config = one(docs, 'ConfigMap', 'grafana-alloy-config')['data']['config.alloy']
        self.assertIn('["monitoring","dstack-system"]', config)
        dashboard = json.loads(one(docs, 'ConfigMap', 'grafana-dogeos-dashboards')['data']['dstack.json'])
        self.assertEqual(dashboard['uid'], 'dogeos-dstack')
        self.assertIn('cached', dashboard['panels'][0]['options']['content'])
        native = rules(docs)
        self.assertEqual(len(native), 3)
        self.assertTrue(all(r['labels']['visibility'] == 'internal' for r in native))
        self.assertFalse(any('status_page' in str(r['labels']) for r in native))
        values['grafanaAlerting'] = {'enabled': False}
        fallback = one(render(MONITOR, values), 'PrometheusRule', 'monitor-dogeos')['spec']['groups']
        self.assertEqual(native, [r for g in fallback for r in g['rules'] if r['alert'].startswith('Dstack')])

    def test_disabled_integration_leaves_baseline_unchanged(self):
        docs = render(MONITOR)
        self.assertEqual(rules(docs), [])
        self.assertNotIn('dstack.json', one(docs, 'ConfigMap', 'grafana-dogeos-dashboards')['data'])
        self.assertNotIn('dstack-system', one(docs, 'ConfigMap', 'grafana-alloy-config')['data']['config.alloy'])

    def test_optional_host_inventory_and_validation(self):
        values = {'dstack': {'enabled': True, 'gpuHosts': {'enabled': True, 'expectedHosts': ['gpu-01', 'gpu-02']}}}
        result = rules(render(MONITOR, values))
        host = [r for r in result if r['alert'] == 'DstackHostTelemetryUnavailable']
        self.assertEqual(len(host), 1)  # One Grafana UID, multiple host alert instances.
        self.assertIn('gpu-01', host[0]['expr'])
        self.assertIn('gpu-02', host[0]['expr'])
        self.assertTrue(all('absent(node_time_seconds' in r['expr'] for r in host))
        values['dstack']['gpuHosts']['expectedHosts'] = []
        self.assertFalse(any(r['alert'] == 'DstackHostTelemetryUnavailable' for r in rules(render(MONITOR, values))))
        for bad in [['duplicate', 'duplicate'], ['bad"host']]:
            values['dstack']['gpuHosts']['expectedHosts'] = bad
            with self.assertRaises(AssertionError):
                render(MONITOR, values)


if __name__ == '__main__':
    unittest.main()
