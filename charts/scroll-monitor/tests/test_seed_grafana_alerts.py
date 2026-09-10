import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/seed-grafana-alerts.py"
SPEC = importlib.util.spec_from_file_location("seed_grafana_alerts", SCRIPT)
SEED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEED)


class MemoryGrafana:
    """Model Grafana 11's distinct rule-create and group-update semantics."""

    def __init__(self):
        self.folder = None
        self.group = None
        self.writes = []

    def request(self, method, path, body=None, allow_missing=False):
        if method == "GET":
            result = self.folder if path.startswith("/api/folders/") else self.group
            return copy.deepcopy(result)
        self.writes.append((method, path, copy.deepcopy(body)))
        if path == "/api/folders":
            self.folder = copy.deepcopy(body)
        elif path == "/api/v1/provisioning/alert-rules":
            assert method == "POST"
            if self.group is None:
                self.group = {"interval": 60, "rules": []}
            assert body["uid"] not in {rule["uid"] for rule in self.group["rules"]}
            self.group["rules"].append(copy.deepcopy(body))
        else:
            assert method == "PUT"
            assert {r["uid"] for r in body["rules"]} <= {
                r["uid"] for r in self.group["rules"]
            }, "Group PUT cannot create a new rule with a supplied UID"
            self.group = copy.deepcopy(body)


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.client = MemoryGrafana()
        self.config = {
            "folderUID": "test-alerts",
            "folderTitle": "Test alerts",
            "datasourceUID": "custom-prometheus",
            "groups": [{"name": "dogeos.metrics", "rules": [{
                "alert": "NotReady", "expr": "max(ready) < 1", "for": "2m",
                "annotations": {"description": "{{ $labels.job }}: {{ $value }}"},
            }]}],
        }

    def test_new_rules_are_enabled_and_handle_zero_valued_alert_samples(self):
        SEED.seed(self.client, self.config)
        rule = self.client.group["rules"][0]
        self.assertFalse(rule["isPaused"])
        self.assertEqual(rule["for"], "2m")
        self.assertEqual(rule["noDataState"], "OK")
        self.assertEqual(rule["execErrState"], "Error")
        self.assertEqual(rule["data"][0]["datasourceUid"], "custom-prometheus")
        self.assertEqual(rule["data"][1]["model"]["expression"], "$A * 0 + 1")
        self.assertEqual(rule["annotations"]["description"],
                         "{{ $labels.job }}: {{ $values.A.Value }}")

    def test_repeated_upgrade_does_not_write(self):
        SEED.seed(self.client, self.config)
        self.client.writes.clear()
        SEED.seed(self.client, self.config)
        self.assertEqual(self.client.writes, [])

    def test_paused_rule_can_be_resumed_and_is_not_repaused_on_upgrade(self):
        self.config["groups"][0]["rules"][0]["isPaused"] = True
        SEED.seed(self.client, self.config)
        self.assertTrue(self.client.group["rules"][0]["isPaused"])
        self.client.group["rules"][0]["isPaused"] = False
        original = copy.deepcopy(self.client.group["rules"][0])
        self.client.writes.clear()
        self.config["groups"][0]["rules"].append({
            "alert": "NewPausedRule", "expr": "up == 0", "isPaused": True,
        })
        SEED.seed(self.client, self.config)
        self.assertEqual(self.client.group["rules"][0], original)
        self.assertTrue(self.client.group["rules"][1]["isPaused"])
        self.client.writes.clear()
        SEED.seed(self.client, self.config)
        self.assertEqual(self.client.writes, [])

    def test_new_default_does_not_unpause_an_operator_paused_rule(self):
        self.config["groups"][0]["rules"][0]["isPaused"] = True
        SEED.seed(self.client, self.config)
        self.config["groups"][0]["rules"][0]["isPaused"] = False
        self.client.writes.clear()
        SEED.seed(self.client, self.config)
        self.assertTrue(self.client.group["rules"][0]["isPaused"])
        self.assertEqual(self.client.writes, [])

    def test_log_alert_uses_loki_instant_query_and_no_pending_period(self):
        self.config["lokiDatasourceUID"] = "custom-loki"
        rule = SEED.alert_rule({
            "alert": "ServiceErrorOrPanickedLogs", "datasourceType": "loki",
            "expr": 'sum(count_over_time({namespace="monitoring"} |= "ERROR" [5m])) > 0',
        }, self.config, "dogeos.logs")
        self.assertEqual(rule["data"][0]["datasourceUid"], "custom-loki")
        self.assertEqual(rule["data"][0]["model"]["datasource"]["type"], "loki")
        self.assertEqual(rule["data"][0]["model"]["queryType"], "instant")
        self.assertEqual(rule["for"], "0s")

    def test_upgrade_preserves_edits_pause_and_interval_while_adding_rule(self):
        SEED.seed(self.client, self.config)
        edited = self.client.group["rules"][0]
        edited.update(isPaused=True, title="Operator title", **{"for": "15m"})
        edited["data"][0]["model"]["expr"] = "max(ready) < 0.5"
        edited["labels"]["team"] = "ops"
        edited["notification_settings"] = {"receiver": "slack-and-email"}
        self.client.group["interval"] = 120
        original = copy.deepcopy(edited)
        self.config["groups"][0]["rules"].append({"alert": "NewRule", "expr": "up == 0"})
        SEED.seed(self.client, self.config)
        self.assertEqual(self.client.group["rules"][0], original)
        self.assertEqual(self.client.group["interval"], 120)
        self.assertEqual(len(self.client.group["rules"]), 2)

    def test_retries_after_partial_import_do_not_duplicate_rules(self):
        SEED.seed(self.client, self.config)
        self.config["groups"][0]["rules"].extend([
            {"alert": "Second", "expr": "up == 0"},
            {"alert": "Third", "expr": "up == 0"},
        ])
        request = self.client.request

        def fail_third(method, path, body=None, **kwargs):
            if body and body.get("title") == "Third":
                raise RuntimeError("interrupted import")
            return request(method, path, body, **kwargs)

        with patch.object(self.client, "request", side_effect=fail_third):
            with self.assertRaisesRegex(RuntimeError, "interrupted import"):
                SEED.seed(self.client, self.config)
        SEED.seed(self.client, self.config)
        self.assertEqual(len(self.client.group["rules"]), 3)

    def test_api_provenance_is_cleared_without_resetting_paused_rule(self):
        SEED.seed(self.client, self.config)
        self.client.group["rules"][0].update(provenance="api", isPaused=True)
        self.client.group["interval"] = 120
        SEED.seed(self.client, self.config)
        self.assertNotIn("provenance", self.client.group["rules"][0])
        self.assertTrue(self.client.group["rules"][0]["isPaused"])
        self.assertEqual(self.client.group["interval"], 120)

    def test_file_provisioning_requires_removing_the_source(self):
        SEED.seed(self.client, self.config)
        self.client.group["rules"][0]["provenance"] = "file"
        self.client.writes.clear()
        with self.assertRaisesRegex(RuntimeError, "file-provisioned"):
            SEED.seed(self.client, self.config)
        self.assertEqual(self.client.writes, [])

    def test_api_client_disables_provenance_for_both_auth_methods(self):
        for credentials in [
            {"GRAFANA_TOKEN": "test-token"},
            {"GRAFANA_USER": "admin", "GRAFANA_PASSWORD": "test-password"},
        ]:
            with self.subTest(credentials=list(credentials)):
                with patch.dict("os.environ", {
                    "GRAFANA_URL": "http://grafana", **credentials,
                }, clear=True):
                    client = SEED.Grafana()
                self.assertEqual(client.headers["X-Disable-Provenance"], "true")
                self.assertIn("Authorization", client.headers)


if __name__ == "__main__":
    unittest.main()
