"""Runtime configuration changes must recreate the Pod that builds runtime-env.js."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]


class RuntimeConfigTests(unittest.TestCase):
    def render(self, config):
        result = subprocess.run(['helm', 'template', 'frontends', str(CHART), '-f', '-'],
                                input=yaml.safe_dump({'scrollConfig': config,
                                                      'podAnnotations': {'example.com/owner': 'ops'}}),
                                text=True, capture_output=True, check=True)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        deployment = next(d for d in docs if d['kind'] == 'Deployment')
        configmap = next(d for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'frontends-config')
        self.assertEqual(configmap['data']['frontend-config'].strip(), config.strip())
        self.assertEqual(deployment['spec']['template']['metadata']['annotations']['example.com/owner'], 'ops')
        return deployment['spec']['template']

    def test_runtime_config_changes_rollout_and_repeated_render_is_stable(self):
        old = self.render('REACT_APP_EXTERNAL_RPC_URI_L2 = "https://rpc.example.invalid/old"\n')
        new_config = 'REACT_APP_EXTERNAL_RPC_URI_L2 = "https://rpc.example.invalid/new"\n'
        new = self.render(new_config)
        self.assertNotEqual(old['metadata']['annotations']['checksum/frontend-config'],
                            new['metadata']['annotations']['checksum/frontend-config'])
        self.assertEqual(new, self.render(new_config))


if __name__ == '__main__':
    unittest.main()
