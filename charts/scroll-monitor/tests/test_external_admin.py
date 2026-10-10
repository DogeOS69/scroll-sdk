"""Grafana consumes externally synchronized credentials, like Dogecoin."""
import pathlib
import subprocess
import unittest

import yaml

CHART = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = CHART.parents[1] / 'examples/values/scroll-monitor-production.yaml'


class ExternalAdminTest(unittest.TestCase):
    def render(self, *flags):
        result = subprocess.run(
            ['helm', 'template', 'monitor-test', str(CHART), '-n', 'test',
             '-f', str(EXAMPLE), *flags],
            check=True, capture_output=True, text=True,
        )
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def test_aws_store_and_grafana_reference_share_the_secret(self):
        documents = self.render()
        external = next(item for item in documents if item['kind'] == 'ExternalSecret'
                        and item['metadata']['name'] == 'grafana-admin')
        store = next(item for item in documents if item['kind'] == 'SecretStore'
                     and item['metadata']['name'] == 'grafana-admin')
        self.assertEqual(external['spec']['target']['name'], 'grafana-admin')
        self.assertEqual({item['secretKey'] for item in external['spec']['data']},
                         {'admin-user', 'admin-password'})
        self.assertTrue(all(item['remoteRef']['key'] == 'grafana-admin-env'
                            for item in external['spec']['data']))
        self.assertEqual(store['spec']['provider']['aws']['auth']['jwt']
                         ['serviceAccountRef']['name'], 'external-secrets')
        self.assertFalse(any(item['kind'] == 'Secret'
                             and item['metadata']['name'] == 'grafana-admin'
                             for item in documents))
        deployment = next(item for item in documents if item['kind'] == 'Deployment'
                          and item['metadata']['name'] == 'grafana')
        container = next(item for item in deployment['spec']['template']['spec']['containers']
                         if item['name'] == 'grafana')
        password = next(item for item in container['env']
                        if item['name'] == 'GF_SECURITY_ADMIN_PASSWORD')
        self.assertEqual(password['valueFrom']['secretKeyRef'],
                         {'name': 'grafana-admin', 'key': 'admin-password'})

    def test_vault_store_uses_the_selected_authentication(self):
        documents = self.render(
            '--set', 'externalSecrets.grafana-admin.provider=vault',
            '--set', 'externalSecrets.grafana-admin.server=http://vault.test:8200',
            '--set', 'externalSecrets.grafana-admin.path=operator',
            '--set', 'externalSecrets.grafana-admin.version=v2',
            '--set', 'externalSecrets.grafana-admin.tokenSecretName=vault-auth',
            '--set', 'externalSecrets.grafana-admin.tokenSecretKey=token',
        )
        store = next(item for item in documents if item['kind'] == 'SecretStore'
                     and item['metadata']['name'] == 'grafana-admin')
        self.assertEqual(set(store['spec']['provider']), {'vault'})
        self.assertEqual(store['spec']['provider']['vault']['auth']['tokenSecretRef'],
                         {'name': 'vault-auth', 'key': 'token'})


if __name__ == '__main__':
    unittest.main()
