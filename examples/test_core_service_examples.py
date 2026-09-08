#!/usr/bin/env python3
"""Local-only example contract checks (Python 3.11+, PyYAML and Helm)."""

from pathlib import Path
import runpy
import subprocess
import tomllib
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "arn:aws:eks:us-east-1:074120976575:cluster/dogeos-devnet-cluster"
SERVICES = (
    "l1-interface", "withdrawal-processor", "eth-da-submitter", "fee-oracle",
    "proof-coordinator", "tso-service", "cubesigner-signer",
)


def example(service):
    return ROOT / "examples/values" / f"{service}-production.yaml"


def load(path):
    return yaml.safe_load(path.read_text())


class CoreServiceExamples(unittest.TestCase):
    def test_all_seven_explicit_runtime_contracts(self):
        contract = runpy.run_path(str(ROOT / ".github/scripts/validate_production_values.py"))
        # Extend coverage locally without changing the chart CI script.
        for service in ("fee-oracle", "tso-service"):
            contract["REQUIRED_TOP_LEVEL"][service] = {
                "global", "image", "command", "args", "service", "probes",
                "env", "persistence", "resources", "serviceMonitor", "ingress",
            }
            contract["SHARED_CONFIG_FILES"][service] = {}
        for service in SERVICES:
            with self.subTest(service=service):
                defaults = load(ROOT / "charts" / service / "values.yaml")
                self.assertEqual(contract["validate_file"](service, example(service), defaults), [])

    def test_proof_token_has_independent_ownership(self):
        wp = load(example("withdrawal-processor"))
        ordinary = wp["externalSecrets"]["withdrawal-processor-secret-env"]["data"]
        self.assertEqual(len(ordinary), 4)
        self.assertTrue(all(item["remoteRef"]["key"] == "dogeos/withdrawal-processor" for item in ordinary))
        token = wp["externalSecrets"]["withdrawal-proof-token"]["data"]
        self.assertEqual(len(token), 1)
        self.assertEqual(token[0]["secretKey"], "DOGEOS_WITHDRAWAL_PROOF_WORK_API__AUTH__BEARER_TOKEN")
        self.assertIn({"secretRef": {"name": "withdrawal-proof-token"}}, wp["envFrom"])
        pc = load(example("proof-coordinator"))
        pc_token = next(item for item in pc["externalSecrets"]["secrets"]["data"] if item["secretKey"] == "proof-work-token")
        self.assertEqual(token[0]["remoteRef"], pc_token["remoteRef"])
        self.assertFalse(any(item["name"].startswith("DOGEOS_PROOF_COORDINATOR_") for item in pc["env"]))

    def test_regions_and_native_sqlite_defaults(self):
        for service in SERVICES:
            for secret in load(example(service)).get("externalSecrets", {}).values():
                if secret.get("provider") == "aws":
                    self.assertTrue(secret.get("secretRegion"), service)
        native = tomllib.loads((ROOT / "examples/withdrawal-processor/WithdrawalProcessor.toml").read_text())
        self.assertEqual(native["database_url"], "sqlite:///app/data/withdrawal_processor.sqlite")
        self.assertEqual(native["broadcast_backoff_base_ms"], 5000)
        self.assertEqual(native["broadcast_backoff_cap_ms"], 300000)

    def test_reth_preserves_l2_rpc_service_alias(self):
        reth = load(example("l2-reth-rpc"))
        self.assertEqual(reth["service"]["main"]["fullname"], "l2-rpc")
        for service, prefix in (("fee-oracle", "DOGEOS_FEE_ORACLE"), ("eth-da-submitter", "DOGEOS_ETH_DA_SUBMITTER")):
            self.assertEqual(load(example(service))["configMaps"]["env"]["data"][prefix + "_L2__RPC_URL"], "http://l2-rpc:8545")

    def test_helm_rendered_workload_contracts(self):
        for service in SERVICES:
            with self.subTest(service=service):
                command = ["helm", "--kube-context", CONTEXT, "template", service,
                           str(ROOT / "charts" / service), "-f", str(example(service))]
                if service == "proof-coordinator":
                    # Test chart wiring only; no fabricated runtime proof config.
                    command += ["--set-string", "proofCoordinator.config.existingConfigMap=review-proof-coordinator-config"]
                rendered = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
                docs = [doc for doc in yaml.safe_load_all(rendered.stdout) if doc]
                workload = next(doc for doc in docs if doc["kind"] in ("Deployment", "StatefulSet"))
                pod = workload["spec"]["template"]["spec"]
                container = pod["containers"][0]
                ports = {port["name"] for port in container["ports"]}
                for probe in ("livenessProbe", "readinessProbe", "startupProbe"):
                    self.assertIn(container[probe]["httpGet"]["port"], ports)
                if service in ("fee-oracle", "tso-service"):
                    pvc = next(doc for doc in docs if doc["kind"] == "PersistentVolumeClaim")
                    self.assertEqual(pvc["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
                    monitor = next(doc for doc in docs if doc["kind"] == "ServiceMonitor")
                    self.assertEqual(monitor["spec"]["endpoints"][0]["path"], "/metrics")
                if service == "fee-oracle":
                    self.assertEqual(pod["serviceAccountName"], "default")
                if service == "withdrawal-processor":
                    secrets = {doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "ExternalSecret"}
                    self.assertEqual(len(secrets["withdrawal-processor-secret-env"]["spec"]["data"]), 4)
                    self.assertEqual(len(secrets["withdrawal-proof-token"]["spec"]["data"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
