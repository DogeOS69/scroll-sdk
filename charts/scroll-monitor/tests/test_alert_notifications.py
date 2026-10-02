"""Shared alert wording and Slack template; see docs/alert-notifications.md."""

from collections import Counter
import json
from pathlib import Path
import re
import tempfile
import unittest

import yaml

from test_monitoring_templates import render, resource


CHART = Path(__file__).resolve().parents[1]
TEMPLATE_EXPR = re.compile(r"\{\{.*?\}\}")
METRIC_NAME = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}\b")
RAW_VALUE = re.compile(r"\{\{-?\s*\$value\s*-?\}\}")


def source_rules():
    for path in sorted((CHART / "alerts").rglob("*.yaml")):
        for group in yaml.safe_load(path.read_text())["groups"]:
            for rule in group["rules"]:
                yield rule


class AlertWordingTests(unittest.TestCase):
    def test_summary_is_a_short_plain_headline(self):
        for rule in source_rules():
            with self.subTest(alert=rule["alert"]):
                summary = rule["annotations"]["summary"]
                plain = TEMPLATE_EXPR.sub("x", summary)
                self.assertNotIn("\n", summary.strip())
                self.assertTrue(summary.endswith("."))
                self.assertLessEqual(len(plain), 100)
                self.assertNotRegex(plain, METRIC_NAME, "name the component, not a metric")

    def test_description_adds_detail(self):
        for rule in source_rules():
            with self.subTest(alert=rule["alert"]):
                annotations = rule["annotations"]
                self.assertTrue(annotations["description"].strip())
                self.assertNotEqual(annotations["description"].strip(), annotations["summary"].strip())

    def test_summaries_identify_one_alert(self):
        counts = Counter(rule["annotations"]["summary"] for rule in source_rules())
        self.assertEqual([summary for summary, count in counts.items() if count > 1], [])

    def test_values_are_formatted_for_people(self):
        for rule in source_rules():
            for key, text in rule["annotations"].items():
                with self.subTest(alert=rule["alert"], annotation=key):
                    self.assertNotRegex(text, RAW_VALUE, "pipe $value through printf or humanize*")


class SlackTemplateTests(unittest.TestCase):
    def seed_config(self, *args):
        docs = render(*args)
        return json.loads(resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])

    def test_template_is_seeded_with_the_network_name(self):
        template = self.seed_config("--set", "statusPage.environment=testnet")["notificationTemplate"]
        self.assertEqual(template["name"], "scroll-monitor")
        for name in ("scroll-monitor.slack.title", "scroll-monitor.slack.text"):
            self.assertIn(f'{{{{ define "{name}" -}}}}', template["template"])
        self.assertIn(" · testnet ·", template["template"])
        self.assertNotIn("__ENVIRONMENT__", template["template"])

    def test_template_can_be_disabled(self):
        config = self.seed_config("--set", "grafanaAlerting.notificationTemplate.enabled=false")
        self.assertNotIn("notificationTemplate", config)

    def test_slack_example_survives_grafana_chart_tpl(self):
        for profile in (CHART / "values/production.yaml",
                        CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"):
            with self.subTest(profile=profile.name):
                block = profile.read_text().split("  # alerting:\n  #   internal-slack.yaml:\n", 1)[1]
                block = block.split("  # Optional Instatus", 1)[0]
                lines = [line.replace("  # ", "  ", 1) for line in block.splitlines()]
                values = "grafana:\n  alerting:\n    internal-slack.yaml:\n" + "\n".join(lines) + "\n"
                with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as handle:
                    handle.write(values)
                    handle.flush()
                    docs = render("-f", handle.name)
                provisioned = resource(docs, "ConfigMap", "grafana")["data"]["internal-slack.yaml"]
                settings = yaml.safe_load(provisioned)["contactPoints"][0]["receivers"][0]["settings"]
                self.assertEqual(settings["title"], '{{ template "scroll-monitor.slack.title" . }}')
                self.assertEqual(settings["text"], '{{ template "scroll-monitor.slack.text" . }}')


if __name__ == "__main__":
    unittest.main()
