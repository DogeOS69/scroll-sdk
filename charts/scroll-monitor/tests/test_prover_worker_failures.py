"""Render both shipped backends and evaluate the per-worker failure rule with promtool."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_monitoring_templates import render, resource, grafana_rules

NAME = 'ProverWorkerRepeatedFailures'
TARGET = {'namespace': 'monitoring', 'job': 'proof-coordinator', 'instance': 'coordinator'}
EVAL = 20  # minutes
RUNBOOK = ('https://github.com/DogeOS69/dogeos-core/blob/'
           '1515af039cab116d1c4d89246c03b13c545e2a30/'
           'docs/engineering/aws-gpu-dstack.md#L618-L653')


def labels(values):
    return '{' + ','.join(f'{k}="{v}"' for k, v in sorted(values.items())) + '}'


def rules(backend='prometheus', *args):
    flags = ['--set', 'alerting.backend=' + backend]
    if backend == 'prometheus':
        flags += ['--set', 'kube-prometheus-stack.alertmanager.alertmanagerSpec.useExistingSecret=true',
                  '--set', 'kube-prometheus-stack.alertmanager.alertmanagerSpec.configSecret=scroll-monitor-alertmanager-config']
    docs = render(*flags, *args)
    if backend == 'grafana':
        return {k: v for k, v in grafana_rules(docs).items() if k == NAME}
    groups = resource(docs, 'PrometheusRule', 'scroll-monitor-dogeos')['spec']['groups']
    return {r['alert']: r for g in groups for r in g['rules'] if r.get('alert') == NAME}


class ProverWorkerFailureTests(unittest.TestCase):
    def test_shared_backends_and_existing_routing(self):
        prom = rules()[NAME]
        grafana = rules('grafana')[NAME]
        for field in ('expr', 'labels', 'annotations'):
            self.assertEqual(prom[field], grafana[field])
        self.assertNotIn('contactPoint', grafana)
        self.assertEqual(prom['labels'], {'severity': 'warning', 'service': 'proof-coordinator'})
        self.assertIn('{{ $labels.worker_id }}', prom['annotations']['summary'])
        self.assertEqual(prom['annotations']['runbook_url'], RUNBOOK)
        self.assertFalse(rules('prometheus', '--set', 'serviceAlerts.enabled=false'))

    def run_promtool(self, shipped, tests):
        with tempfile.TemporaryDirectory(prefix='worker-failures-promql-') as directory:
            root = Path(directory)
            root.chmod(0o755)
            (root/'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'workers', 'rules': [shipped]}]}))
            (root/'tests.yaml').write_text(yaml.safe_dump({'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': tests}))
            (root/'rules.yaml').chmod(0o644)
            (root/'tests.yaml').chmod(0o644)
            subprocess.run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'promtool',
                            '-v', f'{root}:/work:ro', 'prom/prometheus:v2.52.0',
                            'test', 'rules', '/work/tests.yaml'], check=True)

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_real_promql_threshold_is_per_worker(self):
        shipped = rules()[NAME]
        # Five failures within the window fire; four do not; workers are not summed together.
        series = [
            {'series': 'proof_coordinator_worker_failed_results_total' + labels({**TARGET, 'worker_id': w}),
             'values': v}
            for w, v in (('gpu-bad', f'0x{EVAL - 5} 1 2 3 4 5'), ('gpu-four', f'0x{EVAL - 4} 1 2 3 4'),
                         ('gpu-other', f'0x{EVAL - 4} 1 2 3 4'))
        ]
        summary = shipped['annotations']['summary'].replace('{{ $labels.worker_id }}', 'gpu-bad')
        tests = [{'name': 'per-worker threshold', 'interval': '1m', 'input_series': series,
                  'alert_rule_test': [{'eval_time': f'{EVAL}m', 'alertname': NAME, 'exp_alerts': [{
                      'exp_labels': {**TARGET, 'worker_id': 'gpu-bad', **shipped['labels']},
                      'exp_annotations': {**shipped['annotations'], 'summary': summary}}]}]}]
        self.run_promtool(shipped, tests)

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_new_counters_expiry_scrape_gaps_and_resets(self):
        shipped = rules()[NAME]
        worker = 'gpu-new'
        expected = {'exp_labels': {**TARGET, 'worker_id': worker, **shipped['labels']},
                    'exp_annotations': {**shipped['annotations'], 'summary':
                        shipped['annotations']['summary'].replace('{{ $labels.worker_id }}', worker)}}
        # Real Core counters are absent until a failure, not exported as zero.
        # The second window must not keep alerting on their old lifetime total.
        cases = [
            ('first two failures before first scrape', '_x5 2 3 4 5+0x30', [(10, True), (21, False)]),
            ('entire burst before first scrape', '_x15 5+0x25', [(16, True), (20, True), (31, False)]),
            ('new counter below threshold', '_x15 4+0x25', [(20, False)]),
            ('old quiet counter', '9+0x40', [(20, False)]),
            ('old counter after scrape gap', '9x1 _x14 9+0x24', [(22, False)]),
            ('initial nonzero then reset', '_x10 4 1 2+0x25', [(13, True), (28, False)]),
            ('initial nonzero, growth, then reset stays below threshold', '_x10 1 2 3 0 1+0x25', [(15, False)]),
            ('initial nonzero and multiple resets', '_x10 2 3 1 0 1+0x25', [(15, True), (30, False)]),
            ('new counter with a short scrape gap', '_x10 3 _ _ 4+0x25', [(15, False)]),
            ('new counter gap then reset', '_x10 4 _ _ 1 2+0x25', [(15, True)]),
            # A restarted coordinator may omit the counter until the next failure,
            # even though its metrics endpoint is healthy. Retain the initial burst
            # through a stale marker or a gap longer than the instant lookback.
            ('initial burst disappears after restart', '_x10 5 5 stale _x30',
             [(10, True), (13, True), (18, True), (24, True), (25, False), (30, False)]),
            ('initial burst survives extended scrape gap', '_x10 5 5 _x30',
             [(13, True), (18, True), (24, True), (25, False), (30, False)]),
            ('counter returns after restart', '_x10 5 5 stale _x5 1+0x20',
             [(13, True), (17, True), (20, True), (24, True), (25, False), (30, False)]),
            ('below threshold disappears', '_x10 4 4 stale _x30',
             [(13, False), (18, False), (24, False), (30, False)]),
            ('old quiet series disappears and returns', '9x10 stale _x3 9+0x30',
             [(15, False), (20, False), (30, False)]),
            # Raw increase extrapolates sparse new counters above their actual
            # lifetime total (1 -> 4 -> stale becomes 5.5 at minute 13).
            # Only the padded branch should evaluate these new series.
            ('four failures then stale', '_x10 1 4 stale _x30',
             [(11, False), (12, False), (13, False), (20, False), (25, False)]),
            ('three failures then stale', '_x10 1 3 stale _x30',
             [(12, False), (13, False), (20, False)]),
            ('four failures then scrape gap', '_x10 1 4 _x30',
             [(12, False), (13, False), (18, False), (24, False)]),
            ('five failures then stale', '_x10 1 5 stale _x30',
             [(12, True), (13, True), (20, True), (24, True), (26, False)]),
            ('established counter reset', '10x15 0 1 2 3 4 5+0x19', [(20, False), (21, True)]),
        ]
        tests = [
            {'name': name, 'interval': '1m', 'input_series': [{
                'series': 'proof_coordinator_worker_failed_results_total' + labels({**TARGET, 'worker_id': worker}),
                'values': values}],
             'alert_rule_test': [{'eval_time': f'{minute}m', 'alertname': NAME,
                                 'exp_alerts': [expected] if fires else []}
                                for minute, fires in evaluations]}
            for name, values, evaluations in cases
        ]
        # Neither new worker is individually over threshold; don't combine their totals.
        tests.append({'name': 'new workers stay separate', 'interval': '1m', 'input_series': [
            {'series': 'proof_coordinator_worker_failed_results_total' + labels({**TARGET, 'worker_id': w}),
             'values': '_x15 4+0x5'} for w in ('gpu-a', 'gpu-b')],
            'alert_rule_test': [{'eval_time': '20m', 'alertname': NAME, 'exp_alerts': []}]})
        tests.append({'name': 'reset between minute evaluations', 'interval': '15s',
                      'input_series': [{'series': 'proof_coordinator_worker_failed_results_total'
                                        + labels({**TARGET, 'worker_id': worker}),
                                        'values': '_x43 4 1 2+0x20'}],
                      'alert_rule_test': [{'eval_time': '12m', 'alertname': NAME,
                                           'exp_alerts': [expected]}]})
        self.run_promtool(shipped, tests)


if __name__ == '__main__':
    unittest.main()
