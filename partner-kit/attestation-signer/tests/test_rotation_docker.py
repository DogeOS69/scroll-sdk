"""Opt-in Docker integration; only disposable fake signers, never live services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

from test_rotation import KEYS, envelope

IMAGE = 'python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
WRAPPER = Path(__file__).parents[1] / 'scripts/rotation.sh'
SERVER = '''import json, tomllib
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        config = tomllib.load(open('/etc/signer.toml', 'rb'))
        body = {'public_key': %r, 'network': 'testnet', 'policy_mode': 'enforce',
                'v2_capabilities': [{'capability': 'advance_l1', 'production_serving': True},
                                    {'capability': 'advance_l2', 'production_serving': True},
                                    {'capability': 'rotate_key', 'production_serving':
                    bool(config.get('rotation_policy', {}).get('allowed_next_bridge_script_hashes'))}]}
        self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(body).encode())
    def log_message(self, *args): pass
HTTPServer(('0.0.0.0', 4040), Handler).serve_forever()
''' % KEYS[0]


@unittest.skipUnless(os.environ.get('RUN_DOCKER_ROTATION_TESTS') == '1', 'Set RUN_DOCKER_ROTATION_TESTS=1 for disposable Docker test')
class DockerApprovalTest(unittest.TestCase):
    def run_command(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_ready_without_restart_or_rotation_allowlist(self):
        name = 'sdk-readiness-test-' + uuid.uuid4().hex[:12]
        with tempfile.TemporaryDirectory(prefix='sdk-rotation-') as folder:
            root = Path(folder)
            config = root / 'attestation-signer.toml'
            original = '[rotation_policy]\nallowed_next_bridge_script_hashes = []\n'
            config.write_text(original)
            item = envelope()
            (root / 'proposal.json').write_text(json.dumps(item))
            (root / 'server.py').write_text(SERVER.replace(KEYS[0], KEYS[3]))
            try:
                self.run_command(['docker', 'run', '-d', '--name', name,
                                  '--mount', f'type=bind,src={root},dst=/fixture,readonly',
                                  '--mount', f'type=bind,src={config},dst=/etc/signer.toml,readonly',
                                  IMAGE, 'python', '/fixture/server.py', '-c', '/etc/signer.toml'])
                time.sleep(1)
                before = self.run_command(['docker', 'inspect', '--format', '{{.State.StartedAt}}', name]).stdout
                args = ['bash', str(WRAPPER), 'ready', str(root / 'proposal.json'),
                        '--expected-sha256', item['sha256'], '--current-key-hash', item['proposal']['current']['keyHash'],
                        '--config', str(config), '--container', name, '--signer-public-key', KEYS[3],
                        '--transport-public-key', KEYS[10], '--acknowledge-tso-connected']
                self.run_command(args)
                receipt = json.loads((root / ('rotation-readiness-' + item['sha256'] + '.json')).read_text())
                self.assertEqual(receipt['signerAttestationPubkey'], KEYS[3])
                self.assertTrue(receipt['tsoConnected'])
                self.assertEqual(config.read_text(), original)
                after = self.run_command(['docker', 'inspect', '--format', '{{.State.StartedAt}}', name]).stdout
                self.assertEqual(before, after)
            finally:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)

    def test_restart_bound_config_and_emit_receipt(self):
        name = 'sdk-rotation-test-' + uuid.uuid4().hex[:12]
        with tempfile.TemporaryDirectory(prefix='sdk-rotation-') as folder:
            root = Path(folder)
            config = root / 'attestation-signer.toml'
            config.write_text('[rotation_policy]\nallowed_next_bridge_script_hashes = []\nallowed_next_sequencer_signers = []\n')
            item = envelope()
            (root / 'proposal.json').write_text(json.dumps(item))
            (root / 'server.py').write_text(SERVER)
            alias = root / 'operator-alias'
            alias.symlink_to(root, target_is_directory=True)
            mounted_config = alias / config.name
            try:
                self.run_command(['docker', 'run', '-d', '--name', name,
                                  '--mount', f'type=bind,src={root},dst=/fixture,readonly',
                                  '--mount', f'type=bind,src={mounted_config},dst=/etc/signer.toml,readonly',
                                  IMAGE, 'python', '/fixture/server.py', '-c', '/etc/signer.toml'])
                time.sleep(1)
                before = config.stat().st_ino
                args = ['bash', str(WRAPPER), 'approve', str(root / 'proposal.json'),
                        '--expected-sha256', item['sha256'], '--current-key-hash', item['proposal']['current']['keyHash'],
                        '--config', str(config), '--container', name, '--signer-public-key', KEYS[0]]
                self.run_command(args)
                self.assertEqual(before, config.stat().st_ino)
                receipt = json.loads((root / ('rotation-approval-' + item['sha256'] + '.json')).read_text())
                self.assertEqual(receipt['signerAttestationPubkey'], KEYS[0])
                self.assertEqual(receipt['targetKeyHash'], item['proposal']['target']['keyHash'])
                self.assertEqual(len(list(root.glob('*.before-rotation-*'))), 1)
                # Same proposal retry keeps policy and backup unchanged.
                self.run_command(args)
                self.assertEqual(len(list(root.glob('*.before-rotation-*'))), 1)
            finally:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
