"""Exercise the rendered alert against Loki 3.1.1 with synthetic incident logs.

Run with SCROLL_MONITOR_LOKI_TEST=1. Uses an isolated, disposable local container;
never uses the cluster, its data, or an externally configured Loki URL.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from test_monitoring_templates import grafana_rules, render


# (case, service, line, expected count). Fixtures reproduce the observed formats
# without production addresses, credentials, transaction payloads or pod names.
CASES = [
    ("grafana_query", "grafana", 'logger=tsdb.loki level=info msg="Response received from loki" query="error|panicked" statusCode=200', 0),
    ("loki_query", "loki", 'level=info msg="executing query" query="level=error or panicked"', 0),
    ("quoted_level", "grafana", 'logger=context msg="nested level=error" level=info', 0),
    ("json_query", "blockscout", '{"severity":"info","message":"query contains error and panicked"}', 0),
    ("json_nested_level", "blockscout", json.dumps({"message": 'nested "level":"error"', "severity": "info"}), 0),
    ("json_nested_object", "blockscout", '{"severity":"info","metadata":{"level":"error"}}', 0),
    ("recovery", "proof-coordinator", '\x1b[2m2026-09-09T03:30:00Z\x1b[0m \x1b[32mINFO\x1b[0m recovered last_error="task panicked"', 0),
    ("peer_warning", "l2-reth-rpc", 'ts=2026-09-09T03:30:00Z level=warn message="peer lookup error"', 0),
    ("access_url", "frontends", '127.0.0.1 - - [09/Sep/2026:03:30:00 +0000] "GET /alert-error.svg HTTP/1.1" 200 798', 0),
    ("access_parameter", "frontends", '127.0.0.1 - - [09/Sep/2026:03:30:00 +0000] "GET /logo.png?ignore-error,1 HTTP/1.1" 200 798', 0),
    ("smtp", "grafana", 'logger=ngalert level=error msg="Notify for alerts failed" err="SMTP not configured"', 1),
    ("json_error", "blockscout", '{"time":"2026-09-09T03:30:00Z","severity":"error","message":"Not found"}', 1),
    ("json_level", "application", '{"message":"failed","level":"ERROR"}', 1),
    ("json_after_metadata", "application", '{"metadata":{"request":"test"},"level":"error"}', 1),
    ("logfmt_after_message", "application", 'msg="request failed" level="ERROR"', 1),
    ("logfmt_escaped_message", "application", r'msg="escaped \"quote\"" level=error', 1),
    ("fatal", "application", 'time=2026-09-09T03:30:00Z level=fatal msg="exiting"', 1),
    ("panic_level", "application", '{"level":"panic","message":"failed"}', 1),
    ("rust_error", "withdrawal-processor", '\x1b[2m2026-09-09T03:30:00.123Z\x1b[0m \x1b[31mERROR\x1b[0m indexer: RPC request failed', 1),
    ("geth_error", "l2-bootnode", 'ERROR[09-09|03:30:00.123] Error verifying headers', 1),
    ("plain_error", "blockscout-sc-verifier", 'Error: solidity fetcher initialization', 1),
    ("node_error", "blockscout-frontend", ' ⨯ Error: Required param not provided', 1),
    ("type_error", "application", 'TypeError: missing argument', 1),
    ("rust_panic", "proof-coordinator", "thread 'tokio-rt-worker' (21) panicked at src/block.rs:174:41:", 1),
    ("rust_panic_old", "proof-coordinator", "thread 'main' panicked at src/main.rs:12:5:", 1),
    ("go_panic", "application", 'panic: runtime error: invalid memory address', 1),
    ("retired_service", "rollup-explorer-backend", 'level=error msg="failed"', 0),
    ("retired_module", "metrics-exporter", 'time=2026-09-09T03:30:00Z level=ERROR msg="Http call failed" module=rollup-last-batch-indexes error="no such host"', 0),
    ("retired_module_quoted", "metrics-exporter", 'level=ERROR module="rollup-last-batch-indexes" msg="Http call failed"', 0),
    ("active_exporter_module", "metrics-exporter", 'level=ERROR module=dogecoin-chaininfo msg="Http call failed"', 1),
    ("exporter_no_module", "metrics-exporter", 'level=ERROR msg="exporter failed"', 1),
    ("retired_module_other_service", "application", 'level=ERROR module=rollup-last-batch-indexes msg="failed"', 0),
    ("quoted_module", "metrics-exporter", 'level=ERROR module=dogecoin-chaininfo msg="module=rollup-last-batch-indexes"', 1),
]


@unittest.skipUnless(os.environ.get("SCROLL_MONITOR_LOKI_TEST") == "1",
                     "set SCROLL_MONITOR_LOKI_TEST=1 to run local Loki integration")
class LogAlertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="scroll-monitor-loki-")
        cls.addClassCleanup(cls.directory.cleanup)
        config = Path(cls.directory.name) / "loki.yaml"
        config.write_text("""auth_enabled: false
server:
  http_listen_port: 3100
common:
  path_prefix: /tmp/loki
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h
analytics:
  reporting_enabled: false
""")
        Path(cls.directory.name).chmod(0o755)
        name = "scroll-monitor-log-test-" + uuid4().hex[:10]
        cls.addClassCleanup(lambda: subprocess.run(
            ["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False))
        subprocess.run([
            "docker", "run", "--rm", "-d", "--name", name,
            "-p", "127.0.0.1::3100", "-v", f"{config}:/etc/loki/test.yaml:ro",
            "grafana/loki:3.1.1", "-config.file=/etc/loki/test.yaml",
        ], check=True, stdout=subprocess.DEVNULL)
        port = subprocess.check_output(["docker", "port", name, "3100"], text=True).strip()
        cls.url = "http://" + port
        for _ in range(60):
            try:
                with urlopen(cls.url + "/ready", timeout=2):
                    break
            except (URLError, TimeoutError, ConnectionError):
                time.sleep(1)
        else:
            raise RuntimeError("Disposable test Loki did not become ready")

    @classmethod
    def api(cls, path, body=None, **params):
        request = Request(cls.url + path + ("?" + urlencode(params) if params else ""),
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else None
        except HTTPError as error:
            raise AssertionError(error.read().decode()) from error

    def test_rendered_rule_counts_real_errors_without_incident_false_positives(self):
        timestamp = time.time_ns() - 10_000_000_000
        streams = [{"stream": {"namespace": "monitoring", "service": service,
                               "pod": case, "container": service},
                    "values": [[str(timestamp), line]]}
                   for case, service, line, _ in CASES]
        self.api("/loki/api/v1/push", {"streams": streams})
        rule = grafana_rules(render())["ServiceErrorOrPanickedLogs"]
        result = self.api("/loki/api/v1/query", query=rule["expr"])
        actual = {entry["metric"]["pod"]: int(float(entry["value"][1]))
                  for entry in result["data"]["result"]}
        for case, _, _, expected in CASES:
            with self.subTest(case=case):
                self.assertEqual(actual.get(case, 0), expected)
        self.assertEqual(sum(actual.values()), sum(case[3] for case in CASES))
        for entry in result["data"]["result"]:
            self.assertEqual(set(entry["metric"]), {"namespace", "service", "pod", "container"})
        # Once logs leave the five-minute window, the alert must clear.
        expired = self.api("/loki/api/v1/query", query=rule["expr"],
                           time=str(timestamp + 360_000_000_000))
        self.assertEqual(expired["data"]["result"], [])


if __name__ == "__main__":
    unittest.main()
