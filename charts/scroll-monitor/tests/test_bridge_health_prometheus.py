import copy
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bridge_health_prometheus", CHART / "scripts/bridge-health-prometheus.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def fixture(instance="10.0.0.1:8080"):
    # Emitted by the actual Rust collector's signing_metrics_wire_contract_fixture test.
    rows = [{"metric": {"__name__": "up", "namespace": "bridge", "job": "tso-service", "instance": instance}, "value": [1000, "1"]}]
    for line in (CHART / "tests/fixtures/tso-signing-v1.prom").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r'([a-z_]+)(?:\{(.*)\})? ([0-9.e+-]+)', line)
        name, labels, value = match.groups()
        if name not in adapter.NAMES:
            continue
        row = {"__name__": name, "namespace": "bridge", "job": "tso-service", "instance": instance}
        row.update(dict(re.findall(r'([a-z_]+)="([^"]*)"', labels or "")))
        rows.append({"metric": row, "value": [1000, value]})
    return {"status": "success", "data": {"resultType": "vector", "result": rows}}


def cfg(**updates):
    return adapter.config({"prometheusUrl": "http://prometheus:9090", "environment": "devnet", "chainId": "291",
                           "namespace": "bridge", "job": "tso-service", "expectedTargets": 1, **updates})


class AdapterTests(unittest.TestCase):
    def get(self, payload, **options):
        return adapter.collect(cfg(**options), now=1000, fetch=lambda _: payload)

    def test_real_rust_wire_fixture_is_evidence_not_global_outage(self):
        result = self.get(fixture())
        self.assertTrue(result["observationValid"])
        self.assertTrue(result["coverageComplete"])
        self.assertEqual(result["businessStatus"], "unknown")
        self.assertEqual(result["coverage"], "tso_signing_only")
        self.assertEqual(result["validUntil"], 1120)
        self.assertEqual(result["sources"][0]["roles"]["attestation"]["transactions"], {"satisfied": 0, "pending": 1, "unreachable": 1})

    def test_missing_each_metric_invalidates_instead_of_zero_fill(self):
        original = fixture()
        for index in range(len(original["data"]["result"])):
            payload = copy.deepcopy(original)
            del payload["data"]["result"][index]
            with self.subTest(index=index):
                self.assertFalse(self.get(payload)["observationValid"])

    def test_duplicate_series_is_not_summed(self):
        payload = fixture()
        payload["data"]["result"].append(copy.deepcopy(payload["data"]["result"][2]))
        self.assertEqual(self.get(payload)["reason"], "duplicate_series")

    def test_target_inventory_and_scopes_are_explicit(self):
        self.assertFalse(self.get(fixture(), expectedTargets=2)["observationValid"])
        payload = fixture()
        payload["data"]["result"] += fixture("10.0.0.2:8080")["data"]["result"]
        self.assertFalse(self.get(payload)["observationValid"])
        self.assertEqual(len(self.get(payload, expectedTargets=2)["sources"]), 2)
        payload["data"]["result"][0]["metric"]["namespace"] = "other-chain"
        self.assertEqual(self.get(payload, expectedTargets=2)["reason"], "wrong_scope")

    def test_invalid_stale_future_schema_and_inconsistent_counts(self):
        cases = [("snapshot_valid", "0", "invalid_snapshot"), ("snapshot_schema_version", "2", "unsupported_schema"),
                 ("snapshot_timestamp_seconds", "880", "stale_snapshot"), ("snapshot_timestamp_seconds", "1006", "stale_snapshot"),
                 ("active_transactions", "3", "inconsistent_counts"), ("active_transactions", "1.5", "invalid_count"),
                 ("active_transactions", "NaN", "invalid_number"), ("active_transactions", "-1", "invalid_number"),
                 ("observer_start_timestamp_seconds", "1006", "stale_snapshot")]
        for name, value, reason in cases:
            payload = fixture()
            next(row for row in payload["data"]["result"] if row["metric"]["__name__"] == adapter.PREFIX + name)["value"][1] = value
            with self.subTest(name=name, value=value):
                self.assertEqual(self.get(payload)["reason"], reason)

    def test_old_samples_and_down_targets_are_observation_gaps(self):
        payload = fixture(); payload["data"]["result"][0]["value"] = [1000, "0"]
        result = self.get(payload)
        self.assertFalse(result["observationValid"])
        self.assertEqual(result["businessStatus"], "unknown")
        payload["data"]["result"][0]["value"] = [879, "1"]
        self.assertEqual(self.get(payload)["reason"], "stale_sample")

    def test_query_errors_warnings_bad_shape_and_network_errors_fail_closed(self):
        for payload in [{}, {"status": "error"}, {"status": "success", "warnings": ["partial"]},
                        {"status": "success", "data": {"resultType": "matrix", "result": []}},
                        {"status": "success", "data": {"resultType": "vector", "result": []}}]:
            self.assertFalse(self.get(payload)["observationValid"])
        def fail(_):
            raise OSError("private endpoint detail")
        result = adapter.collect(cfg(), now=1000, fetch=fail)
        self.assertEqual(result["reason"], "collection_failed")
        self.assertNotIn("private endpoint", json.dumps(result))

    def test_metric_labels_escape_prometheus_text(self):
        value = 'node"\\\n雪'
        self.assertEqual(adapter.metric_quote(value), '"node\\"\\\\\\n雪"')
        rendered = adapter.metrics(self.get(fixture(value)), 1000)
        self.assertIn('source_instance=' + adapter.metric_quote(value), rendered)

    def test_metric_output_expires_even_if_collection_stops(self):
        result = self.get(fixture())
        fresh = adapter.metrics(result, 1119)
        stale = adapter.metrics(result, 1120)
        self.assertIn('scroll_bridge_signing_observation_valid{environment="devnet",chain_id="291"} 1', fresh)
        self.assertIn('scroll_bridge_signing_observation_valid{environment="devnet",chain_id="291"} 0', stale)
        self.assertNotIn("quorum_transactions", stale)

    def test_unclassified_is_valid_partial_evidence_not_complete_health(self):
        payload = fixture()
        for row in payload["data"]["result"]:
            if row["metric"]["__name__"] == adapter.PREFIX + "active_transactions": row["value"][1] = "3"
            if row["metric"]["__name__"] == adapter.PREFIX + "unclassified_transactions": row["value"][1] = "1"
        result = self.get(payload)
        self.assertTrue(result["observationValid"])
        self.assertFalse(result["coverageComplete"])
        self.assertEqual(result["businessStatus"], "unknown")

    def test_real_http_collection_uses_only_get_and_rejects_redirects(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                if self.path.startswith("/redirect/"):
                    self.send_response(302)
                    self.send_header("Location", "/must-not-be-followed")
                    self.end_headers()
                    return
                body = json.dumps(fixture()).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            configuration = cfg(prometheusUrl=url)
            result = adapter.collect(configuration, now=1000)
            self.assertTrue(result["observationValid"])
            request = urlsplit(calls[0])
            self.assertEqual(request.path, "/api/v1/query")
            self.assertEqual(parse_qs(request.query)["query"], [adapter.query(configuration)])
            result = adapter.collect(cfg(prometheusUrl=url + "/redirect"), now=1000)
            self.assertFalse(result["observationValid"])
            self.assertEqual(len(calls), 2, "redirect must not contact another endpoint")
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_query_escaping_and_config_validation(self):
        query = adapter.query(cfg(job='tso"} or up{job="other'))
        self.assertIn('job="tso\\\"} or up{job=\\\"other"', query)
        for updates in ({"expectedTargets": 0}, {"expectedTargets": True}, {"environment": ""},
                        {"chainId": "abc"}, {"intervalSeconds": 5, "timeoutSeconds": 5},
                        {"prometheusUrl": "http://user:secret@prometheus"}, {"unexpected": 1}):
            with self.assertRaises(ValueError): cfg(**updates)


class TemplateTests(unittest.TestCase):
    def render(self, values):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as file:
            yaml.safe_dump(values, file); file.flush()
            return subprocess.run(["helm", "template", "monitor", str(CHART), "--namespace", "bridge", "-f", file.name], capture_output=True, text=True)

    def test_default_off_and_explicit_source_configuration(self):
        result = self.render({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("monitor-bridge-health", result.stdout)
        result = self.render({"bridgeHealth": {"enabled": True, "environment": "devnet", "chainId": "291"}})
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc and doc.get("metadata", {}).get("name") == "monitor-bridge-health"]
        self.assertEqual({doc["kind"] for doc in docs}, {"ConfigMap", "Deployment", "Service", "ServiceMonitor"})
        cm = next(doc for doc in docs if doc["kind"] == "ConfigMap")
        generated = adapter.config(json.loads(cm["data"]["adapter.json"]))
        self.assertEqual(generated["namespace"], "bridge")
        self.assertEqual(generated["chainId"], "291")
        deploy = next(doc for doc in docs if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
        self.assertFalse(deploy["automountServiceAccountToken"])
        container = deploy["containers"][0]
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertNotIn("env", container)
        monitor = next(doc for doc in docs if doc["kind"] == "ServiceMonitor")
        self.assertEqual(monitor["metadata"]["labels"]["release"], "monitor")
        # The chart's Prometheus discovers monitors by instance-label presence.
        # A valid adapter endpoint without this label is invisible to scraping.
        prometheus = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc.get("kind") == "Prometheus")
        for requirement in prometheus["spec"]["serviceMonitorSelector"]["matchExpressions"]:
            self.assertEqual(requirement["operator"], "Exists")
            self.assertIn(requirement["key"], monitor["metadata"]["labels"])

    def test_invalid_inputs_fail_render(self):
        for patch in ({}, {"environment": "devnet"}, {"environment": "devnet", "chainId": "291", "expectedTargets": 0},
                      {"environment": "devnet", "chainId": "291", "timeoutSeconds": 30}):
            self.assertNotEqual(self.render({"bridgeHealth": {"enabled": True, **patch}}).returncode, 0)


if __name__ == "__main__":
    unittest.main()
