import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]


class StatusPageTests(unittest.TestCase):
    def fixture(self):
        env = {"secretKeyRef": {"name": "instatus-grafana-webhook", "key": "url"}}
        provisioning = {"apiVersion": 1, "contactPoints": [{
            "orgId": 1, "name": "instatus-public", "receivers": [{
                "uid": "instatus-public-webhook", "type": "webhook", "disableResolveMessage": False,
                "settings": {"httpMethod": "POST", "url": "$INSTATUS_GRAFANA_WEBHOOK_URL"},
            }],
        }]}
        return {
            "grafana": {"envValueFrom": {"INSTATUS_GRAFANA_WEBHOOK_URL": copy.deepcopy(env)},
                        "alerting": {"instatus-contact-points.yaml": copy.deepcopy(provisioning)}},
            "statusPage": {
                "enabled": True, "environment": "testnet",
                "catalog": {"groupName": "Testnet", "environment": "testnet", "components": [{"key": "public-rpc", "name": "Public RPC"}]},
                "generated": {"env": env, "provisioning": provisioning, "environment": "testnet", "version": 1},
            },
        }

    def publication_fixture(self, automatic=False):
        defaults = yaml.safe_load((CHART / "values.yaml").read_text())
        publication = copy.deepcopy(defaults["statusPage"]["publication"])
        for component in publication["components"].values():
            component["mode"] = "observe"  # This fixture explicitly opts out of the automatic default.
        publication["delivery"]["enabled"] = False
        publication["probes"]["mode"] = "external"  # This fixture exercises legacy external publication.
        key = "batch-publication"
        if automatic:
            publication["components"][key] = {"mode": "automatic", "rule": {"builtin": False, "expr": "fixture_health", "for": "5m"}}
        envs = {"INSTATUS_BATCH_PUBLICATION_WEBHOOK_URL": {"secretKeyRef": {"name": "instatus-batch-publication-webhook", "key": "url"}}} if automatic else {}
        provisioning = {"apiVersion": 1, "contactPoints": [], "groups": []}
        if automatic:
            provisioning["contactPoints"] = [{"orgId": 1, "name": "instatus-batch-publication", "receivers": [{
                "uid": "instatus-batch-publication", "type": "webhook", "disableResolveMessage": True,
                "settings": {"httpMethod": "POST", "url": "$INSTATUS_BATCH_PUBLICATION_WEBHOOK_URL"},
            }]}]
        return {
            "grafana": {"envValueFrom": copy.deepcopy(envs), "alerting": {"instatus-component-publication.yaml": copy.deepcopy(provisioning)}},
            "statusPage": {"enabled": True, "environment": "testnet", "publication": publication,
                "instatus": {"pageId": "page-1", "componentIds": {key: "batch-1"}},
                "catalog": {"groupName": "Testnet", "environment": "testnet", "components": [{"key": key, "name": "Batch Publication"}]},
                "generated": {"version": 2, "environment": "testnet",
                    "componentBindings": {key: {"pageId": "page-1", "componentId": "batch-1"}} if automatic else {},
                    "componentPublication": {"orgId": 1, "datasourceUid": "scroll-prometheus", "inputs": copy.deepcopy(publication), "envs": envs, "provisioning": provisioning, "readiness": {}}}},
        }

    def test_component_observation_requires_no_webhook_and_automatic_uses_only_its_secret(self):
        for automatic in [False, True]:
            result = self.render(self.publication_fixture(automatic))
            self.assertEqual(result.returncode, 0, result.stderr)
            docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
            deployment = next(doc for doc in docs if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "grafana")
            container = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "grafana")
            envs = [e for e in container["env"] if e["name"].startswith("INSTATUS_")]
            self.assertEqual(len(envs), 1 if automatic else 0)
            if automatic:
                self.assertEqual(envs[0]["valueFrom"]["secretKeyRef"]["name"], "instatus-batch-publication-webhook")

    def test_status_collectors_match_the_real_prometheus_discovery_selector(self):
        values = self.publication_fixture(True)
        status = values["statusPage"]
        publication = status["publication"]
        publication["delivery"]["enabled"] = True
        publication["nodeSync"]["mode"] = "official"
        status["catalog"]["chainId"] = "291"
        delivery = {"prometheusUrl": "http://prometheus-prometheus:9090", "orgId": 1,
                    "components": {"batch-publication": {"webhookEnv": "INSTATUS_BATCH_PUBLICATION_WEBHOOK_URL"}}}
        node = {"chainId": "291", "environment": "testnet",
                "reference": {"service": "sequencer", "port": 8545, "replicas": 1},
                "followers": [{"service": "rpc", "port": 8545, "replicas": 1}]}
        generated = status["generated"]
        generated.update(delivery=delivery, nodeSync=node)
        generated["componentPublication"].update(delivery=copy.deepcopy(delivery), nodeSync=copy.deepcopy(node),
                                                 inputs=copy.deepcopy(publication))
        result = self.render(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        spec = next(d for d in docs if d["kind"] == "Prometheus")["spec"]
        for name in ["scroll-monitor-status-node-sync", "scroll-monitor-status-delivery"]:
            monitor = next(d for d in docs if d["kind"] == "ServiceMonitor" and d["metadata"]["name"] == name)
            labels = monitor["metadata"]["labels"]
            for expression in spec["serviceMonitorSelector"]["matchExpressions"]:
                self.assertEqual(expression["operator"], "Exists")
                self.assertIn(expression["key"], labels)
            service = next(d for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == name)
            for key, value in monitor["spec"]["selector"]["matchLabels"].items():
                self.assertEqual(service["metadata"]["labels"][key], value)

    def test_component_publication_rejects_unapplied_binding_or_stale_mode(self):
        missing = self.publication_fixture(True)
        missing["statusPage"]["generated"]["componentBindings"] = {}
        cross_component = self.publication_fixture(True)
        cross_component["statusPage"]["instatus"]["componentIds"]["batch-publication"] = "another-component"
        stale = self.publication_fixture(True)
        stale["statusPage"]["publication"]["components"]["batch-publication"]["mode"] = "manual"
        for values in [missing, cross_component, stale]:
            result = self.render(values)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("statusPage", result.stderr)

    def render(self, values):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as file:
            yaml.safe_dump(values, file)
            file.flush()
            return subprocess.run(["helm", "template", "scroll-monitor", str(CHART),
                                   "--namespace", "monitoring", "-f", file.name],
                                  text=True, capture_output=True)

    def test_generated_contract_renders_catalog_and_native_secret_backed_contact_point(self):
        result = self.render(self.fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
        catalog = next(doc for doc in docs if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "scroll-monitor-status-page")
        self.assertEqual(json.loads(catalog["data"]["catalog.json"])["environment"], "testnet")
        deployment = next(doc for doc in docs if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "grafana")
        container = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "grafana")
        env = next(e for e in container["env"] if e["name"] == "INSTATUS_GRAFANA_WEBHOOK_URL")
        self.assertEqual(env["valueFrom"]["secretKeyRef"], {"name": "instatus-grafana-webhook", "key": "url"})
        self.assertNotIn("INSTATUS_API_KEY", result.stdout)
        self.assertFalse(any("publisher" in doc["metadata"]["name"] for doc in docs))

    def test_defaults_are_disabled_and_examples_match(self):
        defaults = yaml.safe_load((CHART / "values.yaml").read_text())["statusPage"]
        self.assertFalse(defaults["enabled"])
        self.assertTrue(all(c["mode"] == "automatic" for c in defaults["publication"]["components"].values()))
        self.assertEqual(defaults["publication"]["health"], {})
        for profile in [CHART / "values/production.yaml", CHART.parents[1] / "examples/values/scroll-monitor-production.yaml"]:
            self.assertEqual(yaml.safe_load(profile.read_text())["statusPage"], defaults)
        result = self.render({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("catalog.json:", result.stdout)

    def test_helm_rejects_stale_or_missing_generation(self):
        missing = {"statusPage": {"enabled": True, "environment": "testnet"}}
        environment = self.fixture()
        environment["statusPage"]["environment"] = "mainnet"
        secret = self.fixture()
        secret["grafana"]["envValueFrom"]["INSTATUS_GRAFANA_WEBHOOK_URL"]["secretKeyRef"]["name"] = "changed"
        disabled = self.fixture()
        disabled["statusPage"]["enabled"] = False
        identity = self.fixture()
        identity["statusPage"]["grafana"] = {"orgId": 2}
        group = self.fixture()
        group["statusPage"]["catalog"]["groupName"] = "Mainnet"
        for values in [missing, environment, secret, disabled, identity, group]:
            with self.subTest(values=values["statusPage"]):
                result = self.render(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("statusPage", result.stderr)


if __name__ == "__main__":
    unittest.main()
