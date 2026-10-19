"""Render both shipped backends and evaluate actual runway rules with promtool."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_monitoring_templates import render, resource, grafana_rules

NAMES = {'RecoveryRunwayWarning', 'RecoveryRunwayCritical', 'RecoveryRunwayObservationStale'}
PREFIX = 'withdrawal_processor_recovery_runway_'
TARGET = {'namespace': 'monitoring', 'job': 'withdrawal-processor', 'instance': 'wp'}
EVAL = 25  # minutes


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


def annotations(rule, runway):
    # Mirrors the shipped `{{ $value | printf "%.0f" }}` rendering.
    return {k: v.replace('{{ $value | printf "%.0f" }}', f'{float(runway):.0f}')
            for k, v in rule['annotations'].items()}


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
                       '--set', 'recoveryRunwayAlerts.criticalBlocks=100000')
        self.assertIn('<= 200000', custom['RecoveryRunwayWarning']['expr'])
        self.assertIn('<= 100000', custom['RecoveryRunwayCritical']['expr'])
        self.assertFalse(rules('prometheus', '--set', 'serviceAlerts.enabled=false'))

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_real_promql_boundaries_and_stale_monitor(self):
        shipped = rules()
        cases = []
        fresh = f'0+60x{EVAL}'

        def check(name, runway, valid=f'1x{EVAL}', timestamp=fresh, expected=(), runway_metrics=True):
            minimum = ' '.join(['NaN'] * (EVAL + 1)) if runway == 'NaN' else f'{runway}x{EVAL}'
            series = [{'series': PREFIX + k + labels(TARGET), 'values': v}
                      for k, v in (('minimum_blocks', minimum), ('observation_valid', valid),
                                   ('timestamp_seconds', timestamp)) if runway_metrics]
            # Every WP target exports protocol metrics; a healthy replica stays quiet.
            healthy = {**TARGET, 'instance': 'wp-healthy'}
            series += [{'series': 'withdrawal_processor_protocol_snapshot_valid' + labels({**t, 'source': 'jobs'}),
                        'values': f'1x{EVAL}'} for t in (TARGET, healthy)]
            series += [{'series': PREFIX + k + labels(healthy), 'values': v}
                       for k, v in (('minimum_blocks', 'NaN ' * EVAL + 'NaN'),
                                    ('observation_valid', f'1x{EVAL}'), ('timestamp_seconds', fresh))]
            cases.append({'name': name, 'interval': '1m', 'input_series': series,
                          'alert_rule_test': [{
                              'eval_time': f'{EVAL}m', 'alertname': alert,
                              'exp_alerts': [{'exp_labels': {**TARGET, **shipped[alert]['labels']},
                                              'exp_annotations': annotations(shipped[alert], runway)}]
                              if alert in expected else []} for alert in sorted(NAMES)]})

        check('warning inclusive boundary', 129600, expected=('RecoveryRunwayWarning',))
        check('above warning', 129601)
        check('critical inclusive boundary', 86400, expected=('RecoveryRunwayCritical',))
        check('above critical', 86401, expected=('RecoveryRunwayWarning',))
        check('exact expiry', 0, expected=('RecoveryRunwayCritical',))
        check('expired retired funded script', -12, expected=('RecoveryRunwayCritical',))
        check('nothing funded is quiet', 'NaN')
        # The success timestamp freezes at the last good observation.
        check('failed observations keep the last good hazard', -12,
              valid=f'1x{EVAL - 2} 0 0', timestamp=f'0+60x{EVAL - 2} 1380 1380',
              expected=('RecoveryRunwayCritical',))
        check('hazard stays up until the stale alert takes over', -12,
              valid=f'1x11 0x{EVAL - 11}', timestamp=f'0+60x11 660x{EVAL - 11}',
              expected=('RecoveryRunwayCritical', 'RecoveryRunwayObservationStale'))
        check('hazard older than 15 minutes hands over to stale', -12,
              valid=f'1x9 0x{EVAL - 9}', timestamp=f'0+60x9 540x{EVAL - 9}',
              expected=('RecoveryRunwayObservationStale',))
        check('stale success timestamp', 1, timestamp=f'0x{EVAL}',
              expected=('RecoveryRunwayObservationStale',))
        check('runway metrics missing from a scraped WP', 1, runway_metrics=False,
              expected=('RecoveryRunwayObservationStale',))
        # A stalled task can keep exposing valid=1 while its success timestamp
        # freezes. Check the handover itself, not just the eventual stale alert.
        for offset in (0, 30):
            cases.append({'name': f'stalled observer handover, timestamp offset {offset}s',
                          'interval': '1m',
                          'input_series': [{'series': PREFIX + k + labels(TARGET), 'values': v}
                                           for k, v in (
                                               ('minimum_blocks', '-12x25'),
                                               ('observation_valid', '1x25'),
                                               ('timestamp_seconds', f'{offset}x25'))],
                          'alert_rule_test': [
                              {'eval_time': f'{minute}m', 'alertname': alert,
                               'exp_alerts': [{'exp_labels': {**TARGET, **shipped[alert]['labels']},
                                               'exp_annotations': annotations(shipped[alert], -12)}]
                               if fires else []}
                              for minute in (10, 14, 15, 16, 20, 21)
                              for alert, fires in (
                                  ('RecoveryRunwayCritical', minute * 60 - offset < 900),
                                  ('RecoveryRunwayObservationStale', minute * 60 - offset >= 900))]})
        with tempfile.TemporaryDirectory(prefix='runway-promql-') as directory:
            root = Path(directory)
            root.chmod(0o755)
            (root/'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'runway', 'rules': list(shipped.values())}]}))
            (root/'tests.yaml').write_text(yaml.safe_dump({'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': cases}))
            (root/'rules.yaml').chmod(0o644)
            (root/'tests.yaml').chmod(0o644)
            subprocess.run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'promtool',
                            '-v', f'{root}:/work:ro', 'prom/prometheus:v2.52.0',
                            'test', 'rules', '/work/tests.yaml'], check=True)
