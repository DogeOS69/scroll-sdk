"""Check the optional dedicated metrics listener (metricsPort) in rendered charts."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENV = {
    "tso-service": "METRICS_PORT",
    "withdrawal-processor": "DOGEOS_WITHDRAWAL_METRICS_PORT",
    "cubesigner-signer": "DOGEOS_CUBESIGNER_SIGNER_METRICS_PORT",
}
POLICY_SERVICES = ("tso-service", "withdrawal-processor")
MONITOR = {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "prometheus"}}}
EDGE = {"ipBlock": {"cidr": "192.0.2.0/24"}}


class MetricsPortTests(unittest.TestCase):
    def render(self, service, overlay=None):
        values = yaml.safe_load(yaml.safe_dump(overlay or {}))
        if service == "tso-service":
            values.setdefault("networkPolicy", {}).setdefault("allowFrom", {}).setdefault("edge", [EDGE])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overlay.yaml"
            path.write_text(yaml.safe_dump(values))
            cmd = ["helm", "template", "review", str(ROOT / "charts" / service),
                   "-f", str(ROOT / "examples/values" / f"{service}-production.yaml"),
                   "-f", str(path)]
            return subprocess.run(cmd, capture_output=True, text=True)

    def documents(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return [d for d in yaml.safe_load_all(result.stdout) if d]

    @staticmethod
    def kind(docs, kind):
        return [d for d in docs if d["kind"] == kind]

    def container(self, docs):
        workload = next(d for d in docs if d["kind"] in ("StatefulSet", "Deployment"))
        return workload["spec"]["template"]["spec"]["containers"][0]

    def test_examples_keep_metrics_on_the_api_port(self):
        for service, env in ENV.items():
            with self.subTest(service=service):
                values = yaml.safe_load((ROOT / "examples/values" / f"{service}-production.yaml").read_text())
                self.assertIn("metricsPort", values)
                self.assertIsNone(values["metricsPort"])
                docs = self.documents(self.render(service))
                container = self.container(docs)
                self.assertNotIn(env, [e["name"] for e in container.get("env", [])])
                self.assertNotIn("metrics", [p["name"] for p in container["ports"]])
                for policy in self.kind(docs, "NetworkPolicy"):
                    self.assertEqual(len([r for r in policy["spec"]["ingress"]
                                          if MONITOR in r["from"]]), 1)

    def test_metrics_port_wires_env_service_and_service_monitor(self):
        for service, env in ENV.items():
            with self.subTest(service=service):
                docs = self.documents(self.render(service, {
                    "metricsPort": 9100, "serviceMonitor": {"main": {"enabled": True}}}))
                container = self.container(docs)
                self.assertIn({"name": env, "value": "9100"}, container["env"])
                self.assertIn({"name": "metrics", "containerPort": 9100, "protocol": "TCP"},
                              container["ports"])
                service_ports = next(d for d in self.kind(docs, "Service")
                                     if d["metadata"]["name"] == service)["spec"]["ports"]
                self.assertIn({"name": "metrics", "port": 9100, "targetPort": 9100, "protocol": "TCP"},
                              service_ports)
                monitors = self.kind(docs, "ServiceMonitor")
                self.assertTrue(monitors)
                for monitor in monitors:
                    self.assertTrue(all(e["port"] == "metrics" for e in monitor["spec"]["endpoints"]))
                # Probes stay on the API port.
                self.assertEqual(container["livenessProbe"]["httpGet"]["port"], "http")

    def test_monitoring_peers_move_to_the_metrics_port(self):
        for service in POLICY_SERVICES:
            with self.subTest(service=service):
                docs = self.documents(self.render(service, {
                    "metricsPort": 9100, "networkPolicy": {"allowFrom": {"monitoring": [MONITOR]}}}))
                rules = self.kind(docs, "NetworkPolicy")[0]["spec"]["ingress"]
                self.assertNotIn(MONITOR, rules[0]["from"])
                self.assertEqual(rules[0]["ports"], [{"protocol": "TCP", "port": 3000}])
                self.assertEqual(rules[-1], {"from": [MONITOR], "ports": [{"protocol": "TCP", "port": 9100}]})

    def test_metrics_port_without_monitoring_peers_opens_nothing(self):
        for service in POLICY_SERVICES:
            with self.subTest(service=service):
                docs = self.documents(self.render(service, {
                    "metricsPort": 9100, "networkPolicy": {"allowFrom": {"monitoring": []}}}))
                rules = self.kind(docs, "NetworkPolicy")[0]["spec"]["ingress"]
                self.assertFalse(any(p["port"] == 9100 for r in rules for p in r["ports"]))

    def test_invalid_metrics_ports_fail(self):
        cases = [(service, port) for service in ENV for port in (0, 3000, 70000)]
        cases.append(("withdrawal-processor", 9300))
        for service, port in cases:
            with self.subTest(service=service, port=port):
                result = self.render(service, {"metricsPort": port})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("metricsPort", result.stderr)

    def test_explicit_env_conflicts_with_metrics_port(self):
        for service, env in ENV.items():
            with self.subTest(service=service):
                values = yaml.safe_load((ROOT / "examples/values" / f"{service}-production.yaml").read_text())
                result = self.render(service, {
                    "metricsPort": 9100, "env": values["env"] + [{"name": env, "value": "9100"}]})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"set metricsPort instead of env {env}", result.stderr)


if __name__ == "__main__":
    unittest.main()
