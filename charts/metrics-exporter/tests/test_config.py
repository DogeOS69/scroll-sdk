"""Regression checks for retiring the rollup poller during Helm upgrades."""

from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
EXAMPLE = CHART.parents[1] / "examples/values/metrics-exporter-production.yaml"


def render(overrides=None):
    with tempfile.TemporaryDirectory(prefix="metrics-exporter-test-") as directory:
        values = Path(directory) / "values.yaml"
        values.write_text(yaml.safe_dump(overrides or {}))
        result = subprocess.check_output([
            "helm", "template", "metrics-exporter", str(CHART),
            "-f", str(EXAMPLE), "-f", str(values),
        ], text=True)
    docs = [doc for doc in yaml.safe_load_all(result) if doc]
    config = next(doc for doc in docs if doc["kind"] == "ConfigMap")
    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    return yaml.safe_load(config["data"]["config.yml"]), deployment


class ConfigTests(unittest.TestCase):
    def test_retained_rollup_values_cannot_restore_the_retired_poller(self):
        original, _ = render()
        retained, _ = render({"metricsConfig": {"rollup": {
            "url": "http://rollup-explorer-backend", "name": "legacy", "prefix": "old",
        }}})
        self.assertEqual(retained, original)
        self.assertNotIn("rollup_last_batch_index", yaml.safe_dump(retained))
        self.assertNotIn("last_batch_indexes", yaml.safe_dump(retained))

    def test_active_modules_keep_their_rpc_metrics_and_authentication(self):
        config, deployment = render({"metricsConfig": {"dogeos": {
            "L2_TX_FEE_VAULT_ADDR": "0x" + "11" * 20,
            "L2_BRIDGE_FEE_RECIPIENT_ADDR": "0x" + "22" * 20,
        }}})
        self.assertEqual(set(config["modules"]), {
            "l1-block", "dogeos-l2-tx-fee-vault", "dogeos-l2-bridge-fee-recipient",
            "dogecoin-chaininfo", "dogecoin-info", "dogecoin-mempool",
            "dogecoin-nettotals", "dogecoin-networkhashps",
        })
        self.assertEqual(sum(len(module["metrics"]) for module in config["modules"].values()), 14)
        self.assertEqual(config["modules"]["dogecoin-chaininfo"]["headers"], {
            "Authorization": "Basic ${env.DOGECOIN_RPC_TOKEN}",
        })
        self.assertEqual(config["modules"]["dogecoin-chaininfo"]["metrics"][0]["name"],
                         "dogecoin_chain_block_height")
        self.assertEqual(config["modules"]["dogeos-l2-tx-fee-vault"]["metrics"][0]["name"],
                         "dogeos_l2_tx_fee_vault_balance")
        self.assertEqual(deployment["spec"]["template"]["spec"]["containers"][0]["image"],
                         "ghcr.io/unifralabs/metrics-exporter:v0.1.3")

    def test_configuration_changes_trigger_rollout_and_preserve_pod_annotations(self):
        _, original = render({"podAnnotations": {"example.com/owner": "ops"}})
        config, updated = render({"metricsConfig": {"dogecoin": {"url": "http://new-dogecoin:44555"}},
                                  "podAnnotations": {"example.com/owner": "ops"}})
        original_annotations = original["spec"]["template"]["metadata"]["annotations"]
        updated_annotations = updated["spec"]["template"]["metadata"]["annotations"]
        self.assertNotEqual(original_annotations["checksum/metrics-exporter-config"],
                            updated_annotations["checksum/metrics-exporter-config"])
        self.assertEqual(updated_annotations["example.com/owner"], "ops")
        self.assertEqual(config["modules"]["dogecoin-chaininfo"]["url"], "http://new-dogecoin:44555")
        _, repeated = render({"podAnnotations": {"example.com/owner": "ops"}})
        self.assertEqual(original["spec"]["template"], repeated["spec"]["template"])

    def test_optional_l1_queue_and_custom_modules_remain_available(self):
        custom = {"url": "http://custom-service/height", "interval": "1m", "metrics": [
            {"name": "custom_height", "path": "{.height}", "type": "gauge"},
        ]}
        config, _ = render({"metricsConfig": {
            "l1Network": {"L1_MESSAGE_QUEUE_PROXY_ADDR": "0x" + "33" * 20},
            "modules": {"custom-height": custom},
        }})
        self.assertIn("l1-queue", config["modules"])
        self.assertEqual(config["modules"]["custom-height"], custom)


if __name__ == "__main__":
    unittest.main()
