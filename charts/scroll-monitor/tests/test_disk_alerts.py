import copy
import json
from pathlib import Path
import subprocess
import unittest

from test_monitoring_templates import CHART, grafana_rules, render, resource
from test_seed_grafana_alerts import MemoryGrafana, SEED


NAMES = {"NodeDiskUsageHigh", "NodeDataDiskUsageHigh", "PVCUsageHigh"}


def helm_template(*args):
    return subprocess.run(["helm", "template", "scroll-monitor", str(CHART), *args],
                          capture_output=True, text=True)


class DiskAlertTests(unittest.TestCase):
    def test_default_threshold_and_scope(self):
        rules = grafana_rules(render())
        for name in NAMES:
            rule = rules[name]
            self.assertFalse(rule.get("isPaused", False))
            self.assertEqual(rule["labels"]["severity"], "warning")
        for name in ("PVCUsageHigh", "NodeDataDiskUsageHigh"):
            self.assertEqual(rules[name]["for"], "5m")
            self.assertIn(">= 80", rules[name]["expr"])
            self.assertTrue(rules[name]["expr"].strip().endswith("< 95"))
            self.assertTrue(rules[name + "Critical"]["expr"].strip().endswith(">= 95"))
        self.assertNotIn('namespace="monitoring"', rules["PVCUsageHigh"]["expr"])
        self.assertNotIn('namespace="monitoring"', rules["NodeDiskUsageHigh"]["expr"])

    def test_node_thresholds_sit_between_kubelet_image_gc_and_eviction(self):
        rules = grafana_rules(render())
        warning, critical = rules["NodeDiskUsageHigh"], rules["NodeDiskUsageHighCritical"]
        self.assertEqual(warning["for"], "30m")
        # The warning has no upper bound, so crossing the critical threshold does not restart it.
        self.assertTrue(warning["expr"].strip().endswith(">= 85"))
        self.assertEqual(critical["for"], "5m")
        self.assertTrue(critical["expr"].strip().endswith(">= 88"))

    def test_node_and_pvc_thresholds_change_independently(self):
        rules = grafana_rules(render("--set", "diskAlerts.usagePercent=70"))
        self.assertIn(">= 70", rules["PVCUsageHigh"]["expr"])
        self.assertIn(">= 85", rules["NodeDiskUsageHigh"]["expr"])
        rules = grafana_rules(render("--set", "diskAlerts.nodeUsagePercent=86",
                                     "--set", "diskAlerts.nodeCriticalUsagePercent=89",
                                     "--set", "diskAlerts.nodeWarningFor=1h"))
        self.assertTrue(rules["NodeDiskUsageHigh"]["expr"].strip().endswith(">= 86"))
        self.assertEqual(rules["NodeDiskUsageHigh"]["for"], "1h")
        self.assertTrue(rules["NodeDiskUsageHighCritical"]["expr"].strip().endswith(">= 89"))
        self.assertIn(">= 80", rules["PVCUsageHigh"]["expr"])
        self.assertFalse(NAMES & grafana_rules(render("--set", "diskAlerts.enabled=false")).keys())

    def test_invalid_thresholds_are_rejected(self):
        for key in ("usagePercent", "nodeUsagePercent"):
            for value in ("0", "101", "abc"):
                result = helm_template("--set-string", f"diskAlerts.{key}={value}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"diskAlerts.{key}", result.stderr)

    def test_node_warning_must_be_below_node_critical(self):
        result = helm_template("--set", "diskAlerts.nodeUsagePercent=88")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("diskAlerts.nodeUsagePercent must be below", result.stderr)

    def test_node_critical_must_fire_before_kubelet_eviction(self):
        for args in (("--set", "diskAlerts.nodeCriticalUsagePercent=90"),
                     ("--set", "diskAlerts.kubeletEvictionAvailablePercent=15")):
            result = helm_template(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("before the kubelet evicts pods", result.stderr)
        self.assertEqual(helm_template("--set", "diskAlerts.nodeCriticalUsagePercent=89.9").returncode, 0)
        # Upstream kubelet defaults also evict on imagefs.available<15%; lower thresholds then fit.
        self.assertEqual(helm_template("--set", "diskAlerts.kubeletEvictionAvailablePercent=15",
                                       "--set", "diskAlerts.nodeUsagePercent=80",
                                       "--set", "diskAlerts.nodeCriticalUsagePercent=83").returncode, 0)

    def test_eviction_percent_accepts_zero_and_rejects_invalid_values(self):
        self.assertEqual(helm_template("--set", "diskAlerts.kubeletEvictionAvailablePercent=0").returncode, 0)
        for value in ("100", "-1", "abc"):
            result = helm_template("--set-string", f"diskAlerts.kubeletEvictionAvailablePercent={value}")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("diskAlerts.kubeletEvictionAvailablePercent", result.stderr)

    def test_kubelet_mountpoints_split_node_rules(self):
        rules = grafana_rules(render())
        for name in ("NodeDiskUsageHigh", "NodeDiskUsageHighCritical"):
            self.assertIn('mountpoint=~"/|/var|/var/lib/kubelet|/var/lib/containerd"', rules[name]["expr"])
        for name in ("NodeDataDiskUsageHigh", "NodeDataDiskUsageHighCritical"):
            self.assertIn('mountpoint!~"/|/var|/var/lib/kubelet|/var/lib/containerd"', rules[name]["expr"])
        rules = grafana_rules(render("--set-string", "diskAlerts.kubeletMountpointRegex=/var/lib/rancher"))
        self.assertIn('mountpoint=~"/var/lib/rancher"', rules["NodeDiskUsageHigh"]["expr"])
        self.assertIn('mountpoint!~"/var/lib/rancher"', rules["NodeDataDiskUsageHigh"]["expr"])
        result = helm_template("--set-string", "diskAlerts.kubeletMountpointRegex=")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("diskAlerts.kubeletMountpointRegex", result.stderr)

    def test_invalid_kubelet_mountpoint_regex_is_rejected(self):
        result = helm_template("--set-string", "diskAlerts.kubeletMountpointRegex=(/var")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error parsing regexp", result.stderr)

    def test_grafana_migrates_shipped_node_rules_and_splits_keep_operator_settings(self):
        config = json.loads(resource(render(), "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
        sources = {rule["alert"]: (group["name"], rule) for group in config["groups"] for rule in group["rules"]}
        # What 0.1.64-dogeos rendered with default values, pinned so that later edits to
        # previousExpr cannot silently stop the migration of existing Grafana rules.
        shipped = json.loads((Path(__file__).parent / "fixtures/node-disk-usage-0.1.64-dogeos.json").read_text())
        for name, new_for in (("NodeDiskUsageHigh", "30m"), ("NodeDiskUsageHighCritical", "5m")):
            group, source = sources[name]
            self.assertEqual(source["previousExpr"], shipped[name]["expr"])
            self.assertEqual(source["previousAnnotations"], shipped[name]["annotations"])
            desired = SEED.alert_rule(source, config, group)
            existing = copy.deepcopy(desired)
            existing["data"][0]["model"]["expr"] = shipped[name]["expr"]
            existing["for"] = shipped[name]["for"]
            existing["annotations"] = {key: value.replace("$value", "$values.A.Value")
                                       for key, value in shipped[name]["annotations"].items()}
            updated = SEED.migrate_expression(existing, source, desired)
            self.assertEqual(updated["data"][0]["model"]["expr"], source["expr"])
            self.assertEqual(updated["for"], new_for)
            for key in ("summary", "description"):
                self.assertEqual(updated["annotations"][key], desired["annotations"][key])
        self.assertEqual(sources["NodeDataDiskUsageHigh"][1]["inheritOperatorSettingsFrom"], "NodeDiskUsageHigh")
        self.assertEqual(sources["NodeDataDiskUsageHighCritical"][1]["inheritOperatorSettingsFrom"],
                         "NodeDiskUsageHighCritical")
        # Grafana-only metadata must not reach PrometheusRule, which rejects unknown fields.
        native = resource(render("--set", "grafanaAlerting.enabled=false"), "PrometheusRule", "scroll-monitor-dogeos")
        for group in native["spec"]["groups"]:
            for rule in group["rules"]:
                self.assertFalse({"inheritOperatorSettingsFrom", "previousExpr", "previousFor",
                                  "previousAnnotations"} & rule.keys(), rule.get("alert"))

    def test_direct_slack_route_identifies_each_disk_and_pvc(self):
        for profile in (CHART / "values/production.yaml",
                        CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"):
            # This test covers alerting; status-page generation is tested separately.
            docs = render("-f", str(profile), "--set", "statusPage.enabled=false")
            config = json.loads(resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
            self.assertEqual(config["diskContactPoint"], "slack-alerts")
            for group in config["groups"]:
                for source in group["rules"]:
                    if source["alert"] in NAMES:
                        rule = SEED.alert_rule(source, config, group["name"])
                        settings = SEED.notification_routes(config)["disks"]
                        self.assertIn("scroll_monitor_route", rule["labels"])
                        self.assertEqual(settings["receiver"], "slack-alerts")
                        self.assertEqual(settings["group_wait"], "30s")
                        self.assertTrue({"namespace", "persistentvolumeclaim", "instance", "mountpoint"}
                                        <= set(settings["group_by"]))

    def test_disk_contact_is_checked_without_pod_alerts(self):
        client = MemoryGrafana()
        with self.assertRaisesRegex(RuntimeError, "existing Grafana Slack contact"):
            SEED.seed(client, {"diskContactPoint": "slack-alerts"})
        self.assertEqual(client.writes, [])


if __name__ == "__main__":
    unittest.main()
