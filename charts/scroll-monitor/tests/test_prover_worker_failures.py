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
        self.assertTrue(prom['annotations']['runbook_url'].endswith('aws-gpu-dstack.md#misbehaving-worker'))
        self.assertFalse(rules('prometheus', '--set', 'serviceAlerts.enabled=false'))

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


if __name__ == '__main__':
    unittest.main()
