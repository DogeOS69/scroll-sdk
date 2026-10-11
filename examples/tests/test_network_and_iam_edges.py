"""Render production defaults and bridge ingress isolation without cluster access."""
import pathlib
import subprocess
import tempfile
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CERT = 'arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000'


def values(service):
    return yaml.safe_load((ROOT / 'examples' / 'values' / f'{service}-production.yaml').read_text())


def render(chart, config, success=True):
    with tempfile.TemporaryDirectory() as directory:
        file = pathlib.Path(directory) / 'values.yaml'
        file.write_text(yaml.safe_dump(config))
        result = subprocess.run(['helm', 'template', chart, str(ROOT / 'charts' / chart),
                                 '-n', 'default', '-f', str(file)], capture_output=True, text=True)
    if not success:
        return result
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


class ProductionNetworkTests(unittest.TestCase):
    def test_optional_l1_devnet_keeps_rpc_internal_by_default(self):
        docs = render('l1-devnet', values('l1-devnet'))
        self.assertTrue(any(doc['kind'] == 'Service' for doc in docs))
        self.assertFalse(any(doc['kind'] == 'Ingress' for doc in docs))

    def tso(self):
        config = values('tso-service')
        config['networkPolicy']['allowFrom']['edge'] = [{'ipBlock': {'cidr': '10.0.10.0/24'}}]
        config['ingress']['main']['annotations']['alb.ingress.kubernetes.io/certificate-arn'] = CERT
        return config

    def test_tso_selects_only_its_pods_and_keeps_management_routes_internal(self):
        docs = render('tso-service', self.tso())
        policy = next(doc for doc in docs if doc['kind'] == 'NetworkPolicy')
        workload = next(doc for doc in docs if doc['kind'] == 'StatefulSet')
        labels = workload['spec']['template']['metadata']['labels']
        for key, value in policy['spec']['podSelector']['matchLabels'].items():
            self.assertEqual(labels[key], value)
        rule = policy['spec']['ingress'][0]
        self.assertEqual(rule['ports'], [{'port': 3000, 'protocol': 'TCP'}])
        self.assertIn({'ipBlock': {'cidr': '10.0.10.0/24'}}, rule['from'])
        self.assertTrue(all(peer.get('podSelector', {}).get('matchLabels') or peer.get('ipBlock') for peer in rule['from']))
        ingress = next(doc for doc in docs if doc['kind'] == 'Ingress')
        self.assertEqual(ingress['spec']['ingressClassName'], 'alb')
        self.assertEqual([path['path'] for path in ingress['spec']['rules'][0]['http']['paths']], ['/health', '/signer'])
        self.assertNotIn('tls', ingress['spec'])
        self.assertFalse(any('nginx' in key or 'cert-manager' in key for key in ingress['metadata']['annotations']))

    def test_wp_separates_api_and_proof_work_callers(self):
        docs = render('withdrawal-processor', values('withdrawal-processor'))
        policy = next(doc for doc in docs if doc['kind'] == 'NetworkPolicy')
        rules = policy['spec']['ingress']
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0]['ports'], [{'port': 3000, 'protocol': 'TCP'}])
        self.assertEqual(rules[1]['ports'], [{'port': 9300, 'protocol': 'TCP'}])
        self.assertEqual(rules[1]['from'], [{'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'proof-coordinator'}}}])
        self.assertNotIn(rules[1]['from'][0], rules[0]['from'])
        self.assertFalse(any(doc['kind'] == 'Ingress' for doc in docs))

    def test_helm_rejects_unresolved_edge_or_unrestricted_peers(self):
        configs = [values('tso-service')]
        for peer in [{}, {'podSelector': {}}, {'namespaceSelector': {}}, {'ipBlock': {'cidr': '0.0.0.0/0'}}, {'ipBlock': {'cidr': '::/0'}}]:
            config = self.tso()
            config['networkPolicy']['allowFrom']['edge'] = [peer]
            configs.append(config)
        for config in configs:
            with self.subTest(config=config['networkPolicy']['allowFrom']['edge']):
                result = render('tso-service', config, success=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('networkPolicy.allowFrom', result.stderr)

    def test_optional_dogecoin_edge_clears_inherited_nginx_and_tls(self):
        config = values('dogecoin')
        self.assertFalse(config['ingress']['enabled'])
        docs = render('dogecoin', config)
        self.assertFalse(any(doc['kind'] == 'Ingress' for doc in docs))
        config['ingress']['enabled'] = True
        config['ingress']['annotations']['alb.ingress.kubernetes.io/certificate-arn'] = CERT
        docs = render('dogecoin', config)
        ingress = next(doc for doc in docs if doc['kind'] == 'Ingress')
        self.assertEqual(ingress['spec']['ingressClassName'], 'alb')
        self.assertNotIn('tls', ingress['spec'])
        self.assertFalse(any('nginx' in key for key in ingress['metadata']['annotations']))

    def test_all_enabled_example_edges_choose_alb(self):
        def check(entry):
            if not isinstance(entry, dict):
                return
            if any(key in entry for key in ['enabled', 'hosts', 'hostname', 'className', 'ingressClassName']):
                if entry.get('enabled') is not False:
                    self.assertEqual(entry.get('className', entry.get('ingressClassName')), 'alb')
            else:
                for child in entry.values():
                    check(child)
        for file in (ROOT / 'examples' / 'values').glob('*-production.yaml'):
            config = yaml.safe_load(file.read_text())
            with self.subTest(file=file.name):
                check(config.get('ingress'))
                check(config.get('grafana', {}).get('ingress'))
                for component in config.get('blockscout-stack', {}).values():
                    check(component.get('ingress'))


if __name__ == '__main__':
    unittest.main()
