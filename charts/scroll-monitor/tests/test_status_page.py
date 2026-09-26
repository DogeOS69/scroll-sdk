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
                "catalog": {"environment": "testnet", "components": [{"key": "public-rpc", "name": "Public RPC"}]},
                "generated": {"env": env, "provisioning": provisioning, "environment": "testnet", "version": 1},
            },
        }

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
        for values in [missing, environment, secret, disabled, identity]:
            with self.subTest(values=values["statusPage"]):
                result = self.render(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("statusPage", result.stderr)


if __name__ == "__main__":
    unittest.main()
