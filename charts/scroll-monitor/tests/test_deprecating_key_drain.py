"""Render both shipped backends and evaluate the deprecating-key drain rules with promtool."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_monitoring_templates import render, resource, grafana_rules

NAMES = {'DeprecatingKeyDrainBehind', 'RetiredKeyCoinsStranded'}
PREFIX = 'withdrawal_processor_protocol_'
TARGET = {'namespace': 'monitoring', 'job': 'withdrawal-processor', 'instance': 'wp'}
EVAL = 10  # minutes


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


def annotations(rule, value):
    # Mirrors the shipped `{{ $value | printf "%.0f" }}` rendering.
    return {k: v.replace('{{ $value | printf "%.0f" }}', f'{float(value):.0f}')
            for k, v in rule['annotations'].items()}


class DeprecatingKeyDrainTests(unittest.TestCase):
    def test_shared_backends_values_and_existing_routing(self):
        prom = rules()
        grafana = rules('grafana')
        self.assertEqual(set(prom), NAMES)
        for name in NAMES:
            for field in ('expr', 'for', 'labels', 'annotations'):
                self.assertEqual(prom[name][field], grafana[name][field])
            self.assertNotIn('contactPoint', grafana[name])
            self.assertNotIn('__', prom[name]['expr'] + str(prom[name]['annotations']))
            self.assertIn('rotation-and-recovery-operations.md#deprecating-key-drain-monitor',
                          prom[name]['annotations']['runbook_url'])
        self.assertIn('< 2 * withdrawal_processor_protocol_deprecating_key_unspent_utxos',
                      prom['DeprecatingKeyDrainBehind']['expr'])
        self.assertIn('unspent_utxos > 0)', prom['RetiredKeyCoinsStranded']['expr'])
        custom = rules('prometheus', '--set', 'deprecatingKeyDrainAlerts.drainMargin=3',
                       '--set', 'deprecatingKeyDrainAlerts.retiredBaseline=4')
        self.assertIn('< 3 * withdrawal_processor_protocol_deprecating_key_unspent_utxos',
                      custom['DeprecatingKeyDrainBehind']['expr'])
        self.assertIn('fewer than 3 WF', custom['DeprecatingKeyDrainBehind']['annotations']['description'])
        self.assertIn('unspent_utxos > 4)', custom['RetiredKeyCoinsStranded']['expr'])
        self.assertFalse(rules('prometheus', '--set', 'serviceAlerts.enabled=false'))

    def test_invalid_values_fail_at_render_time(self):
        for setting in ('deprecatingKeyDrainAlerts.drainMargin=0', 'deprecatingKeyDrainAlerts.retiredBaseline=-1',
                        'deprecatingKeyDrainAlerts.runbookUrl='):
            with self.subTest(setting=setting), self.assertRaises(subprocess.CalledProcessError):
                render('--set', setting)

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_real_promql_boundaries_and_freshness(self):
        shipped = rules()
        cases = []
        fresh = f'0+60x{EVAL}'

        def check(name, coins, remaining, retired=0, timestamp=fresh, expected=()):
            series = [{'series': PREFIX + k + labels(TARGET), 'values': f'{v}x{EVAL}'}
                      for k, v in (('deprecating_key_unspent_utxos', coins),
                                   ('deprecating_key_remaining_wf_txs', remaining),
                                   ('retired_key_unspent_utxos', retired))]
            series.append({'series': PREFIX + 'snapshot_timestamp_seconds' + labels({**TARGET, 'source': 'deprecating_key'}),
                           'values': timestamp})
            # Other snapshot sources stay fresh; they must not stand in for this one.
            series.append({'series': PREFIX + 'snapshot_timestamp_seconds' + labels({**TARGET, 'source': 'jobs'}),
                           'values': fresh})
            value = {'DeprecatingKeyDrainBehind': coins, 'RetiredKeyCoinsStranded': retired}
            cases.append({'name': name, 'interval': '1m', 'input_series': series,
                          'alert_rule_test': [{
                              'eval_time': f'{EVAL}m', 'alertname': alert,
                              'exp_alerts': [{'exp_labels': {**TARGET, **shipped[alert]['labels']},
                                              'exp_annotations': annotations(shipped[alert], value[alert])}]
                              if alert in expected else []} for alert in sorted(NAMES)]})

        check('no deprecating key is quiet', 0, 0)
        check('healthy drain is quiet', 3, 20)
        check('margin boundary is quiet', 5, 10)
        check('below margin warns', 5, 9, expected=('DeprecatingKeyDrainBehind',))
        check('one coin, one WF tx left warns', 1, 1, expected=('DeprecatingKeyDrainBehind',))
        # At remaining 0 the coins count as retired; the critical takes over.
        check('no WF tx left hands over to stranded', 3, 0, retired=3, expected=('RetiredKeyCoinsStranded',))
        check('coins left after the key clears', 0, 0, retired=2, expected=('RetiredKeyCoinsStranded',))
        # Last success 1000s before the evaluation: past the 900s freshness window.
        check('stale observation is quiet', 5, 1, retired=2, timestamp=f'-400x{EVAL}')
        with tempfile.TemporaryDirectory(prefix='drain-promql-') as directory:
            root = Path(directory)
            root.chmod(0o755)
            (root/'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'drain', 'rules': list(shipped.values())}]}))
            (root/'tests.yaml').write_text(yaml.safe_dump({'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': cases}))
            (root/'rules.yaml').chmod(0o644)
            (root/'tests.yaml').chmod(0o644)
            subprocess.run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'promtool',
                            '-v', f'{root}:/work:ro', 'prom/prometheus:v3.16.0',
                            'test', 'rules', '/work/tests.yaml'], check=True)
