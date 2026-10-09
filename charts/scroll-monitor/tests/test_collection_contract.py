"""Cross-chart discovery contracts required by the public-health design."""
from functools import lru_cache
from pathlib import Path
import subprocess
import unittest

import yaml

SDK = Path(__file__).resolve().parents[3]


@lru_cache
def render(chart, release, *args):
    result = subprocess.run(['helm', 'template', release, str(SDK / 'charts' / chart),
                             '--namespace', 'health-test', *args], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def matches(selector, labels):
    if any(labels.get(key) != value for key, value in selector.get('matchLabels', {}).items()):
        return False
    for expression in selector.get('matchExpressions', []):
        if expression['operator'] != 'Exists':
            raise AssertionError('Test must explicitly implement any new selector operator')
        if expression['key'] not in labels:
            return False
    return True


class CollectionContractTests(unittest.TestCase):
    def test_prometheus_discovers_blockscout_frontend_podmonitor_in_own_namespace(self):
        frontend = next(doc for doc in render('blockscout', 'blockscout') if doc['kind'] == 'PodMonitor')
        for profile in [None, SDK / 'charts/scroll-monitor/values/production.yaml',
                        SDK / 'examples/values/scroll-monitor-production.yaml']:
            args = ('-f', str(profile)) if profile else ()
            prometheus = next(doc for doc in render('scroll-monitor', 'monitor', *args)
                              if doc['kind'] == 'Prometheus')['spec']
            self.assertTrue(matches(prometheus['podMonitorSelector'], frontend['metadata']['labels']))
            self.assertFalse(matches(prometheus['podMonitorSelector'], {}))
            selector = prometheus['podMonitorNamespaceSelector']
            self.assertTrue(matches(selector, {'kubernetes.io/metadata.name': 'health-test'}))
            self.assertFalse(matches(selector, {'kubernetes.io/metadata.name': 'other-chain'}))
        workload = next(doc for doc in render('blockscout', 'blockscout')
                        if doc['kind'] == 'Deployment' and
                        matches(frontend['spec']['selector'], doc['spec']['template']['metadata']['labels']))
        ports = {port['name'] for container in workload['spec']['template']['spec']['containers']
                 for port in container.get('ports', [])}
        self.assertIn(frontend['spec']['podMetricsEndpoints'][0]['port'], ports)
        self.assertEqual(frontend['spec']['podMetricsEndpoints'][0]['path'], '/node-api/metrics')

    def test_eager_production_monitor_selects_its_real_private_service(self):
        profile = str(SDK / 'examples/values/eager-materializer-production.yaml')
        # Opaque config is required by the chart; no application process is started.
        for release in ['eager-materializer', 'custom-materializer']:
            docs = render('eager-materializer', release, '-f', profile,
                          '--set-string', 'eagerMaterializer.config=render-only-fixture')
            monitors = [doc for doc in docs if doc['kind'] == 'ServiceMonitor']
            self.assertEqual(len(monitors), 1)
            monitor = monitors[0]
            services = [doc for doc in docs if doc['kind'] == 'Service' and
                        matches(monitor['spec']['selector'], doc['metadata']['labels'])]
            self.assertEqual(len(services), 1)
            endpoint = monitor['spec']['endpoints'][0]
            self.assertEqual(endpoint, {'port': 'http', 'path': '/metrics',
                                        'interval': '30s', 'scrapeTimeout': '10s'})
            self.assertTrue(any(port['name'] == endpoint['port'] for port in services[0]['spec']['ports']))
            prometheus = next(doc for doc in render('scroll-monitor', 'monitor') if doc['kind'] == 'Prometheus')
            self.assertTrue(matches(prometheus['spec']['serviceMonitorSelector'], monitor['metadata']['labels']))
        disabled = render('eager-materializer', 'eager-materializer', '-f', profile,
                          '--set-string', 'eagerMaterializer.config=render-only-fixture',
                          '--set', 'serviceMonitor.main.enabled=false')
        self.assertFalse(any(doc['kind'] == 'ServiceMonitor' for doc in disabled))

    def test_current_reth_rpc_monitor_matches_service_even_with_name_overrides(self):
        profile = str(SDK / 'examples/values/l2-reth-rpc-production.yaml')
        for args in [(), ('--set', 'global.nameOverride=custom-rpc,service.main.fullname=private-rpc')]:
            docs = render('l2-reth', 'l2-reth-rpc', '-f', profile, *args)
            monitor = next(doc for doc in docs if doc['kind'] == 'ServiceMonitor')
            services = [doc for doc in docs if doc['kind'] == 'Service' and
                        matches(monitor['spec']['selector'], doc['metadata']['labels'])]
            self.assertEqual(len(services), 1)
            self.assertTrue(any(port['name'] == 'metrics' for port in services[0]['spec']['ports']))


if __name__ == '__main__':
    unittest.main()
