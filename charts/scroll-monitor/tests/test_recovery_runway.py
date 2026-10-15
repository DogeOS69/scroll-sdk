"""Render both shipped backends and evaluate actual runway expressions with promtool."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_monitoring_templates import render, resource, grafana_rules

NAMES = {'RecoveryRunwayWarning', 'RecoveryRunwayCritical', 'RecoveryRunwayObservationUnknown'}
PREFIX = 'withdrawal_processor_recovery_runway_'
TARGET = {'namespace': 'monitoring', 'job': 'withdrawal-processor', 'instance': 'wp'}


def labels(values):
    return '{' + ','.join(f'{k}="{v}"' for k, v in sorted(values.items())) + '}'


def rules(backend='prometheus', *args):
    flags = ['--set', 'alerting.backend=' + backend]
    if backend == 'prometheus':
        flags += ['--set', 'kube-prometheus-stack.alertmanager.alertmanagerSpec.useExistingSecret=true',
                  '--set', 'kube-prometheus-stack.alertmanager.alertmanagerSpec.configSecret=scroll-monitor-alertmanager-config']
    docs = render(*flags, *args)
    if backend == 'grafana':
        return {k: v for k, v in grafana_rules(docs).items() if k in NAMES}
    groups = resource(docs, 'PrometheusRule', 'scroll-monitor-dogeos')['spec']['groups']
    return {r['alert']: r for g in groups for r in g['rules'] if r.get('alert') in NAMES}


class RecoveryRunwayTests(unittest.TestCase):
    def test_shared_backends_thresholds_and_existing_routing(self):
        prom = rules()
        grafana = rules('grafana')
        self.assertEqual(set(prom), NAMES)
        for name in NAMES:
            for field in ('expr', 'for', 'labels', 'annotations'):
                self.assertEqual(prom[name][field], grafana[name][field])
            self.assertNotIn('contactPoint', grafana[name])
        custom = rules('prometheus', '--set', 'recoveryRunwayAlerts.warningBlocks=200000',
                       '--set', 'recoveryRunwayAlerts.criticalBlocks=100000',
                       '--set-string', 'recoveryRunwayAlerts.jobRegex=wp-mainnet')
        self.assertIn('<= 200000', custom['RecoveryRunwayWarning']['expr'])
        self.assertIn('<= 100000', custom['RecoveryRunwayCritical']['expr'])
        self.assertIn('job=~"wp-mainnet"', custom['RecoveryRunwayObservationUnknown']['expr'])
        self.assertFalse(rules('prometheus', '--set', 'serviceAlerts.enabled=false'))

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_real_promql_boundaries_unknown_and_quiet_inventory(self):
        shipped = rules()
        cases = []

        def check(name, runway, known=1, complete=1, timestamp='0+60x10', up=1,
                  missing=(), expected=()):
            values = {'known_valid': str(known)+'x10', 'inventory_complete': str(complete)+'x10',
                      'timestamp_seconds': timestamp, 'minimum_blocks': ' '.join(['NaN'] * 11) if runway == 'NaN' else str(runway)+'x10'}
            series = [{'series': PREFIX+k+labels(TARGET), 'values': v}
                      for k, v in values.items() if k not in missing]
            series.append({'series': 'up'+labels(TARGET), 'values': str(up)+'x10'})
            tests = []
            for alert, rule in shipped.items():
                active = alert in expected
                metric = 'up' if alert == 'RecoveryRunwayObservationUnknown' else PREFIX+'minimum_blocks'
                value = up if metric == 'up' else runway
                tests.append({'expr': rule['expr'], 'eval_time': '8m',
                              'exp_samples': [{'labels': metric+labels(TARGET), 'value': value}] if active else []})
            cases.append({'name': name, 'interval': '1m', 'input_series': series,
                          'promql_expr_test': tests,
                          'alert_rule_test': [{'eval_time': '8m', 'alertname': alert,
                                               'exp_alerts': [{'exp_labels': {**TARGET, **shipped[alert]['labels']},
                                                               'exp_annotations': {k: v.replace('{{ $value }}', str(up if alert == 'RecoveryRunwayObservationUnknown' else runway))
                                                                                   for k, v in shipped[alert]['annotations'].items()}}] if alert in expected else []}
                                              for alert in NAMES]})

        check('warning inclusive boundary', 129600, expected=('RecoveryRunwayWarning',))
        check('above warning', 129601)
        check('critical inclusive boundary', 86400, expected=('RecoveryRunwayCritical',))
        check('above critical', 86401, expected=('RecoveryRunwayWarning',))
        check('exact expiry', 0, expected=('RecoveryRunwayCritical',))
        check('expired retired funded script', -12, expected=('RecoveryRunwayCritical',))
        check('known hazard with unverified inventory', -12, complete=0,
              expected=('RecoveryRunwayCritical', 'RecoveryRunwayObservationUnknown'))
        check('complete empty inventory quiet', 'NaN')
        check('unverified empty inventory unknown', 'NaN', complete=0,
              expected=('RecoveryRunwayObservationUnknown',))
        for name, overrides in [
            ('failed observation', {'known': 0}), ('stale source', {'timestamp': '0x10'}),
            ('future source', {'timestamp': '10000x10'}), ('scrape failure', {'up': 0}),
            ('missing timestamp', {'missing': ('timestamp_seconds',)}),
            ('old image missing all facts', {'missing': ('known_valid', 'inventory_complete', 'timestamp_seconds', 'minimum_blocks')}),
        ]:
            check(name, 1, expected=('RecoveryRunwayObservationUnknown',), **overrides)
        with tempfile.TemporaryDirectory(prefix='runway-promql-') as directory:
            root = Path(directory)
            root.chmod(0o755)
            (root/'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'runway', 'rules': list(shipped.values())}]}))
            (root/'tests.yaml').write_text(yaml.safe_dump({'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': cases}))
            subprocess.run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'promtool',
                            '-v', f'{root}:/work:ro', 'prom/prometheus:v2.52.0',
                            'test', 'rules', '/work/tests.yaml'], check=True)
