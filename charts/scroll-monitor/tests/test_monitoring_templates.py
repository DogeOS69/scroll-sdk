from functools import lru_cache
import json
from pathlib import Path
import subprocess
import tempfile
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


def without_migration_metadata(rules):
    return {name: {key: value for key, value in rule.items()
                   if key not in ("previousExpr", "previousAnnotations", "previousFor")}
            for name, rule in rules.items()}


class TemplateTests(unittest.TestCase):
    def test_optional_instatus_example_provisions_only_a_secret_backed_contact_point(self):
        profiles = [CHART / "values/production.yaml",
                    CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"]
        snippets = []
        for profile in profiles:
            text = profile.read_text()
            # Exercise the operator-facing, commented example, not a separate fixture.
            block = text.split("  # BEGIN OPTIONAL INSTATUS CONFIG\n", 1)[1].split(
                "  # END OPTIONAL INSTATUS CONFIG", 1)[0]
            snippets.append("grafana:\n" + "\n".join(line.replace("  # ", "  ", 1)
                                                        for line in block.splitlines()))
            disabled = yaml.safe_load(text)["grafana"]
            self.assertNotIn("envValueFrom", disabled)
            self.assertNotIn("alerting", disabled)
        self.assertEqual(snippets[0], snippets[1])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as values:
            values.write(snippets[0])
            values.flush()
            docs = render("-f", str(values.name))
        container = next(c for c in resource(docs, "Deployment", "grafana")
                         ["spec"]["template"]["spec"]["containers"] if c["name"] == "grafana")
        env = next(e for e in container["env"] if e["name"] == "INSTATUS_GRAFANA_WEBHOOK_URL")
        self.assertEqual(env["valueFrom"], {"secretKeyRef": {"name": "instatus-grafana-webhook", "key": "url"}})
        data = resource(docs, "ConfigMap", "grafana")["data"]
        config = yaml.safe_load(data["instatus-contact-points.yaml"])
        self.assertEqual(set(config), {"apiVersion", "contactPoints"})
        receiver = config["contactPoints"][0]["receivers"][0]
        self.assertEqual(receiver["settings"], {"url": "$INSTATUS_GRAFANA_WEBHOOK_URL", "httpMethod": "POST"})
        self.assertEqual(receiver["type"], "webhook")
        self.assertFalse(receiver["disableResolveMessage"])
        self.assertTrue(any(m["mountPath"] == "/etc/grafana/provisioning/alerting/instatus-contact-points.yaml"
                            for m in container["volumeMounts"]))
        default_data = resource(render(), "ConfigMap", "grafana")["data"]
        self.assertNotIn("instatus-contact-points.yaml", default_data)

    def test_eks_profile_replaces_scrapers_and_retains_rules_and_custom_sa(self):
        docs = render("--set", "eksControlPlane.enabled=true",
                      "--set", "kube-prometheus-stack.kubeScheduler.serviceMonitor.enabled=false",
                      "--set", "kube-prometheus-stack.kubeControllerManager.serviceMonitor.enabled=false",
                      "--set", "kube-prometheus-stack.prometheus.serviceAccount.name=metrics-reader")
        monitor = resource(docs, "ServiceMonitor", "scroll-monitor-eks-control-plane")
        self.assertEqual(monitor["spec"]["namespaceSelector"]["matchNames"], ["default"])
        jobs = {e["relabelings"][0]["replacement"] for e in monitor["spec"]["endpoints"]}
        self.assertEqual(jobs, {"kube-scheduler", "kube-controller-manager"})
        for endpoint in monitor["spec"]["endpoints"]:
            self.assertEqual(endpoint["tlsConfig"]["serverName"], "kubernetes.default.svc")
            self.assertNotIn("insecureSkipVerify", endpoint["tlsConfig"])
        self.assertFalse(any(d["kind"] == "ServiceMonitor" and d["metadata"]["name"] in
                             {"prometheus-kube-scheduler", "prometheus-kube-controller-manager"} for d in docs))
        alerts = {r["alert"] for d in docs if d["kind"] == "PrometheusRule"
                  for g in d["spec"]["groups"] for r in g["rules"] if "alert" in r}
        self.assertTrue({"KubeSchedulerDown", "KubeControllerManagerDown"} <= alerts)
        binding = resource(docs, "ClusterRoleBinding", "monitoring-scroll-monitor-eks-metrics")
        self.assertEqual(binding["subjects"], [{"kind": "ServiceAccount", "name": "metrics-reader", "namespace": "monitoring"}])
        role = resource(docs, "ClusterRole", "monitoring-scroll-monitor-eks-metrics")
        self.assertEqual(role["rules"], [{"apiGroups": ["metrics.eks.amazonaws.com"],
                                        "resources": ["ksh/metrics", "kcm/metrics"], "verbs": ["get"]}])

    def test_eks_requires_disabling_old_scrapers(self):
        result = subprocess.run(["helm", "template", "scroll-monitor", str(CHART),
                                 "--set", "eksControlPlane.enabled=true"], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("avoid duplicate targets", result.stderr)

    def test_pause_and_account_switches_reject_string_booleans(self):
        for option in ("grafanaAlerting.pauseRules.FeeOracleStale=false",
                       "balanceMonitoring.ethereum.feeOracle.enabled=false"):
            result = subprocess.run(["helm", "template", "scroll-monitor", str(CHART),
                                     "--set-string", option], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("boolean", result.stderr)

    def test_explicit_pauses_and_disabled_balance_account_are_consistent(self):
        args = ("--set", "balanceMonitoring.ethereum.feeOracle.enabled=false",
                "--set", "grafanaAlerting.pauseRules.FeeOracleMetricMissing=true")
        docs = render(*args)
        rules = grafana_rules(docs)
        self.assertTrue(rules["FeeOracleMetricMissing"]["isPaused"])
        self.assertTrue(rules["FeeOracleAccountBalanceLow"]["isPaused"])
        config = json.loads(resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
        self.assertTrue(config["pauseRules"]["FeeOracleBalanceMonitorMissing"])
        env = resource(docs, "Deployment", "scroll-monitor-account-balances")["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertIn({"name": "SCROLL_BALANCE_FEE_ORACLE_ENABLED", "value": "false"}, env)
        native = resource(render(*args, "--set", "grafanaAlerting.enabled=false"),
                          "PrometheusRule", "scroll-monitor-dogeos")
        names = {r["alert"] for g in native["spec"]["groups"] for r in g["rules"]}
        self.assertNotIn("FeeOracleAccountBalanceLow", names)
        self.assertNotIn("FeeOracleBalanceMonitorMissing", names)
        self.assertNotIn("FeeOracleMetricMissing", names)
        self.assertIn("EthDASubmitterAccountBalanceLow", names)

    def test_require_receiver_rejects_null_default_but_accepts_real_integration(self):
        result = subprocess.run(["helm", "template", "scroll-monitor", str(CHART),
                                 "--set", "infrastructureAlerts.requireReceiver=true"], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("configure a default Alertmanager receiver", result.stderr)
        docs = render("--set", "infrastructureAlerts.requireReceiver=true",
                      "--set", "kube-prometheus-stack.alertmanager.config.route.receiver=ops",
                      "--set", "kube-prometheus-stack.alertmanager.config.receivers[0].name=ops",
                      "--set", "kube-prometheus-stack.alertmanager.config.receivers[0].webhook_configs[0].url=https://alerts.example.com/")
        self.assertTrue(any(d["kind"] == "Alertmanager" for d in docs))

    def test_grafana_and_prometheus_use_identical_metric_rules(self):
        native = resource(render("--set", "grafanaAlerting.enabled=false"),
                          "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
        native = {rule["alert"]: rule for group in native for rule in group["rules"]}
        grafana = grafana_rules(render())
        grafana.pop("ServiceErrorOrPanickedLogs")
        grafana = {name: rule for name, rule in grafana.items() if not rule.get("isPaused")}
        self.assertEqual(without_migration_metadata(grafana), native)
        self.assertEqual(len(native), 48)  # Includes three default dstack alerts.

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
        self.assertEqual(len(grafana_rules(docs)), 19)  # Dstack alerts remain independent.
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
        self.assertEqual(charts["dstack"], examples["dstack"])
        self.assertEqual(charts["additionalServiceMonitors"], examples["additionalServiceMonitors"])
        self.assertEqual(charts["dogecoinIndexerAlerts"], examples["dogecoinIndexerAlerts"])

    def test_indexer_stall_uses_two_minutes_without_confirmation_inputs(self):
        rule = grafana_rules(render())["DogecoinIndexerLag"]
        self.assertIn('job=~"l1-interface|withdrawal-processor"', rule["expr"])
        self.assertIn("[2m]", rule["expr"])
        self.assertIn("offset 2m", rule["expr"])
        self.assertNotIn("dogecoin_chain_block_height", rule["expr"])
        self.assertEqual(rule["for"], "0s")
        legacy = grafana_rules(render(
            "--set", "dogecoinIndexerAlerts.confirmationsByJob.l1-interface=60",
            "--set", "dogecoinIndexerAlerts.confirmationsByJob.withdrawal-processor=120",
            "--set", "dogecoinIndexerAlerts.maxExcessLagBlocks=7"))["DogecoinIndexerLag"]
        self.assertEqual(legacy["expr"], rule["expr"])
        self.assertIn('job="l1-interface"})) - 60, 0) > 7', legacy["previousExpr"][1])
        self.assertIn('job="withdrawal-processor"})) - 120, 0) > 7', legacy["previousExpr"][1])

    def test_indexer_job_selector_is_configurable_and_required(self):
        rule = grafana_rules(render("--set", "dogecoinIndexerAlerts.jobRegex=custom-indexer"))["DogecoinIndexerLag"]
        self.assertIn('job=~"custom-indexer"', rule["expr"])
        result = subprocess.run(["helm", "template", "scroll-monitor", str(CHART),
                                 "--set", "dogecoinIndexerAlerts.jobRegex="], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dogecoinIndexerAlerts.jobRegex", result.stderr)

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
        self.assertEqual(len(grafana_rules(render("--set", "serviceAlerts.enabled=false"))), 49)

    def test_explicit_activation_is_equivalent_across_backends(self):
        grafana = grafana_rules(render("--set", "serviceAlerts.paused=false"))
        grafana.pop("ServiceErrorOrPanickedLogs")
        for rule in grafana.values():
            self.assertFalse(rule.pop("isPaused", False))
        native = resource(render("--set", "grafanaAlerting.enabled=false,serviceAlerts.paused=false"),
                          "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
        native = {rule["alert"]: rule for group in native for rule in group["rules"]}
        self.assertEqual(without_migration_metadata(grafana), native)
        self.assertEqual(len(native), 155)

    def test_disabling_grafana_does_not_activate_paused_rules(self):
        for setting in ("grafanaAlerting.enabled=false", "grafana.enabled=false"):
            groups = resource(render("--set", setting), "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
            self.assertEqual(sum(len(group["rules"]) for group in groups), 48)
            self.assertFalse(any("isPaused" in rule for group in groups for rule in group["rules"]))

    def test_supplemental_tso_monitor_is_default_and_discoverable(self):
        self.assertFalse(any(doc["metadata"]["name"] == "scroll-monitor-extra-tso"
                             for doc in render("--set", "additionalServiceMonitors.tso.enabled=false")))
        docs = render()
        monitor = resource(docs, "ServiceMonitor", "scroll-monitor-extra-tso")
        self.assertEqual(monitor["metadata"]["namespace"], "monitoring")
        self.assertEqual(monitor["metadata"]["labels"]["app.kubernetes.io/instance"], "scroll-monitor")
        self.assertNotIn("namespaceSelector", monitor["spec"])
        # Sanitized live Service contract from the read-only testnet audit.
        # In particular, the endpoint uses a named Service port, not "3000".
        service = {"metadata": {"labels": {
            "app.kubernetes.io/name": "tso-service",
            "app.kubernetes.io/instance": "tso-service",
            "app.kubernetes.io/service": "tso-service",
        }}, "spec": {"ports": [{"name": "http", "port": 3000, "targetPort": "http"}]}}
        for key, value in monitor["spec"]["selector"]["matchLabels"].items():
            self.assertEqual(service["metadata"]["labels"][key], value)
        endpoint = monitor["spec"]["endpoints"][0]
        self.assertIn(endpoint["port"], [port["name"] for port in service["spec"]["ports"]])
        self.assertEqual(endpoint["path"], "/metrics")


if __name__ == "__main__":
    unittest.main()
