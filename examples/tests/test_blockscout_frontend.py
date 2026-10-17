"""The pinned Blockscout chart must emit unique, complete frontend environment."""
from pathlib import Path
import subprocess
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


if __name__ == '__main__':
    unittest.main()
