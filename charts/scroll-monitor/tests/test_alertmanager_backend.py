"""Ownership, pause preservation and portable notification routing."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
import yaml
from test_monitoring_templates import render, resource

CHART = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('seed', CHART / 'scripts/seed-grafana-alerts.py')
SEED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEED)
FLAGS = ['--set', 'alerting.backend=prometheus', '--set',
         'kube-prometheus-stack.alertmanager.alertmanagerSpec.useExistingSecret=true',
         '--set', 'kube-prometheus-stack.alertmanager.alertmanagerSpec.configSecret=scroll-monitor-alertmanager-config']

class BackendTests(unittest.TestCase):
    def test_metric_owner_and_paused_rules(self):
        docs = render(*FLAGS, '--set', 'grafanaAlerting.pauseRules.AttestationSignerNotReady=true')
        rules = resource(docs, 'PrometheusRule', 'scroll-monitor-dogeos')['spec']['groups']
        names = {r['alert'] for g in rules for r in g['rules']}
        self.assertIn('L2BatchHeightStalled', names)
        self.assertNotIn('AttestationSignerNotReady', names)
        self.assertNotIn('ServiceErrorOrPanickedLogs', names)
        config = json.loads(resource(docs, 'ConfigMap', 'scroll-monitor-grafana-alerts')['data']['rules.json'])
        self.assertEqual([r['alert'] for g in config['groups'] for r in g['rules']], ['ServiceErrorOrPanickedLogs'])
        self.assertIn('forwardAlertmanager', config)
        self.assertNotIn('defaultContactPoint', config)
        ds = yaml.safe_load(resource(docs, 'ConfigMap', 'grafana-datasources-config')['data']['datasources.yaml'])
        self.assertEqual(next(x for x in ds['datasources'] if x['type']=='alertmanager')['jsonData']['implementation'], 'prometheus')
        self.assertIs(next(x for x in ds['datasources'] if x['type'] == 'loki')['jsonData']['manageAlerts'], False)
        self.assertIs(next(x for x in ds['datasources'] if x['type'] == 'prometheus')['jsonData']['manageAlerts'], True)

    def test_optional_slack_is_valid_empty_receiver(self):
        docs = render(*FLAGS)
        data = resource(docs, 'Secret', 'scroll-monitor-alertmanager-config')['stringData']
        cfg = yaml.safe_load(data['alertmanager.yaml'])
        self.assertEqual(next(r for r in cfg['receivers'] if r['name']=='slack-alerts'), {'name':'slack-alerts'})
        self.assertNotIn('slack_api_url', cfg['global'])
        self.assertNotIn('.SilenceURL', data['notifications.tmpl'])

    def test_slack_uses_mounted_secret_file(self):
        docs=render(*FLAGS, '--set', 'alerting.alertmanager.slack.existingSecret=test-slack',
                    '--set', 'kube-prometheus-stack.alertmanager.alertmanagerSpec.secrets[0]=test-slack')
        data=resource(docs, 'Secret', 'scroll-monitor-alertmanager-config')['stringData']
        cfg=yaml.safe_load(data['alertmanager.yaml'])
        slack=next(r for r in cfg['receivers'] if r['name']=='slack-alerts')['slack_configs'][0]
        self.assertEqual(slack['api_url_file'], '/etc/alertmanager/secrets/test-slack/url')

    def test_slack_links_use_grafana_without_internal_fallback(self):
        for url in ('https://grafana.example.invalid/monitoring/', ''):
            with self.subTest(url=url):
                docs = render(*FLAGS, '--set', 'alerting.alertmanager.slack.existingSecret=test-slack',
                              '--set', 'kube-prometheus-stack.alertmanager.alertmanagerSpec.secrets[0]=test-slack',
                              '--set-string', 'alerting.alertmanager.grafanaURL=' + url)
                data = resource(docs, 'Secret', 'scroll-monitor-alertmanager-config')['stringData']
                cfg = yaml.safe_load(data['alertmanager.yaml'])
                slack = next(r for r in cfg['receivers'] if r['name'] == 'slack-alerts')['slack_configs'][0]
                self.assertEqual(slack['title_link'], '{{ template "scroll-monitor.slack.titlelink" . }}')
                template = data['notifications.tmpl']
                self.assertNotIn('.GeneratorURL', template)
                self.assertNotIn('.ExternalURL', template)
                self.assertNotIn('__GRAFANA_URL__', template)
                self.assertIn('.CommonLabels.alertname', template)
                self.assertIn('urlquery', template)
                if url:
                    self.assertIn(url.rstrip('/') + '/alerting/list', template)
                    self.assertIn(url.rstrip('/') + '/alerting/silence/new?alertmanager=Alertmanager', template)
                    self.assertNotIn('/monitoring//', template)
                else:
                    self.assertIn('{{ if "" }}', template)

    def test_forwarding_is_idempotent_and_sends_recovery(self):
        client=Mock();client.request.return_value=[]
        spec={'uid':'external', 'name':'external', 'url':'http://alertmanager:9093'}
        SEED.seed_forwarder(client,spec)
        desired=client.request.call_args.args[2]
        self.assertEqual(desired['type'],'prometheus-alertmanager')
        self.assertFalse(desired['disableResolveMessage'])
        desired["settings"]["basicAuthPassword"]="[REDACTED]"
        client.reset_mock();client.request.return_value=[desired]
        SEED.seed_forwarder(client,spec)
        self.assertEqual(client.request.call_count,1)

    def test_existing_log_rule_switches_only_explicit_routing(self):
        source={'alert':'TestLogs', 'expr':'sum(count_over_time({app="test"}[5m])) > 0'}
        config={'folderUID':'test', 'datasourceUID':'test'}
        current=SEED.alert_rule(source,config,'logs')
        current['isPaused']=True
        config['forwardAlertmanager']={'name':'external'}
        desired=SEED.alert_rule(source,config,'logs')
        changed=SEED.reconcile_rule(current,source,desired)
        self.assertTrue(changed['isPaused'])
        self.assertEqual(changed['data'],current['data'])
        self.assertEqual(changed['notification_settings'],{'receiver':'external', 'group_wait':'0s', 'group_interval':'10s', 'repeat_interval':'1m'})

if __name__=='__main__': unittest.main()
