import json
import subprocess
import unittest

from test_monitoring_templates import CHART, grafana_rules, render, resource
from test_seed_grafana_alerts import MemoryGrafana, SEED


NAMES = {"NodeDiskUsageHigh", "PVCUsageHigh"}


class DiskAlertTests(unittest.TestCase):
    def test_default_threshold_and_scope(self):
        rules = grafana_rules(render())
        for name in NAMES:
            rule = rules[name]
            self.assertFalse(rule.get("isPaused", False))
            self.assertEqual(rule["for"], "5m")
            self.assertEqual(rule["labels"]["severity"], "warning")
            self.assertIn(">= 80", rule["expr"])
            self.assertTrue(rule["expr"].strip().endswith("< 95"))
        self.assertIn('namespace="monitoring"', rules["PVCUsageHigh"]["expr"])
        self.assertNotIn('namespace="monitoring"', rules["NodeDiskUsageHigh"]["expr"])

    def test_threshold_can_change_and_rules_can_be_disabled(self):
        rules = grafana_rules(render("--set", "diskAlerts.usagePercent=85"))
        for name in NAMES:
            self.assertIn(">= 85", rules[name]["expr"])
        self.assertFalse(NAMES & grafana_rules(render("--set", "diskAlerts.enabled=false")).keys())

    def test_invalid_thresholds_are_rejected(self):
        for value in ("0", "101", "abc"):
            result = subprocess.run(["helm", "template", "scroll-monitor", str(CHART),
                                     "--set-string", f"diskAlerts.usagePercent={value}"],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("diskAlerts.usagePercent", result.stderr)

    def test_direct_slack_route_identifies_each_disk_and_pvc(self):
        for profile in (CHART / "values/production.yaml",
                        CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"):
            docs = render("-f", str(profile))
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
