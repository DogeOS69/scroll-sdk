import copy
import json
import os
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

    def collector_fixture(self):
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
        return values

    def test_delivery_resources_can_change_without_regenerating_publication(self):
        values = self.collector_fixture()
        status = values["statusPage"]
        # Existing generated snapshots predate configurable container resources.
        status["generated"]["componentPublication"]["inputs"]["delivery"].pop("resources", None)
        status["publication"]["delivery"]["resources"] = {
            "requests": {"cpu": "150m"}, "limits": {"cpu": "750m"}}
        result = self.render(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        deployment = next(d for d in docs if d["kind"] == "Deployment"
                          and d["metadata"]["name"] == "scroll-monitor-status-delivery")
        self.assertEqual(deployment["spec"]["template"]["spec"]["containers"][0]["resources"], {
            "requests": {"cpu": "150m", "memory": "64Mi"},
            "limits": {"cpu": "750m", "memory": "256Mi"}})
        # The exemption must not allow publication-policy drift.
        status["publication"]["components"]["batch-publication"]["mode"] = "manual"
        result = self.render(values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("component publication changed", result.stderr)

    def test_status_collectors_match_the_real_prometheus_discovery_selector(self):
        values = self.collector_fixture()
        result = self.render(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        delivery_cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "scroll-monitor-status-delivery")
        shared = json.loads(delivery_cm["data"]["l2-batch-progress.json"])
        alert_cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "scroll-monitor-grafana-alerts")
        groups = json.loads(alert_cm["data"]["rules.json"])["groups"]
        alert = next(r for g in groups for r in g["rules"] if r["alert"] == "L2BatchHeightStalled")
        expr = shared["expr"].replace("__SELECTOR__", shared["selector"]).replace("__LABELS__", "namespace, job").replace("__WINDOW__", f'{shared["windowSeconds"]}s')
        self.assertEqual(alert["expr"], f"({expr}) == 0")
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

    def test_l2_stall_window_updates_alerts_runtime_and_rollout_checksum(self):
        checksums = []
        for seconds in (600, 7500, 9000):
            with self.subTest(seconds=seconds):
                values = self.collector_fixture()
                values['businessAlerts'] = {'l2BatchStallSeconds': seconds}
                result = self.render(values)
                self.assertEqual(result.returncode, 0, result.stderr)
                docs = [d for d in yaml.safe_load_all(result.stdout) if d]
                data = next(d['data'] for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'scroll-monitor-status-delivery')
                shared = json.loads(data['l2-batch-progress.json'])
                self.assertEqual(shared['windowSeconds'], seconds)
                seed = next(d['data'] for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'scroll-monitor-grafana-alerts')
                rule = next(r for g in json.loads(seed['rules.json'])['groups'] for r in g['rules'] if r['alert'] == 'L2BatchHeightStalled')
                self.assertIn(f'[{seconds}s:1m]', rule['expr'])
                self.assertIn(f'offset {seconds}s', rule['expr'])
                for text in rule['annotations'].values():
                    self.assertIn(f'{seconds} seconds', text)
                deploy = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'scroll-monitor-status-delivery')
                checksums.append(deploy['spec']['template']['metadata']['annotations']['checksum/script'])
        self.assertEqual(len(set(checksums)), 3)

    def test_l2_stall_window_rejects_invalid_values(self):
        for seconds in (0, -1, 59, 60.5, True, '7500', None):
            with self.subTest(seconds=seconds):
                values = self.collector_fixture()
                values['businessAlerts'] = {'l2BatchStallSeconds': seconds}
                result = self.render(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('businessAlerts.l2BatchStallSeconds must be an integer of at least 60 seconds', result.stderr)

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_rendered_l2_alert_uses_custom_deadline(self):
        values = self.collector_fixture()
        values['businessAlerts'] = {'l2BatchStallSeconds': 600}
        result = self.render(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        seed = next(d['data'] for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'scroll-monitor-grafana-alerts')
        rule = next(r for g in json.loads(seed['rules.json'])['groups'] for r in g['rules'] if r['alert'] == 'L2BatchHeightStalled')
        fixture = {'rule_files': [], 'evaluation_interval': '1m', 'tests': [{
            'interval': '1m', 'input_series': [{
                'series': 'withdrawal_processor_protocol_state_l2_batch_height{namespace="monitoring",job="withdrawal-processor"}',
                'values': '10x10 11x9'}],
            'promql_expr_test': [{'expr': rule['expr'], 'eval_time': at,
                'exp_samples': [{'labels': '{namespace="monitoring",job="withdrawal-processor"}', 'value': 0}] if at == '10m' else []}
                for at in ('9m', '10m', '11m')]}]}
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'tests.json').write_text(json.dumps(fixture))
            result = subprocess.run(['docker', 'run', '--rm', '--user', str(os.getuid()), '--entrypoint', 'promtool',
                '-v', root+':/fixtures:ro', 'prom/prometheus:v2.52.0', 'test', 'rules', '/fixtures/tests.json'],
                text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

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
