"""Render both backends and evaluate the withdrawal bound rules with promtool."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_monitoring_templates import CHART, render, resource, grafana_rules

NAMES = {'WithdrawalBacklogAboveDALimit', 'WithdrawalBacklogPastOnePayDown', 'WithdrawalBacklogUnobserved',
         'AdvanceL2AdoptionDelayed', 'EthDASingleBlockOverWithdrawalLimit'}
BACKLOG = 'withdrawal_processor_public_withdrawal_backlog_lower_bound'
SNAPSHOT = 'withdrawal_processor_protocol_snapshot_'
DA_HEIGHT = 'withdrawal_processor_protocol_latest_da_batch_height'
ADOPTED = 'withdrawal_processor_protocol_state_l2_batch_height'
COUNTER = 'eth_da_submitter_single_block_over_withdrawal_limit_total'
WP = {'namespace': 'monitoring', 'job': 'withdrawal-processor', 'instance': 'wp'}
DA = {'namespace': 'monitoring', 'job': 'eth-da-submitter', 'instance': 'da'}
END = 200  # minutes of input


def labels(values):
    return '{' + ','.join(f'{k}="{v}"' for k, v in sorted(values.items())) + '}'


def series(name, target, values):
    return {'series': name + labels(target), 'values': values}


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


def backlog(count, valid=f'1x{END}', timestamp=f'0+60x{END}', up=f'1x{END}'):
    return [series(BACKLOG, WP, count), series(BACKLOG + '_valid', WP, valid),
            series(BACKLOG + '_timestamp_seconds', WP, timestamp), series('up', WP, up)]


def heights(published, adopted, target=WP, replay_valid=f'1x{END}'):
    fresh = f'0+60x{END}'
    # A healthy backlog observation keeps WithdrawalBacklogUnobserved out of these cases.
    return [series(DA_HEIGHT, target, published), series(ADOPTED, target, adopted),
            *[{**s, 'series': s['series'].replace(labels(WP), labels(target))} for s in backlog(f'0x{END}')],
            series(SNAPSHOT + 'valid', {**target, 'source': 'l2'}, f'1x{END}'),
            series(SNAPSHOT + 'timestamp_seconds', {**target, 'source': 'l2'}, fresh),
            series(SNAPSHOT + 'valid', {**target, 'source': 'replay'}, replay_valid),
            series(SNAPSHOT + 'timestamp_seconds', {**target, 'source': 'replay'}, fresh)]


class WithdrawalBoundTests(unittest.TestCase):
    def test_shared_backends_thresholds_and_switches(self):
        prom = rules()
        grafana = rules('grafana')
        self.assertEqual(set(prom), NAMES)
        for name in NAMES:
            for field in ('expr', 'labels', 'annotations'):
                self.assertEqual(prom[name][field], grafana[name][field], name)
            self.assertEqual(prom[name].get('for', '0s'), grafana[name].get('for', '0s'), name)
            self.assertNotIn('__', prom[name]['expr'], name)
        self.assertIn('> 4500', prom['WithdrawalBacklogAboveDALimit']['expr'])
        self.assertIn('> 2745', prom['WithdrawalBacklogPastOnePayDown']['expr'])
        # The documented freshness is five minutes, not the two of the other WP snapshots.
        self.assertIn('< 300', prom['WithdrawalBacklogAboveDALimit']['expr'])
        self.assertIn('< 120', prom['AdvanceL2AdoptionDelayed']['expr'])
        custom = rules('prometheus', '--set', 'withdrawalBoundAlerts.maxWithdrawalsPerDaTx=6000',
                       '--set', 'withdrawalBoundAlerts.payDownCapacity=3000')
        self.assertIn('> 6000', custom['WithdrawalBacklogAboveDALimit']['expr'])
        self.assertIn('limit of 6000', custom['WithdrawalBacklogAboveDALimit']['annotations']['description'])
        self.assertIn('limit of 6000', custom['EthDASingleBlockOverWithdrawalLimit']['annotations']['description'])
        self.assertIn('> 3000', custom['WithdrawalBacklogPastOnePayDown']['expr'])
        self.assertFalse(rules('prometheus', '--set', 'serviceAlerts.enabled=false'))

    def test_timing_overrides_reach_the_queries(self):
        timed = rules('prometheus', '--set', 'alertTiming.rules.AdvanceL2AdoptionDelayed.window=45m',
                      '--set', 'alertTiming.rules.WithdrawalBacklogUnobserved.snapshotMaxAgeSeconds=600',
                      '--set', 'alertTiming.rules.EthDASingleBlockOverWithdrawalLimit.window=2h')
        self.assertIn('offset 45m', timed['AdvanceL2AdoptionDelayed']['expr'])
        self.assertIn('waited 45m', timed['AdvanceL2AdoptionDelayed']['annotations']['summary'])
        self.assertIn('< 600', timed['WithdrawalBacklogUnobserved']['expr'])
        self.assertIn('[2h:1m]', timed['EthDASingleBlockOverWithdrawalLimit']['expr'])

    def test_rejects_thresholds_that_cannot_work(self):
        for flags in (('--set', 'withdrawalBoundAlerts.maxWithdrawalsPerDaTx=0'),
                      ('--set-string', 'withdrawalBoundAlerts.maxWithdrawalsPerDaTx=4500'),
                      ('--set', 'withdrawalBoundAlerts.payDownCapacity=2745.5'),
                      ('--set', 'withdrawalBoundAlerts.payDownCapacity=4501')):
            with self.subTest(flags=flags):
                failed = subprocess.run(['helm', 'template', 'scroll-monitor', str(CHART), '--namespace', 'monitoring', *flags],
                                        capture_output=True, text=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn('withdrawalBoundAlerts', failed.stderr)

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_real_promql_thresholds_freshness_and_first_events(self):
        shipped = rules()
        cases = []

        def check(name, inputs, firing):
            """firing maps an alert to {minute: whether it fires}. Unlisted alerts stay quiet."""
            minutes = sorted({m for expected in firing.values() for m in expected})
            expected = {alert: firing.get(alert, dict.fromkeys(minutes, False)) for alert in sorted(NAMES)}
            cases.append({'name': name, 'interval': '1m', 'input_series': inputs, 'promql_expr_test': [
                {'expr': f'count(ALERTS{{alertname="{alert}",alertstate="firing"}}) or vector(0)',
                 'eval_time': f'{minute}m', 'exp_samples': [{'labels': '{}', 'value': int(fires)}]}
                for alert, at in expected.items() for minute, fires in at.items()]})

        critical, warning, unobserved = 'WithdrawalBacklogAboveDALimit', 'WithdrawalBacklogPastOnePayDown', 'WithdrawalBacklogUnobserved'
        check('backlog above the limit pages after ten minutes and warns after an hour', backlog(f'4501x{END}'),
              {critical: {9: False, 11: True, 65: True}, warning: {11: False, 59: False, 61: True}})
        check('backlog at the limit only warns', backlog(f'4500x{END}'), {warning: {61: True}, critical: {61: False}})
        check('backlog at one pay-down is quiet', backlog(f'2745x{END}'), {warning: {61: False}})
        check('backlog past one pay-down warns', backlog(f'2746x{END}'), {warning: {61: True}})
        check('an invalid count is not a backlog', backlog(f'9999x{END}', valid=f'0x{END}'),
              {unobserved: {9: False, 11: True, 61: True}})
        # A failed refresh keeps the last count and its success timestamp.
        check('a stale count is not a backlog', backlog(f'9999x{END}', timestamp=f'0x{END}'),
              {unobserved: {14: False, 16: True, 70: True}})
        check('a timestamp from the future is not fresh', backlog(f'9999x{END}', timestamp=f'90000x{END}'),
              {unobserved: {11: True, 61: True}})
        check('a target that is not scraped proves nothing', backlog(f'9999x{END}', up=f'0x{END}'),
              {unobserved: {11: True, 61: True}})
        check('a WP without the backlog metrics is unobserved',
              [series(SNAPSHOT + 'valid', {**WP, 'source': 'jobs'}, f'1x{END}')], {unobserved: {9: False, 11: True}})
        check('a backlog that recovers resolves', backlog('4501x30 100x170'),
              {critical: {11: True, 32: False}, warning: {61: False}})

        delayed = 'AdvanceL2AdoptionDelayed'
        check('a batch ahead for the whole window warns', heights(f'10x{END}', f'9x{END}'),
              {delayed: {29: False, 30: True, 90: True}})
        check('a batch published after an idle period gets the whole window',
              heights('9x40 10x159', f'9x{END}'), {delayed: {45: False, 70: False, 72: True}})
        check('adoption that trails a steady stream is not delayed',
              heights('10+1x199', '9+1x199'), {delayed: {31: False, 90: False}})
        check('adoption in the window resets it', heights(f'12x{END}', '9x50 10x149'),
              {delayed: {40: True, 55: False, 80: False, 82: True}})
        check('no published batch ahead is idle', heights(f'9x{END}', f'9x{END}'), {delayed: {90: False}})
        check('an invalid replay snapshot proves nothing', heights(f'10x{END}', f'9x{END}', replay_valid=f'0x{END}'),
              {delayed: {90: False}})
        replaced = {**WP, 'instance': 'wp-new'}
        check('a replaced pod keeps the window',
              [{**s, 'values': s['values'].replace(f'x{END}', 'x19') + ' stale'} for s in heights(f'10x{END}', f'9x{END}')]
              + [{**s, 'values': '_x20 ' + s['values'].replace(f'x{END}', 'x170').replace('0+60', '1200+60')}
                 for s in heights(f'10x{END}', f'9x{END}', target=replaced)],
              {delayed: {30: True}})

        single = 'EthDASingleBlockOverWithdrawalLimit'
        up = series('up', DA, f'1x{END}')
        check('the first event creates the counter', [up, series(COUNTER, DA, '_x20 1x179')],
              {single: {19: False, 21: True, 75: True, 85: False}})
        check('a later event increases it', [up, series(COUNTER, DA, '0x30 1x169')],
              {single: {29: False, 31: True, 85: True, 95: False}})
        check('a restart clears the counter and the next event still counts',
              [up, series(COUNTER, DA, '2x30 stale _x80 1x88')], {single: {35: False, 110: False, 113: True, 180: False}})
        check('a failed scrape is not an event',
              [series('up', DA, '1x30 0x5 1x164'), series(COUNTER, DA, '3x30 stale _x4 3x164')],
              {single: {33: False, 40: False, 100: False}})
        check('a counter that never moves is quiet', [up, series(COUNTER, DA, f'0x{END}')], {single: {30: False, 150: False}})
        check('an event from before this Prometheus is not a new one', [up, series(COUNTER, DA, f'3x{END}')],
              {single: {5: False, 30: False, 150: False}})
        new_pod = {**DA, 'instance': 'da-new'}
        check('an event right after the pod is replaced counts',
              [series('up', DA, '1x30 stale'), series('up', new_pod, '_x31 1x168'), series(COUNTER, new_pod, '_x31 1x168')],
              {single: {30: False, 32: True}})
        other = {**DA, 'job': 'da-publisher'}
        check('another job name gets later events only',
              [series('up', other, f'1x{END}'), series(COUNTER, other, '_x20 1x40 2x138')],
              {single: {25: False, 62: True}})

        with tempfile.TemporaryDirectory(prefix='withdrawal-bound-promql-') as directory:
            root = Path(directory)
            root.chmod(0o755)
            (root/'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'bound', 'rules': list(shipped.values())}]}))
            (root/'tests.yaml').write_text(yaml.safe_dump({'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': cases}))
            (root/'rules.yaml').chmod(0o644)
            (root/'tests.yaml').chmod(0o644)
            subprocess.run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'promtool',
                            '-v', f'{root}:/work:ro', 'prom/prometheus:v3.16.0',
                            'test', 'rules', '/work/tests.yaml'], check=True)


if __name__ == '__main__':
    unittest.main()
