"""Render beta.6 signer transport and public edge contracts."""
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
# Public generator point, never signing material.
PUBLIC_KEY = "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"


def render(service, overlay=None):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "overlay.yaml"
        path.write_text(yaml.safe_dump(overlay or {}))
        return subprocess.run([
            "helm", "template", "review", str(ROOT / "charts" / service),
            "-f", str(ROOT / "examples/values" / f"{service}-production.yaml"),
            "-f", str(path),
        ], capture_output=True, text=True)


class Beta6CompatibilityTests(unittest.TestCase):
    def test_partner_compose_publishes_only_loopback_ports(self):
        compose = yaml.safe_load((ROOT / "partner-kit/attestation-signer/docker-compose/docker-compose.yml").read_text())
        signer = compose["services"]["attestation-signer"]
        for port in signer["ports"]:
            self.assertTrue(port.startswith("127.0.0.1:"), "Partner port exposed beyond loopback")
        self.assertIn("127.0.0.1:4040:4040", signer["ports"])
        self.assertIn("127.0.0.1:9100:9100", signer["ports"])

    def documents(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    def test_push_and_pull_signers_render_native_beta6_fields(self):
        push = {"network": "testnet", "roles": ["Correctness"],
                "uri": "http://cubesigner-signer:3000", "delivery": "push"}
        pull = {"network": "testnet", "roles": ["Attestation"], "delivery": "pull",
                "publicKeyOverride": PUBLIC_KEY, "transportPubkey": PUBLIC_KEY,
                "signatureMode": "ecdsa"}
        docs = self.documents(render("withdrawal-processor", {"tsoSigners": [push, pull]}))
        config = next(doc["data"]["signers.toml"] for doc in docs
                      if doc["kind"] == "ConfigMap" and "signers.toml" in (doc.get("data") or {}))
        signers = tomllib.loads(config)["tso_signers"]
        self.assertEqual(signers[0], push)
        self.assertEqual(signers[1], {"network": "testnet", "roles": ["Attestation"],
                         "delivery": "pull", "public_key_override": PUBLIC_KEY,
                         "transport_pubkey": PUBLIC_KEY, "signature_mode": "ecdsa"})

    def test_invalid_signer_migrations_fail_during_render(self):
        base = {"network": "testnet", "roles": ["Correctness"], "uri": "http://signer:3000"}
        cases = [({**base, "role": "Correctness"}, "role is retired"),
                 ({**base, "roles": []}, "exactly one role"),
                 ({**base, "roles": ["Correctness", "Attestation"]}, "exactly one role"),
                 ({**base, "roles": "Correctness"}, "must be a list"),
                 ({**base, "roles": ["unknown"]}, "Correctness or Attestation"),
                 ({**base, "delivery": "poll"}, "push or pull"),
                 ({**base, "delivery": "pull"}, "pull tsoSigner needs"),
                 ({**base, "uri": None}, "push tsoSigner needs uri")]
        for signer, message in cases:
            with self.subTest(message=message):
                result = render("withdrawal-processor", {"tsoSigners": [signer]})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_tso_edge_exposes_only_health_and_signed_routes(self):
        docs = self.documents(render("tso-service"))
        ingress = next(d for d in docs if d["kind"] == "Ingress")
        paths = ingress["spec"]["rules"][0]["http"]["paths"]
        self.assertEqual([(p["path"], p["pathType"]) for p in paths],
                         [("/health", "Exact"), ("/signer", "Prefix")])
        self.assertEqual(ingress["spec"]["ingressClassName"], "alb")
        self.assertNotIn("alb.ingress.kubernetes.io/group.name", ingress["metadata"]["annotations"])

    def test_edge_peer_is_scoped_to_api_port(self):
        edge = {"ipBlock": {"cidr": "192.0.2.0/24"}}
        docs = self.documents(render("tso-service", {"networkPolicy": {
            "enabled": True, "allowFrom": {"edge": [edge]}}}))
        policy = next(d for d in docs if d["kind"] == "NetworkPolicy")
        self.assertEqual(len(policy["spec"]["ingress"]), 1)
        rule = policy["spec"]["ingress"][0]
        self.assertIn(edge, rule["from"])
        self.assertEqual(rule["ports"], [{"protocol": "TCP", "port": 3000}])

    def test_coordinator_has_its_own_alb_and_request_timeout(self):
        docs = self.documents(render("proof-coordinator", {"proofCoordinator": {
            "config": {"existingConfigMap": "review-coordinator-config"}},
            "ingress": {"main": {"enabled": True}}}))
        ingress = next(d for d in docs if d["kind"] == "Ingress")
        self.assertEqual(ingress["spec"]["ingressClassName"], "alb")
        annotations = ingress["metadata"]["annotations"]
        self.assertNotIn("alb.ingress.kubernetes.io/group.name", annotations)
        self.assertIn("idle_timeout.timeout_seconds=120",
                      annotations["alb.ingress.kubernetes.io/load-balancer-attributes"])


if __name__ == "__main__":
    unittest.main()
