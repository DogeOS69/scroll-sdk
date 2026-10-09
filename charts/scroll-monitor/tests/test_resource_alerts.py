"""Resource classification, configuration, notification routing and validation."""
import json
import subprocess
import unittest

from test_monitoring_templates import CHART, grafana_rules, render, resource
from test_seed_grafana_alerts import MemoryGrafana, SEED


class ResourceAlertTests(unittest.TestCase):
    def test_resources_are_classified_active_and_scoped(self):
        rules = grafana_rules(render())
        resources = {n: r for n, r in rules.items() if r['labels'].get('alert_scope') == 'resources'}
        self.assertEqual(len(resources), 9)
        for name, rule in resources.items():
            self.assertFalse(rule.get('isPaused', False))
            self.assertIn(rule['labels']['alert_category'], ('memory', 'cpu', 'node-pressure'))
            self.assertNotIn('__', rule['expr'])
            if name.startswith('Container') and name != 'ContainerCPUThrottlingHigh':
                self.assertIn('namespace="monitoring"', rule['expr'])
            else:
                self.assertNotIn('namespace="monitoring"', rule['expr'])
        self.assertEqual(resources['NodeCPUUsageHigh']['for'], '15m')
        self.assertEqual(resources['NodeCPUUsageHigh']['labels']['severity'], 'warning')
        self.assertEqual(resources['NodeMemoryUsageHighCritical']['for'], '5m')
        self.assertIn('MemAvailable', resources['NodeMemoryUsageHigh']['expr'])
        self.assertIn('resource="memory", unit="byte"', resources['ContainerMemoryUsageHigh']['expr'])
        self.assertNotIn('resource_requests', resources['ContainerCPUUsageHigh']['expr'])

    def test_resource_switch_selectors_and_thresholds(self):
        self.assertFalse(any(r['labels'].get('alert_scope') == 'resources' for r in
                             grafana_rules(render('--set', 'resourceAlerts.enabled=false')).values()))
        rules = grafana_rules(render('--set', 'resourceAlerts.cpuWarningPercent=85',
                                     '--set', 'resourceAlerts.memoryCriticalFor=3m',
                                     '--set-string', 'businessPodAlerts.podNameRegex=worker-.*',
                                     '--set-string', 'businessPodAlerts.workloadNameRegex=worker.*',
                                     '--set-string', 'diskAlerts.excludeMountpointRegex=/readonly'))
        self.assertIn('>= 85', rules['NodeCPUUsageHigh']['expr'])
        self.assertEqual(rules['NodeMemoryUsageHighCritical']['for'], '3m')
        self.assertIn('pod=~"worker-.*"', rules['ContainerCPUUsageHigh']['expr'])
        self.assertNotIn('deployment=~"worker.*"', rules['BusinessDeploymentUnavailable']['expr'])
        self.assertIn('mountpoint!~"/readonly"', rules['NodeFilesystemReadOnly']['expr'])

    def test_invalid_threshold_order_and_durations_fail(self):
        options = ['resourceAlerts.nodeMemoryWarningPercent=96',
                   'resourceAlerts.containerMemoryCriticalPercent=80',
                   'resourceAlerts.cpuWarningPercent=101',
                   'resourceAlerts.memoryCriticalFor=0m',
                   'diskAlerts.criticalUsagePercent=70',
                   'diskAlerts.inodeWarningPercent=95',
                   'diskAlerts.predictionCriticalHours=24',
                   'diskAlerts.predictionWarningHours=abc',
                   'businessPodAlerts.workloadNameRegex=',
                   'businessPodAlerts.crashLoopFor=bad']
        for option in options:
            with self.subTest(option=option):
                result = subprocess.run(['helm', 'template', 'scroll-monitor', str(CHART),
                                         '--set-string', option], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(option.split('.')[0], result.stderr)

    def test_notification_groups_merge_symptoms_but_isolate_resources_and_severity(self):
        docs = render('-f', str(CHART / 'values/production.yaml'))
        config = json.loads(resource(docs, 'ConfigMap', 'scroll-monitor-grafana-alerts')['data']['rules.json'])
        self.assertEqual(config['resourceContactPoint'], 'slack-alerts')
        grouped = {}
        for group in config['groups']:
            for source in group['rules']:
                if source['labels'].get('alert_scope') not in ('resources', 'disks', 'business-pods'):
                    continue
                rule = SEED.alert_rule(source, config, group['name'])
                settings = SEED.notification_routes(config)[source["labels"]["alert_scope"]]
                self.assertIn("scroll_monitor_route", rule["labels"])
                self.assertNotIn("notification_settings", rule)
                self.assertEqual(settings['receiver'], 'slack-alerts')
                self.assertNotIn('alertname', settings['group_by'])
                self.assertTrue({'alert_category', 'severity'} <= set(settings['group_by']))
                self.assertEqual(settings["group_wait"], "30s")
                self.assertEqual(settings["routes"][0]["group_wait"], "0s")
                self.assertEqual(settings['group_interval'], '5m')
                self.assertEqual(settings['repeat_interval'], '4h')
                grouped[source['alert']] = settings
        self.assertEqual(grouped['BusinessPodContainerRestarted'], grouped['BusinessPodContainerFailed'])
        self.assertIn('container', grouped['ContainerMemoryUsageHigh']['group_by'])
        self.assertIn('deployment', grouped['BusinessDeploymentUnavailable']['group_by'])

    def test_resources_validate_slack_independently(self):
        client = MemoryGrafana()
        with self.assertRaisesRegex(RuntimeError, 'existing Grafana Slack contact'):
            SEED.seed(client, {'resourceContactPoint': 'slack-alerts'})
        self.assertEqual(client.writes, [])


if __name__ == '__main__':
    unittest.main()
