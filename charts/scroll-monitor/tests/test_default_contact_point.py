"""Bootstrap an empty default destination without overwriting UI configuration."""
import copy
import json
import os
import unittest
from unittest.mock import patch

from test_monitoring_templates import CHART, render, resource
from test_seed_grafana_alerts import MemoryGrafana, SEED


class ContactGrafana(MemoryGrafana):
    def __init__(self):
        super().__init__()
        self.config = {"template_files": {"operator": "existing template"},
                       "alertmanager_config": {
                           "route": {"receiver": "grafana-default-email", "group_by": ["alertname"],
                                     "routes": [{"receiver": "other", "object_matchers": [["team", "=", "other"]]}]},
                           "receivers": [{"name": "grafana-default-email"},
                                         {"name": "other", "grafana_managed_receiver_configs": [
                                             {"uid": "other-slack", "name": "other", "type": "slack",
                                              "settings": {}, "secureFields": {"url": True}}]}]}}
        self.policies = self.config["alertmanager_config"]["route"]

    def request(self, method, path, body=None, allow_missing=False):
        if method == "PUT" and path.startswith(self.TEMPLATES):
            self.config["template_files"][path.removeprefix(self.TEMPLATES)] = body["template"]
        if path == SEED.ALERTMANAGER_CONFIG_PATH:
            if method == "GET":
                return copy.deepcopy(self.config)
            assert method == "POST"
            self.writes.append((method, path, copy.deepcopy(body)))
            self.config = copy.deepcopy(body)
            self.policies = self.config["alertmanager_config"]["route"]
            return None
        if method == "GET" and path == "/api/v1/provisioning/contact-points":
            return [cp for r in self.config["alertmanager_config"]["receivers"]
                    for cp in r.get("grafana_managed_receiver_configs", [])]
        return super().request(method, path, body, allow_missing)


