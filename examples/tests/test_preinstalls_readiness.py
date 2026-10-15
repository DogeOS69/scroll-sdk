"""Exercise the rendered RPC gate against HTTP responses, including JSON-RPC errors."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class PreinstallsReadinessTest(unittest.TestCase):
    def test_rpc_readiness(self):
        for chart in ("preinstalls-deployer",):
            for first_reply in ("ready", "rpc_error", "http_error", "missing_result"):
                with self.subTest(chart=chart, first_reply=first_reply):
                    rendered = subprocess.check_output(
                        ["helm", "template", "test", str(ROOT / "charts" / chart)], text=True
                    )
                    pod = next(x for x in yaml.safe_load_all(rendered)
                               if x and x.get("kind") == "Pod"
                               and x["metadata"]["name"].endswith("-preinstalls-deploy"))
                    init = pod["spec"]["initContainers"][0]
                    script = init["args"][0]
                    requests = []

                    class Handler(http.server.BaseHTTPRequestHandler):
                        def do_POST(self):
                            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                            requests.append(request)
                            reply = ({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000}}
                                     if first_reply == "rpc_error" and len(requests) == 1
                                     else {"jsonrpc": "2.0", "id": 1, "result": "0x35fc2"})
                            if first_reply == "missing_result" and len(requests) == 1:
                                reply = {"jsonrpc": "2.0", "id": 1, "result": None}
                            self.send_response(503 if first_reply == "http_error" and len(requests) == 1 else 200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(reply).encode())

                        def do_GET(self):
                            self.send_error(405)

                        def log_message(self, *args):
                            pass

                    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        endpoint = f"http://127.0.0.1:{server.server_port}"
                        command = [*init["command"], script]
                        if os.environ.get("PREINSTALLS_READINESS_DOCKER_TEST") == "1":
                            command = [
                                "docker", "run", "--rm", "--network", "host",
                                "--entrypoint", init["command"][0],
                                "-e", f"L2_RPC_ENDPOINT={endpoint}", init["image"],
                                *init["command"][1:], script,
                            ]
                        run = subprocess.run(
                            command, capture_output=True, text=True, timeout=30,
                            env={**os.environ, "L2_RPC_ENDPOINT": endpoint},
                        )
                        self.assertEqual(run.returncode, 0, run.stderr)
                        self.assertEqual(len(requests), 1 if first_reply == "ready" else 2)
                        self.assertTrue(all(x["method"] == "eth_chainId" for x in requests))
                        self.assertIn("L2 JSON-RPC is ready.", run.stdout)
                    finally:
                        server.shutdown()
                        thread.join()
                        server.server_close()


if __name__ == "__main__":
    unittest.main()
