"""Check isolation and beta.6's shared API/metrics listener with rendered charts."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("tso-service", "withdrawal-processor")
MONITOR = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "monitoring"}}}


class NetworkPolicyTests(unittest.TestCase):
    def render(self, service, overlay=None, example=True):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overlay.yaml"
            path.write_text(yaml.safe_dump(overlay or {}))
            cmd = ["helm", "template", "review", str(ROOT / "charts" / service)]
            if example:
                cmd += ["-f", str(ROOT / "examples/values" / f"{service}-production.yaml")]
            cmd += ["-f", str(path)]
            return subprocess.run(cmd, capture_output=True, text=True)

    def documents(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return [d for d in yaml.safe_load_all(result.stdout) if d]

    def test_default_and_example_require_explicit_opt_in(self):
        for service in SERVICES:
            for example in (False, True):
                with self.subTest(service=service, example=example):
                    docs = self.documents(self.render(service, example=example))
                    self.assertFalse(any(d["kind"] == "NetworkPolicy" for d in docs))

    def test_monitoring_uses_the_beta6_api_port(self):
        for service in SERVICES:
            with self.subTest(service=service):
                docs = self.documents(self.render(service, {"networkPolicy": {
                    "enabled": True, "allowFrom": {"monitoring": [MONITOR]}}}))
                policy = next(d for d in docs if d["kind"] == "NetworkPolicy")
                rule = policy["spec"]["ingress"][0]
                self.assertIn(MONITOR, rule["from"])
                self.assertEqual(rule["ports"], [{"protocol": "TCP", "port": 3000}])
                workload = next(d for d in docs if d["kind"] in ("StatefulSet", "Deployment"))
                labels = workload["spec"]["template"]["metadata"]["labels"]
                for key, value in policy["spec"]["podSelector"]["matchLabels"].items():
                    self.assertEqual(labels[key], value)
                values = yaml.safe_load((ROOT / "examples/values" / f"{service}-production.yaml").read_text())
                self.assertNotIn("metrics", values["service"]["main"]["ports"])
                self.assertFalse(any("METRICS_PORT" in e["name"] for e in values["env"]))
                for monitor in values["serviceMonitor"].values():
                    self.assertTrue(all(e["port"] == "http" for e in monitor["endpoints"]))

    def test_required_api_peers_fail_closed(self):
        for service, keys in [("tso-service", ["withdrawalProcessor", "signers"]),
                              ("withdrawal-processor", ["tso"])]:
            for key in keys:
                with self.subTest(service=service, peer=key):
                    result = self.render(service, {"networkPolicy": {
                        "enabled": True, "allowFrom": {key: []}}})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"networkPolicy.allowFrom.{key}", result.stderr)

    def test_proof_work_port_is_separate_and_opt_in(self):
        for enabled in (False, True):
            peers = [{"podSelector": {"matchLabels": {"app": "coordinator"}}}] if enabled else []
            docs = self.documents(self.render("withdrawal-processor", {"networkPolicy": {
                "enabled": True, "allowFrom": {"proofCoordinator": peers}}}))
            policy = next(d for d in docs if d["kind"] == "NetworkPolicy")
            rules = policy["spec"]["ingress"]
            self.assertEqual(len(rules), 2 if enabled else 1)
            if enabled:
                self.assertEqual(rules[1], {"from": peers, "ports": [{"protocol": "TCP", "port": 9300}]})


if __name__ == "__main__":
    unittest.main()