class DefaultContactPointTests(unittest.TestCase):
    def setUp(self):
        self.client = ContactGrafana()
        self.spec = {"defaultContactPoint": {"name": "slack-alerts"}}

    def bootstrap(self, dry_run=False):
        plan = SEED.default_contact_point_plan(self.client, self.spec)
        SEED.seed_default_contact_point(self.client, plan, dry_run=dry_run)
        return plan

    def test_creates_empty_destination_and_preserves_other_configuration(self):
        expected = copy.deepcopy(self.client.config)
        expected["alertmanager_config"]["route"]["receiver"] = "slack-alerts"
        expected["alertmanager_config"]["receivers"].append(
            {"name": "slack-alerts", "grafana_managed_receiver_configs": []})
        plan = self.bootstrap()
        self.assertTrue(plan["empty"])
        self.assertEqual(self.client.config, expected)
        self.assertEqual(len(self.client.writes), 1)

    def test_ui_integration_and_repeated_upgrade_are_preserved(self):
        self.bootstrap()
        self.client.config["alertmanager_config"]["receivers"][-1]["grafana_managed_receiver_configs"] = [
            {"uid": "ui-slack", "type": "slack", "settings": {}, "secureFields": {"url": True}}]
        before = copy.deepcopy(self.client.config)
        self.client.writes.clear()
        plan = self.bootstrap()
        self.assertFalse(plan["empty"])
        self.assertEqual(self.client.config, before)
        self.assertEqual(self.client.writes, [])

    def test_custom_default_and_child_routes_are_preserved(self):
        self.client.policies["receiver"] = "other"
        before = copy.deepcopy(self.client.policies)
        self.bootstrap()
        self.assertEqual(self.client.policies, before)

    def test_binds_blank_slack_fields_preserving_custom_fields_and_secrets(self):
        self.bootstrap()
        integrations = [
            {"uid": "blank", "type": "slack", "settings": {"title": " ", "text": None},
             "secureFields": {"url": True}, "disableResolveMessage": True},
            {"uid": "custom", "type": "slack", "settings": {"title": "Custom title", "text": "Custom text"},
             "secureFields": {"token": True}},
            {"uid": "partial", "type": "slack", "settings": {"title": "My title"}},
            {"uid": "email", "type": "email", "settings": {"addresses": "operator@example.invalid"}},
        ]
        self.client.config["alertmanager_config"]["receivers"][-1]["grafana_managed_receiver_configs"] = integrations
        before = copy.deepcopy(self.client.config)
        self.spec["notificationTemplate"] = {"name": "scroll-monitor", "template": "template content"}
        self.bootstrap()
        expected = copy.deepcopy(before)
        settings = expected["alertmanager_config"]["receivers"][-1]["grafana_managed_receiver_configs"]
        settings[0]["settings"].update(title='{{ template "scroll-monitor.slack.title" . }}',
                                        text='{{ template "scroll-monitor.slack.text" . }}')
        settings[2]["settings"]["text"] = '{{ template "scroll-monitor.slack.text" . }}'
        self.assertEqual(self.client.config, expected)
        self.client.writes.clear()
        self.bootstrap()
        self.assertEqual(self.client.writes, [])

    def test_binding_can_be_disabled_without_changing_integrations(self):
        self.bootstrap()
        self.client.config["alertmanager_config"]["receivers"][-1]["grafana_managed_receiver_configs"] = [
            {"uid": "ui-slack", "type": "slack", "settings": {}, "secureFields": {"url": True}}]
        self.spec["notificationTemplate"] = {"name": "scroll-monitor", "bindDefaultContactPoint": False}
        before = copy.deepcopy(self.client.config)
        self.client.writes.clear()
        self.bootstrap()
        self.assertEqual(self.client.config, before)
        self.assertEqual(self.client.writes, [])

    def test_template_is_installed_before_binding_and_survives_config_write(self):
        self.bootstrap()
        self.client.config["alertmanager_config"]["receivers"][-1]["grafana_managed_receiver_configs"] = [
            {"uid": "ui-slack", "type": "slack", "settings": {}, "secureFields": {"url": True}}]
        config = dict(self.spec, folderUID="test", folderTitle="Test", groups=[],
                      notificationTemplate={"name": "scroll-monitor", "template": "new template"})
        self.client.writes.clear()
        SEED.seed(self.client, config)
        paths = [w[1] for w in self.client.writes]
        self.assertLess(paths.index(self.client.TEMPLATES + "scroll-monitor"),
                        paths.index(SEED.ALERTMANAGER_CONFIG_PATH))
        self.assertEqual(self.client.config["template_files"]["scroll-monitor"],
                         SEED.managed_template("new template"))
        self.assertEqual(self.client.config["template_files"]["operator"], "existing template")
        self.client.writes.clear()
        SEED.seed(self.client, config)
        self.assertEqual(self.client.writes, [])

    def test_disabled_and_dry_run_do_not_write(self):
        self.assertIsNone(SEED.default_contact_point_plan(self.client, {}))
        before = copy.deepcopy(self.client.config)
        self.bootstrap(dry_run=True)
        self.assertEqual(self.client.config, before)
        self.assertEqual(self.client.writes, [])

    def test_invalid_existing_configuration_is_not_replaced(self):
        for invalid in (None, {}, {"alertmanager_config": {"receivers": []}}):
            self.client.config = invalid
            with self.assertRaisesRegex(RuntimeError, "refusing to replace"):
                self.bootstrap()
        self.assertEqual(self.client.writes, [])

    def test_empty_destination_works_with_existing_seeder_and_scoped_policies(self):
        config = dict(self.spec, folderUID="test", folderTitle="Test", groups=[],
                      businessPodContactPoint="slack-alerts", diskContactPoint="slack-alerts",
                      resourceContactPoint="slack-alerts")
        SEED.seed(self.client, config)
        self.assertEqual(self.client.policies["receiver"], "slack-alerts")
        self.assertEqual(len(self.client.policies["routes"]), 4)
        self.assertEqual(self.client.writes[0][1], SEED.ALERTMANAGER_CONFIG_PATH)
        self.client.writes.clear()
        SEED.seed(self.client, config)
        self.assertEqual(self.client.writes, [])

    def test_invalid_explicit_slack_reference_fails_before_bootstrap_writes(self):
        with self.assertRaisesRegex(RuntimeError, "existing Grafana Slack contact"):
            SEED.seed(self.client, dict(self.spec, businessPodContactPoint="missing-contact"))
        self.assertEqual(self.client.writes, [])

    def test_uncertain_configuration_post_is_not_retried(self):
        with patch.dict(os.environ, GRAFANA_URL="http://grafana.invalid", GRAFANA_TOKEN="test-token"), \
                patch.object(SEED, "urlopen", side_effect=TimeoutError("response lost")) as request:
            with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
                SEED.Grafana().request("POST", SEED.ALERTMANAGER_CONFIG_PATH, {})
            self.assertEqual(request.call_count, 1)

    def test_examples_use_existing_seeder_without_inline_code_or_an_extra_job(self):
        profile = CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"
        docs = render("-f", str(profile))
        jobs = [d["metadata"]["name"] for d in docs if d["kind"] == "Job"]
        self.assertNotIn("grafana-slack-bootstrap", jobs)
        self.assertNotIn("import base64", profile.read_text())
        cm = resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")
        self.assertIn("def default_contact_point_plan", cm["data"]["seed.py"])
        config = json.loads(cm["data"]["rules.json"])
        self.assertEqual(config["defaultContactPoint"], {"name": "slack-alerts"})
        self.assertEqual(config["diskContactPoint"], "slack-alerts")
        disabled = render("--set", "grafanaAlerting.defaultContactPoint.enabled=false")
        config = json.loads(resource(disabled, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
        self.assertNotIn("defaultContactPoint", config)

    def test_chart_binding_defaults_on_and_supports_opt_out(self):
        for args, expected in (((), True),
                               (("--set", "grafanaAlerting.notificationTemplate.bindDefaultContactPoint=false"), False)):
            docs = render(*args)
            config = json.loads(resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
            self.assertIs(config["notificationTemplate"]["bindDefaultContactPoint"], expected)


if __name__ == "__main__":
    unittest.main()
