from functools import lru_cache
import json
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]


@lru_cache
def render(*args):
    output = subprocess.check_output([
        "helm", "template", "scroll-monitor", str(CHART), "--namespace", "monitoring", *args,
    ], text=True)
    return [doc for doc in yaml.safe_load_all(output) if doc]


def resource(docs, kind, name):
    return next(doc for doc in docs if doc["kind"] == kind and doc["metadata"]["name"] == name)


def grafana_rules(docs):
    data = resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"]
    groups = json.loads(data)["groups"]
    return {rule["alert"]: rule for group in groups for rule in group["rules"]}


class TemplateTests(unittest.TestCase):
    def test_grafana_and_prometheus_use_identical_metric_rules(self):
        native = resource(render("--set", "grafanaAlerting.enabled=false"),
                          "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
        native = {rule["alert"]: rule for group in native for rule in group["rules"]}
        grafana = grafana_rules(render())
        grafana.pop("ServiceErrorOrPanickedLogs")
        grafana = {name: rule for name, rule in grafana.items() if not rule.get("isPaused")}
        self.assertEqual(grafana, native)
        self.assertEqual(len(native), 41)

    def test_configurable_thresholds_and_quorum_are_rendered(self):
        docs = render("--set", "balanceMonitoring.feeWallet.minimumDoge=250",
                      "--set", "balanceMonitoring.ethereum.feeOracle.minimumEth=7",
                      "--set", "balanceMonitoring.ethereum.ethDaSubmitter.minimumEth=0.2",
                      "--set", "businessAlerts.requiredSignersByRole.Correctness=2")
        rules = grafana_rules(docs)
        self.assertTrue(rules["FeeWalletBalanceLow"]["expr"].endswith("< 250"))
        self.assertTrue(rules["FeeOracleAccountBalanceLow"]["expr"].endswith("< 7"))
        self.assertTrue(rules["EthDASubmitterAccountBalanceLow"]["expr"].endswith("< 0.2"))
        self.assertIn('< 2', rules["TSOCorrectnessQuorumUnavailable"]["expr"])

    def test_public_account_config_maps_to_independent_environment_variables(self):
        docs = render("--set", "balanceMonitoring.ethereum.feeOracle.address=0x" + "aa" * 20,
                      "--set", "balanceMonitoring.ethereum.ethDaSubmitter.address=0x" + "bb" * 20,
                      "--set", "balanceMonitoring.ethereum.ethDaSubmitter.rpcUrl=http://ethereum:8545",
                      "--set-string", "balanceMonitoring.ethereum.feeOracle.expectedChainId=1234")
        container = resource(docs, "Deployment", "scroll-monitor-account-balances")["spec"]["template"]["spec"]["containers"][0]
        env = {entry["name"]: entry["value"] for entry in container["env"]}
        self.assertEqual(env["SCROLL_BALANCE_FEE_ORACLE_ADDRESS"], "0x" + "aa" * 20)
        self.assertEqual(env["SCROLL_BALANCE_FEE_ORACLE_RPC_URL"], "http://l2-rpc:8545")
        self.assertEqual(env["SCROLL_BALANCE_FEE_ORACLE_EXPECTED_CHAIN_ID"], "1234")
        self.assertEqual(env["SCROLL_BALANCE_ETH_DA_SUBMITTER_RPC_URL"], "http://ethereum:8545")
        self.assertEqual(env["SCROLL_BALANCE_ETH_DA_SUBMITTER_ADDRESS"], "0x" + "bb" * 20)
        monitor = resource(docs, "ServiceMonitor", "scroll-monitor-account-balances")
        service = resource(docs, "Service", "scroll-monitor-account-balances")
        for key, value in monitor["spec"]["selector"]["matchLabels"].items():
            self.assertEqual(service["metadata"]["labels"][key], value)

    def test_secret_can_supply_empty_fields(self):
        docs = render("--set", "balanceMonitoring.exporter.envFromSecret=balance-rpc",
                      "--set", "balanceMonitoring.ethereum.feeOracle.rpcUrl=")
        container = resource(docs, "Deployment", "scroll-monitor-account-balances")["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["envFrom"], [{"secretRef": {"name": "balance-rpc"}}])
        names = [env["name"] for env in container["env"]]
        self.assertNotIn("SCROLL_BALANCE_FEE_ORACLE_ADDRESS", names)
        self.assertNotIn("SCROLL_BALANCE_FEE_ORACLE_RPC_URL", names)

    def test_exporter_and_alerts_can_be_disabled_together(self):
        docs = render("--set", "balanceMonitoring.enabled=false,businessAlerts.enabled=false,serviceAlerts.enabled=false")
        self.assertEqual(len(grafana_rules(docs)), 14)
        self.assertFalse(any(doc["metadata"]["name"] == "scroll-monitor-account-balances" for doc in docs))

    def test_external_exporter_keeps_balance_alerts(self):
        docs = render("--set", "balanceMonitoring.exporter.enabled=false")
        self.assertIn("FeeOracleAccountBalanceLow", grafana_rules(docs))
        self.assertFalse(any(doc["metadata"]["name"] == "scroll-monitor-account-balances" for doc in docs))

    def test_production_values_expose_the_same_generator_contract(self):
        charts = yaml.safe_load((CHART / "values/production.yaml").read_text())
        examples = yaml.safe_load((CHART.parents[1] / "examples/values/scroll-monitor-production.yaml").read_text())
        self.assertEqual(charts["balanceMonitoring"], examples["balanceMonitoring"])
        self.assertEqual(charts["businessAlerts"], examples["businessAlerts"])
        self.assertEqual(charts["serviceAlerts"], examples["serviceAlerts"])

    def test_new_service_rules_start_paused_without_changing_existing_rules(self):
        rules = grafana_rules(render())
        paused = {name: rule for name, rule in rules.items() if rule.get("isPaused")}
        self.assertEqual(len(paused), 107)
        self.assertEqual({r["labels"]["service"] for r in paused.values()}, {
            "withdrawal-processor", "tso-service", "proof-coordinator", "l2-reth",
            "l1-interface", "eth-da-submitter", "cubesigner-signer", "fee-oracle",
        })
        self.assertNotIn("isPaused", rules["FeeWalletBalanceLow"])
        self.assertNotIn("isPaused", rules["ProtocolStateWFTxNumberStalled"])
        self.assertEqual(len(grafana_rules(render("--set", "serviceAlerts.enabled=false"))), 42)

    def test_explicit_activation_is_equivalent_across_backends(self):
        grafana = grafana_rules(render("--set", "serviceAlerts.paused=false"))
        grafana.pop("ServiceErrorOrPanickedLogs")
        for rule in grafana.values():
            self.assertFalse(rule.pop("isPaused", False))
        native = resource(render("--set", "grafanaAlerting.enabled=false,serviceAlerts.paused=false"),
                          "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
        native = {rule["alert"]: rule for group in native for rule in group["rules"]}
        self.assertEqual(grafana, native)
        self.assertEqual(len(native), 148)

    def test_disabling_grafana_does_not_activate_paused_rules(self):
        for setting in ("grafanaAlerting.enabled=false", "grafana.enabled=false"):
            groups = resource(render("--set", setting), "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
            self.assertEqual(sum(len(group["rules"]) for group in groups), 41)
            self.assertFalse(any("isPaused" in rule for group in groups for rule in group["rules"]))


if __name__ == "__main__":
    unittest.main()
