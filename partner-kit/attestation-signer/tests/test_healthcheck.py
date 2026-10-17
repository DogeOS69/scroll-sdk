"""Run the actual Compose Bash probe against a local HTTP fixture."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import threading
import unittest

import yaml


class HealthcheckTests(unittest.TestCase):
    def test_probe_accepts_only_successful_health_response(self):
        class Handler(BaseHTTPRequestHandler):
            status = 200

            def do_GET(self):
                self.send_response(self.status if self.path == '/health' else 404)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            compose = yaml.safe_load((Path(__file__).resolve().parents[1] / 'docker-compose.yml').read_text())
            probe = compose['services']['attestation-signer']['healthcheck']['test'][1:]
            probe[-1] = probe[-1].replace('$$', '$')  # Compose interpolation.
            for status in [200, 503]:
                Handler.status = status
                result = subprocess.run(probe, env={**os.environ, 'PORT': str(server.server_port)},
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode == 0, status == 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
