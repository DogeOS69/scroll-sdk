"""Production timing overrides must reach both evaluators and existing Grafana rules."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml

from test_monitoring_templates import CHART, render, resource, grafana_rules
from test_seed_grafana_alerts import MemoryGrafana, SEED


def render_values(values, *args):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as file:
        yaml.safe_dump(values, file)
        file.flush()
        return render("-f", file.name, *args)


def catalog():
    return {rule["alert"]: rule for path in sorted((CHART / "alerts").rglob("*.yaml"))
            for group in yaml.safe_load(path.read_text())["groups"] for rule in group["rules"]}


class AlertTimingTests(unittest.TestCase):
    def test_omitted_and_empty_overrides_preserve_defaults(self):
        defaults = grafana_rules(render())
        empty = grafana_rules(render_values({"alertTiming": {"rules": {}, "groupIntervals": {}}}))
        self.assertEqual(defaults, empty)
        self.assertEqual(defaults["FeeOracleStale"]["for"], "5m")
        self.assertIn("> 900", defaults["FeeOracleStale"]["expr"])
        self.assertIn("[60m:1m]", defaults["ReplayHeadWFTxNumberStalled"]["expr"])
        self.assertIn("[2m]", defaults["DogecoinIndexerLag"]["expr"])
        self.assertIn("[5m]", defaults["ServiceErrorLogs"]["expr"])
        self.assertNotIn("__TIME_", json.dumps(defaults))
        self.assertFalse(any("timing" in r or "timingAnnotations" in r for r in defaults.values()))

    def test_all_shipped_rules_accept_pending_periods_and_declared_parameters(self):
        overrides = {}
        for name, rule in catalog().items():
            params = copy.deepcopy(rule.get("timing", {}))
            for key, value in params.items():
                params[key] = value * 2 if key.endswith("Seconds") else str(int(value[:-1]) * 2) + value[-1]
            if re.search(r"__(TSO_(REGISTRY|STATUS)|WP_(JOBS|JOB_HEAD|PROOF_WORK))_VALID__", rule["expr"]):
                params["snapshotMaxAgeSeconds"] = 240
            overrides[name] = {**params, "for": "7m"}
        values = {"alertTiming": {"rules": overrides}, "dstack": {"gpuHosts": {"enabled": True, "expectedHosts": ["test-gpu"]}}}
        overrides["DstackHostTelemetryUnavailable"] = {"for": "7m"}
        overrides["DstackHostDiskSpaceLow"] = {"for": "7m"}
        grafana = grafana_rules(render_values(values))
        native = resource(render_values(values, "--set", "grafanaAlerting.enabled=false"),
                          "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
        native = {r["alert"]: r for g in native for r in g["rules"]}
        for name, rule in grafana.items():
            self.assertEqual(rule["for"], "7m", name)
            self.assertNotIn("__TIME_", json.dumps(rule), name)
            if name in native:
                self.assertEqual(rule["expr"], native[name]["expr"], name)
                self.assertEqual(rule["for"], native[name]["for"], name)
                self.assertEqual(rule["annotations"], native[name]["annotations"], name)
        self.assertIn("[120m:2m]", grafana["ProtocolStateWFTxNumberStalled"]["expr"])
        self.assertIn("offset 120m", grafana["ProtocolStateWFTxNumberStalled"]["expr"])
        self.assertIn("[4m]", grafana["DogecoinIndexerLag"]["expr"])
        self.assertIn("offset 4m", grafana["DogecoinIndexerLag"]["expr"])
        self.assertIn("< 1200", grafana["BusinessPodContainerRestarted"]["expr"])
        self.assertIn("time() - 1200", grafana["BusinessPodContainerFailed"]["expr"])
        self.assertIn("> 60", grafana["CubeSignerSigningSlow"]["expr"])
        self.assertIn(">= 5", grafana["CubeSignerSigningSlow"]["expr"])  # sample count is not a timeout
        self.assertIn("< 240", grafana["WFBuildQueueStalled"]["expr"])
        self.assertIn("< 120", str(grafana["WFBuildQueueStalled"]["previousExpr"]))  # legacy migration stays exact
        self.assertIn("1800 seconds", grafana["FeeOracleStale"]["annotations"]["summary"])
        self.assertIn("10m", grafana["ServiceErrorLogs"]["annotations"]["description"])

    def test_production_profiles_support_partial_overrides_and_existing_settings(self):
        values = {"alertTiming": {"rules": {"FeeOracleStale": {"for": "0s", "maxAgeSeconds": 1800}}},
                  "businessAlerts": {"l2BatchStallSeconds": 9000, "jobMaxAgeSeconds": 1200},
                  "statusPage": {"enabled": False}}
        for profile in (CHART / "values/production.yaml", CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as file:
                yaml.safe_dump(values, file); file.flush()
                rules = grafana_rules(render("-f", str(profile), "-f", file.name))
            self.assertEqual(rules["FeeOracleStale"]["for"], "0s")
            self.assertIn("> 1800", rules["FeeOracleStale"]["expr"])
            self.assertIn("[9000s:1m]", rules["L2BatchHeightStalled"]["expr"])
            self.assertIn("> 1200", rules["WFJobStalled"]["expr"])

    def test_group_intervals_and_dynamic_quorum(self):
        values = {"alertTiming": {"groupIntervals": {"dogeos.metrics": "30s", "dogeos.logs": "2m"},
                                  "rules": {"TSOCorrectnessQuorumUnavailable": {"for": "8m", "snapshotMaxAgeSeconds": 240}}},
                  "businessAlerts": {"requiredSignersByRole": {"Correctness": 2}}}
        docs = render_values(values)
        cfg = json.loads(resource(docs, "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
        intervals = {g["name"]: g["interval"] for g in cfg["groups"]}
        self.assertEqual(intervals["dogeos.metrics"], "30s")
        self.assertEqual(intervals["dogeos.logs"], "2m")
        rule = grafana_rules(docs)["TSOCorrectnessQuorumUnavailable"]
        self.assertEqual(rule["for"], "8m")
        self.assertIn("< 240", rule["expr"])

    def test_invalid_names_types_and_durations_fail_at_render_time(self):
        invalid = [
            {"rules": {"FeeOracleTypo": {"for": "5m"}}},
            {"rules": {"FeeOracleStale": {"maxAgeSecond": 120}}},
            {"rules": {"FeeOracleStale": {"for": "-5m"}}},
            {"rules": {"FeeOracleStale": {"for": 10}}},
            {"rules": {"FeeOracleStale": {"maxAgeSeconds": "120"}}},
            {"rules": {"FeeOracleStale": {"maxAgeSeconds": False}}},
            {"rules": {"FeeOracleStale": {"maxAgeSeconds": 0}}},
            {"rules": {"DogecoinIndexerLag": {"window": "0s"}}},
            {"rules": {"ReplayHeadWFTxNumberStalled": {"window": "1m", "step": "2m"}}},
            {"groupIntervals": {"dogeos.metrics": "0s"}},
            {"groupIntervals": {"unknown.group": "1m"}},
        ]
        for value in invalid:
            with self.subTest(value=value), tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as file:
                yaml.safe_dump({"alertTiming": value}, file); file.flush()
                result = subprocess.run(["helm", "template", "monitor", str(CHART), "-f", file.name], text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("alertTiming", result.stderr)

    @unittest.skipUnless(os.environ.get("SCROLL_STATUS_RUNTIME_TEST") == "1", "requires Docker/promtool")
    def test_custom_age_and_pending_period_control_firing(self):
        docs = render_values({"alertTiming": {"rules": {"FeeOracleStale": {"maxAgeSeconds": 600, "for": "3m"}}}},
                             "--set", "grafanaAlerting.enabled=false")
        groups = resource(docs, "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
        rule = next(r for g in groups for r in g["rules"] if r["alert"] == "FeeOracleStale")
        tests = {"rule_files": ["rules.yaml"], "evaluation_interval": "1m", "tests": [{
            "interval": "1m", "input_series": [{"series": "fee_oracle_ethereum_da_oracle_value_latest_computed_at_ms", "values": "0x20"}],
            "alert_rule_test": [
                {"eval_time": "13m", "alertname": "FeeOracleStale", "exp_alerts": []},
                {"eval_time": "14m", "alertname": "FeeOracleStale", "exp_alerts": [{"exp_labels": rule["labels"], "exp_annotations": rule["annotations"]}]},
            ]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); root.chmod(0o755)
            (root / "rules.yaml").write_text(yaml.safe_dump({"groups": [{"name": "custom", "rules": [rule]}]}))
            (root / "tests.yaml").write_text(yaml.safe_dump(tests))
            result = subprocess.run(["docker", "run", "--rm", "--entrypoint", "promtool", "-v", f"{root}:/work:ro", "-w", "/work",
                                     "prom/prometheus:v2.52.0", "test", "rules", "tests.yaml"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class GrafanaTimingTests(unittest.TestCase):
    def test_explicit_timing_reconciles_existing_rule_and_preserves_other_ui_fields(self):
        values = {"alertTiming": {"rules": {"FeeOracleStale": {"for": "10m", "maxAgeSeconds": 1800}},
                                  "groupIntervals": {"dogeos.metrics": "30s"}}}
        cfg = json.loads(resource(render_values(values), "ConfigMap", "scroll-monitor-grafana-alerts")["data"]["rules.json"])
        source = next(r for g in cfg["groups"] for r in g["rules"] if r["alert"] == "FeeOracleStale")
        cfg = {k: cfg[k] for k in ("folderUID", "folderTitle", "datasourceUID", "timingOverrides", "groupIntervals")}
        cfg["groups"] = [{"name": "dogeos.metrics", "rules": [source]}]
        client = MemoryGrafana()
        SEED.seed(client, cfg)
        self.assertEqual(client.group["interval"], 30)
        existing = client.group["rules"][0]
        existing["for"] = "1h"
        existing["data"][0]["model"]["expr"] = "custom_metric > 0"
        existing["annotations"]["description"] = "custom description"
        existing["isPaused"] = True
        existing["labels"]["team"] = "operators"
        existing["notification_settings"] = {"receiver": "custom-contact"}
        SEED.seed(client, cfg)
        result = client.group["rules"][0]
        self.assertEqual(result["for"], "10m")
        self.assertIn("> 1800", result["data"][0]["model"]["expr"])
        self.assertIn("1800 seconds", result["annotations"]["description"])
        self.assertTrue(result["isPaused"])
        self.assertEqual(result["labels"]["team"], "operators")
        self.assertEqual(result["notification_settings"], {"receiver": "custom-contact"})
        client.writes.clear()
        SEED.seed(client, cfg)
        self.assertEqual(client.writes, [])
        # Removing overrides restores UI ownership, including group interval.
        cfg.pop("timingOverrides"); cfg.pop("groupIntervals")
        result["for"] = "2h"; client.group["interval"] = 300
        SEED.seed(client, cfg)
        self.assertEqual(client.group["rules"][0]["for"], "2h")
        self.assertEqual(client.group["interval"], 300)

    def test_group_interval_dry_run_does_not_write(self):
        cfg = {"folderUID": "test", "folderTitle": "Test", "datasourceUID": "prometheus",
               "groups": [{"name": "test", "rules": [{"alert": "Test", "expr": "up == 0"}]}]}
        client = MemoryGrafana(); SEED.seed(client, cfg); client.writes.clear()
        cfg["groupIntervals"] = {"test": "30s"}
        SEED.seed(client, cfg, dry_run=True)
        self.assertEqual(client.group["interval"], 60)
        self.assertEqual(client.writes, [])
