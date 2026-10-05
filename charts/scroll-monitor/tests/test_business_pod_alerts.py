import copy
import json
import unittest

from test_monitoring_templates import CHART, grafana_rules, render, resource
from test_seed_grafana_alerts import MemoryGrafana, SEED


NAMES = {"BusinessPodContainerRestarted", "BusinessPodContainerFailed",
         "BusinessPodCrashLooping", "BusinessPodFailed"}


class PodAlertTests(unittest.TestCase):
    def test_active_despite_paused_diagnostics_and_scoped_to_release_namespace(self):
        rules = grafana_rules(render())
        for name in NAMES:
            rule = rules[name]
            self.assertFalse(rule.get("isPaused", False))
            self.assertEqual(rule["for"], "5m" if name == "BusinessPodCrashLooping" else "0s")
            self.assertEqual(rule["labels"]["severity"], "warning")
            self.assertIn('namespace="monitoring"', rule["expr"])
            self.assertNotIn("__POD_SELECTOR__", rule["expr"])

    def test_can_disable_or_narrow_pods(self):
        self.assertFalse(NAMES & grafana_rules(render("--set", "businessPodAlerts.enabled=false")).keys())
        rules = grafana_rules(render("--set-string", "businessPodAlerts.podNameRegex=worker-.*",
                                     "--set-string", "businessPodAlerts.excludePodNameRegex=worker-test-.*"))
        for name in NAMES:
            self.assertIn('pod=~"worker-.*"', rules[name]["expr"])
            self.assertIn('pod!~"worker-test-.*"', rules[name]["expr"])

    def test_production_routes_new_rules_directly_to_existing_slack(self):
        for profile in (CHART / "values/production.yaml",
                        CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"):
            docs = render("-f", str(profile))
            config = json.loads(resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
            self.assertEqual(config["businessPodContactPoint"], "slack-alerts")
            for group in config["groups"]:
                for source in group["rules"]:
                    rule = SEED.alert_rule(source, config, group["name"])
                    if source.get("labels", {}).get("alert_scope") == "business-pods":
                        settings = SEED.notification_routes(config)["business-pods"]
                        self.assertIn("scroll_monitor_route", rule["labels"])
                        self.assertNotIn("notification_settings", rule)
                        self.assertEqual(settings["receiver"], "slack-alerts")
                        self.assertEqual(settings["group_wait"], "30s")
                        self.assertEqual(settings["routes"][0]["group_wait"], "0s")
                        self.assertIn("pod", settings["group_by"])
                        self.assertIn("uid", settings["group_by"])
                    elif source.get("labels", {}).get("alert_scope") not in ("disks", "resources"):
                        self.assertNotIn("notification_settings", rule)

    def test_missing_slack_contact_fails_before_any_writes(self):
        client = MemoryGrafana()
        with self.assertRaisesRegex(RuntimeError, "existing Grafana Slack contact"):
            SEED.seed(client, {"businessPodContactPoint": "slack-alerts"})
        self.assertEqual(client.writes, [])

    def test_seed_reuses_slack_and_preserves_operator_routing_on_upgrade(self):
        class SlackGrafana(MemoryGrafana):
            def request(self, method, path, body=None, allow_missing=False):
                if method == "GET" and path == "/api/v1/provisioning/contact-points":
                    return [{"name": "slack-alerts", "type": "slack"}]
                return super().request(method, path, body, allow_missing)

        config = {"folderUID": "test", "folderTitle": "Test", "datasourceUID": "prometheus",
                  "businessPodContactPoint": "slack-alerts",
                  "groups": [{"name": "business-pods", "rules": [{
                      "alert": "BusinessPodFailed", "expr": "failed == 1",
                      "labels": {"alert_scope": "business-pods"},
                  }]}]}
        client = SlackGrafana()
        SEED.seed(client, config)
        saved = client.group["rules"][0]
        self.assertEqual(client.policies["routes"][0]["receiver"], "slack-alerts")
        saved["notification_settings"] = {"receiver": "operator-slack"}
        saved["notification_settings"]["receiver"] = "operator-slack"
        saved["isPaused"] = True
        before = copy.deepcopy(saved)
        client.writes.clear()
        SEED.seed(client, config)
        self.assertEqual(client.group["rules"][0], before)
        self.assertEqual(client.writes, [])


if __name__ == "__main__":
    unittest.main()
