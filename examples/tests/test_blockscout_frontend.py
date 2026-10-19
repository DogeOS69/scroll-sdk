"""The pinned Blockscout chart must emit unique, complete frontend environment."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class BlockscoutFrontendTests(unittest.TestCase):
    def test_example_renders_unique_network_host_and_metrics_environment(self):
        result = subprocess.run(['helm', 'template', 'blockscout', str(ROOT / 'charts/blockscout'),
                                 '-f', str(ROOT / 'examples/values/blockscout-production.yaml')],
                                capture_output=True, text=True, check=True)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        frontend = next(d for d in docs if d['kind'] == 'Deployment' and 'frontend' in d['metadata']['name'])
        env = frontend['spec']['template']['spec']['containers'][0]['env']
        names = [e['name'] for e in env]
        self.assertEqual(len(names), len(set(names)))
        values = {e['name']: e.get('value') for e in env}
        self.assertEqual(values['NEXT_PUBLIC_APP_HOST'], 'blockscout.scrollsdk')
        self.assertEqual(values['NEXT_PUBLIC_NETWORK_ID'], '221122')
        self.assertEqual(values['NEXT_PUBLIC_NETWORK_CURRENCY_SYMBOL'], 'DOGE')

    def test_chart_production_keeps_metrics_disabled_and_network_env_unique(self):
        output = subprocess.check_output([
            'helm', 'template', 'blockscout', str(ROOT / 'charts/blockscout'),
            '-f', str(ROOT / 'charts/blockscout/values/production.yaml'),
        ], text=True)
        docs = [d for d in yaml.safe_load_all(output) if d]
        frontend = next(d for d in docs if d['kind'] == 'Deployment' and 'frontend' in d['metadata']['name'])
        env = frontend['spec']['template']['spec']['containers'][0]['env']
        names = [e['name'] for e in env]
        self.assertEqual(len(names), len(set(names)))
        values = {e['name']: e.get('value') for e in env}
        self.assertEqual(values['PROMETHEUS_METRICS_ENABLED'], 'false')
        self.assertEqual(values['NEXT_PUBLIC_NETWORK_SHORT_NAME'], 'DogeOS')
        self.assertEqual(values['NEXT_PUBLIC_NETWORK_CURRENCY_DECIMALS'], '18')
        self.assertFalse(any(d['kind'] == 'ServiceMonitor' and
                             not d['metadata']['name'].endswith('-bb') for d in docs))

    def test_spec_examples_declare_required_dedicated_alb_references(self):
        for path in sorted((ROOT / 'examples').glob('deployment-spec.*.example.yaml')):
            with self.subTest(profile=path.name):
                spec = yaml.safe_load(path.read_text())
                alb = spec['infrastructure']['aws']['alb']
                for name in ('tso', 'proof'):
                    endpoint = alb['endpoints'][name]
                    self.assertIsInstance(endpoint, dict)
                    for field in ('loadBalancerArn', 'listenerArn'):
                        self.assertTrue(endpoint[field].startswith('REPLACE_WITH_'))

    def test_shared_alb_renders_inherited_routes_and_unique_environment(self):
        values = yaml.safe_load((ROOT / 'examples/values/blockscout-production.yaml').read_text())
        stack = values['blockscout-stack']
        for component in ['blockscout', 'frontend']:
            ingress = stack[component]['ingress']
            ingress['enabled'] = True
            ingress['hostname'] = 'explorer.example.invalid'
            ingress['annotations']['alb.ingress.kubernetes.io/group.name'] = 'public-example'
            ingress['annotations']['alb.ingress.kubernetes.io/certificate-arn'] = (
                'arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000')
            self.assertNotIn('paths', ingress)
        # Enabled upstream Ingress templates own these host variables.
        for key in ['NEXT_PUBLIC_API_HOST', 'NEXT_PUBLIC_APP_HOST']:
            del stack['frontend']['env'][key]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as file:
            yaml.safe_dump(values, file)
            file.flush()
            output = subprocess.check_output(['helm', 'template', 'blockscout', str(ROOT / 'charts/blockscout'),
                                              '-f', file.name], text=True)
        docs = [d for d in yaml.safe_load_all(output) if d]
        ingresses = [d for d in docs if d['kind'] == 'Ingress']
        self.assertEqual(len(ingresses), 2)
        api = next(d for d in ingresses if 'frontend' not in d['metadata']['name'])
        routes = api['spec']['rules'][0]['http']['paths']
        self.assertTrue({'/api', '/socket', '/public-metrics', '/auth/auth0', '/auth/auth0/callback', '/auth/logout'} <= {r['path'] for r in routes})
        for ingress in ingresses:
            annotations = ingress['metadata']['annotations']
            self.assertTrue(all(isinstance(value, str) for value in annotations.values()))
            self.assertFalse(any(key.startswith('nginx.') for key in annotations))
            self.assertEqual(annotations['alb.ingress.kubernetes.io/group.name'], 'public-example')
            self.assertEqual(ingress['spec']['ingressClassName'], 'alb')
        frontend = next(d for d in ingresses if 'frontend' in d['metadata']['name'])
        self.assertLess(int(api['metadata']['annotations']['alb.ingress.kubernetes.io/group.order']),
                        int(frontend['metadata']['annotations']['alb.ingress.kubernetes.io/group.order']))
        self.assertEqual(api['metadata']['annotations']['alb.ingress.kubernetes.io/healthcheck-path'], '/api/health/readiness')
        self.assertEqual(frontend['metadata']['annotations']['alb.ingress.kubernetes.io/healthcheck-path'], '/api/healthz')
        for doc in docs:
            if doc['kind'] not in ['Deployment', 'Job']:
                continue
            pod = doc['spec']['template']['spec']
            self.assertFalse(pod.get('imagePullSecrets'))
            for container in pod.get('containers', []) + pod.get('initContainers', []):
                env = container.get('env', [])
                names = [item['name'] for item in env]
                self.assertEqual(len(names), len(set(names)), container['name'])
                if 'NEXT_PUBLIC_API_HOST' in names:
                    rendered = {item['name']: item.get('value') for item in env}
                    self.assertEqual(rendered['NEXT_PUBLIC_API_HOST'], 'explorer.example.invalid')
                    self.assertEqual(rendered['NEXT_PUBLIC_API_WEBSOCKET_PROTOCOL'], 'wss')


if __name__ == '__main__':
    unittest.main()
