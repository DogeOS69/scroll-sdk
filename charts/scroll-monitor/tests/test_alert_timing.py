"""Production timing overrides must reach both evaluators and existing Grafana rules."""
import copy
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import urlopen

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
            {"groupIntervals": {"dogeos.metrics": "1s"}},
            {"groupIntervals": {"dogeos.metrics": "15s"}},
            {"groupIntervals": {"dogeos.logs": "15s"}},
            {"groupIntervals": {"unknown.group": "1m"}},
        ]
        for value in invalid:
            with self.subTest(value=value), tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as file:
                yaml.safe_dump({"alertTiming": value}, file); file.flush()
                result = subprocess.run(["helm", "template", "monitor", str(CHART), "-f", file.name], text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("alertTiming", result.stderr)

    def test_prometheus_group_intervals_do_not_inherit_grafana_constraints(self):
        values = {"alertTiming": {"groupIntervals": {"dogeos.metrics": "15s"}}}
        for args in (("--set", "grafanaAlerting.enabled=false"),
                     ("--set", "alerting.backend=prometheus", "--set",
                      "kube-prometheus-stack.alertmanager.alertmanagerSpec.useExistingSecret=true", "--set",
                      "kube-prometheus-stack.alertmanager.alertmanagerSpec.configSecret=scroll-monitor-alertmanager-config")):
            groups = resource(render_values(values, *args), "PrometheusRule", "scroll-monitor-dogeos")["spec"]["groups"]
            self.assertEqual(next(g for g in groups if g["name"] == "dogeos.metrics")["interval"], "15s")

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
    def test_normalized_pending_period_is_idempotent_and_can_return_to_default(self):
        cfg = {"folderUID": "test", "folderTitle": "Test", "datasourceUID": "prometheus",
               "groups": [{"name": "test", "rules": [{"alert": "Test", "expr": "up == 0", "for": "60s"}]}],
               "timingOverrides": {"Test": {"for": "60s"}}}
        client = MemoryGrafana()
        SEED.seed(client, cfg)
        client.group["rules"][0]["for"] = "1m"  # Grafana 11 API readback.
        client.writes.clear()
        SEED.seed(client, cfg)
        self.assertEqual(client.writes, [])
        cfg.pop("timingOverrides")
        cfg["groups"][0]["rules"][0]["for"] = "5m"
        SEED.seed(client, cfg)
        self.assertEqual(client.group["rules"][0]["for"], "5m")

    def test_legacy_string_baseline_migrates_without_overwriting_ui_edits(self):
        cfg = {"folderUID": "test", "folderTitle": "Test", "datasourceUID": "prometheus",
               "groups": [{"name": "test", "rules": [{"alert": "Test", "expr": "up == 0", "for": "5m"}]}]}
        for current, expected in (("5m", "7m"), ("19m", "19m")):
            with self.subTest(current=current):
                client = MemoryGrafana()
                SEED.seed(client, cfg)
                existing = client.group["rules"][0]
                baseline = json.loads(existing["annotations"][SEED.BASELINE])
                baseline["for"] = SEED.fingerprint("5m")
                existing["annotations"][SEED.BASELINE] = json.dumps(baseline)
                existing["for"] = current
                changed = copy.deepcopy(cfg)
                changed["groups"][0]["rules"][0]["for"] = "7m"
                SEED.seed(client, changed)
                self.assertEqual(client.group["rules"][0]["for"], expected)

    @unittest.skipUnless(os.environ.get("SCROLL_STATUS_RUNTIME_TEST") == "1", "requires Docker/Grafana")
    def test_real_grafana_normalization_and_group_interval(self):
        name = "scroll-monitor-timing-test-" + secrets.token_hex(6)
        password = secrets.token_hex(24)
        subprocess.run(["docker", "run", "--rm", "-d", "--name", name,
                        "-p", "127.0.0.1::3000", "-e", "GF_SECURITY_ADMIN_PASSWORD",
                        "-e", "GF_ANALYTICS_REPORTING_ENABLED=false", "grafana/grafana:11.1.5"],
                       env={**os.environ, "GF_SECURITY_ADMIN_PASSWORD": password},
                       check=True, stdout=subprocess.DEVNULL)
        self.addCleanup(lambda: subprocess.run(["docker", "rm", "-f", name],
                                              check=True, stdout=subprocess.DEVNULL))
        port = subprocess.check_output(["docker", "port", name, "3000/tcp"], text=True).strip().rsplit(":", 1)[1]
        url = "http://127.0.0.1:" + port
        for _ in range(60):
            try:
                with urlopen(url + "/api/health", timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            self.fail("Disposable Grafana did not become healthy")
        with patch.dict(os.environ, {"GRAFANA_URL": url, "GRAFANA_USER": "admin",
                                     "GRAFANA_PASSWORD": password, "GRAFANA_TOKEN": ""}):
            client = SEED.Grafana()
        client.request("POST", "/api/datasources", {"name": "test-prom", "uid": "test-prom", "type": "prometheus",
                                                 "access": "proxy", "url": "http://127.0.0.1:9090"})
        cfg = {"folderUID": "test", "folderTitle": "Test", "datasourceUID": "test-prom",
               "groups": [{"name": "test", "rules": [{"alert": "Test", "expr": "up == 0", "for": "60s"}]}],
               "timingOverrides": {"Test": {"for": "60s"}}, "groupIntervals": {"test": "30s"}}
        path = "/api/v1/provisioning/folder/test/rule-groups/test"
        SEED.seed(client, cfg)
        group = client.request("GET", path)
        self.assertEqual(group["interval"], 30)
        self.assertEqual(group["rules"][0]["for"], "1m")
        with patch.object(client, "request", wraps=client.request) as requests:
            SEED.seed(client, cfg)
            self.assertTrue(all(call.args[0] == "GET" for call in requests.call_args_list))
        cfg.pop("timingOverrides")
        cfg["groups"][0]["rules"][0]["for"] = "5m"
        SEED.seed(client, cfg)
        self.assertEqual(client.request("GET", path)["rules"][0]["for"], "5m")
        cfg["groupIntervals"]["test"] = "15s"
        with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
            SEED.seed(client, cfg)

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
