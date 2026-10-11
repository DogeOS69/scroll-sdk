"""Regressions found by comparing devnet alerts with source-service evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_monitoring_templates import render, resource


class LiveAlertSemanticsTests(unittest.TestCase):
    def test_fee_reasons_and_policy_modes(self):
        for mode in ('transport_only', 'production_verifier_key_policy'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                root.chmod(0o755)
                docs = render('--set', 'grafanaAlerting.enabled=false', '--set',
                              'serviceAlerts.cubesignerPolicyMode=' + mode)
                groups = resource(docs, 'PrometheusRule', 'scroll-monitor-dogeos')['spec']['groups']
                wanted = {'EthDAPublicationFeeBlocked', 'EthDAPublishBacklogStalled',
                          'CubeSignerPolicyEvaluationMissing'}
                rules = [r for g in groups for r in g['rules'] if r['alert'] in wanted]
                (root / 'rules.yaml').write_text(yaml.safe_dump({'groups': [
                    {'name': 'regressions', 'rules': rules}]}))
                tests = []
                labels = 'namespace="monitoring",job="eth-da-submitter",instance="one"'
                for reason in ('pending_tx_cap', 'fee_sample_unavailable', 'window_budget_exhausted',
                               'execution_fee_cap_exceeded', 'blob_fee_cap_exceeded', 'replacement'):
                    counter = (f'eth_da_publish_replacement_fee_cap_blocked_total{{{labels}}}'
                               if reason == 'replacement' else
                               f'eth_da_publish_liveness_blocked_total{{{labels},reason="{reason}"}}')
                    tests.append({'name': reason, 'interval': '1m', 'input_series': [
                        {'series': f'eth_da_publish_ready_backlog{{{labels}}}', 'values': '198x30'},
                        {'series': f'eth_da_publish_oldest_ready_age_seconds{{{labels}}}', 'values': '11000x30'},
                        {'series': counter, 'values': '0+1x30'},
                    ], 'promql_expr_test': [
                        {'expr': f'count(ALERTS{{alertname="{name}",alertstate="firing"}}) or vector(0)',
                         'eval_time': '20m', 'exp_samples': [{'labels': '{}', 'value': expected}]}
                        for name, expected in [('EthDAPublicationFeeBlocked', int(reason in
                            ('execution_fee_cap_exceeded', 'blob_fee_cap_exceeded', 'replacement'))),
                            ('EthDAPublishBacklogStalled', 1)]
                    ]})
                for observed in (False, True):
                    tests.append({'name': f'policy-observed-{observed}', 'interval': '1m', 'input_series': [
                        {'series': 'cubesigner_signer_sign_outcome_total{namespace="monitoring",job="cubesigner-signer",instance="one",reason="success"}', 'values': '0+1x30'},
                        {'series': 'cubesigner_signer_policy_evaluations_total{namespace="monitoring",job="cubesigner-signer",instance="one",outcome="Permitted"}', 'values': '0+1x30' if observed else '0x30'},
                    ], 'promql_expr_test': [{
                        'expr': 'count(ALERTS{alertname="CubeSignerPolicyEvaluationMissing",alertstate="firing"}) or vector(0)',
                        'eval_time': '25m', 'exp_samples': [{'labels': '{}', 'value': int(
                            mode == 'production_verifier_key_policy' and not observed)}],
                    }]})
                (root / 'tests.yaml').write_text(yaml.safe_dump({
                    'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': tests}))
                subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'promtool',
                                '-v', f'{root}:/work:ro', 'prom/prometheus:v2.52.0',
                                'test', 'rules', '/work/tests.yaml'], check=True)
