"""Alert switches for deployments that idle, drain long backlogs or run on a shadowfork."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_alert_timing import render_values
from test_monitoring_templates import grafana_rules, render, resource

RUNTIME = os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1'
FLAT_30M = 'x30'


def rules_of(docs):
    groups = resource(docs, 'PrometheusRule', 'scroll-monitor-dogeos')['spec']['groups']
    return {rule['alert']: rule for group in groups for rule in group['rules'] if 'alert' in rule}


def native(values=None):
    merged = {'grafanaAlerting': {'enabled': False}, 'serviceAlerts': {'paused': False}, **(values or {})}
    return render_values(merged)


def series(name, labels, values):
    pairs = ','.join(f'{key}="{value}"' for key, value in labels.items())
    return {'series': f'{name}{{{pairs}}}', 'values': values}


class RenderTests(unittest.TestCase):
    def test_gates_are_off_by_default(self):
        rules = rules_of(native())
        self.assertNotIn('unless', rules['L2BatchHeightStalled']['expr'].split('== 0', 1)[1])
        for name in ('ProofMaterializationQueueStalled', 'ProofWorkerQueueStalled'):
            self.assertNotIn('unless', rules[name]['expr'])

    def test_gates_use_the_completion_metric_of_each_phase(self):
        rules = rules_of(native({'businessAlerts': {'l2BatchRequirePendingWork': True, 'l2BatchStallSeconds': 600, 'proofQueueRequireNoProgress': True}}))
        self.assertIn('[600s:1m]', rules['L2BatchHeightStalled']['expr'])
        materialize = rules['ProofMaterializationQueueStalled']['expr']
        self.assertIn('unless on (namespace) (', materialize)
        self.assertIn('proof_coordinator_work_items_total{outcome="success"}[1800s]', materialize)
        self.assertIn('proof_coordinator_prove_attempts_ended_total{cause="succeeded"}[1800s]', materialize)
        self.assertIn('proof_coordinator_prove_attempts_ended_total{cause="succeeded"}[3600s]', rules['ProofWorkerQueueStalled']['expr'])

    def test_stale_runway_rule_is_paused_or_omitted_only_on_request(self):
        off = {'recoveryRunwayAlerts': {'observationStaleEnabled': False}}
        self.assertNotIn('RecoveryRunwayObservationStale', rules_of(native(off)))
        self.assertIn('RecoveryRunwayCritical', rules_of(native(off)))
        self.assertTrue(grafana_rules(render_values({**off, 'serviceAlerts': {'paused': False}}))['RecoveryRunwayObservationStale']['isPaused'])
        self.assertFalse(grafana_rules(render_values({'serviceAlerts': {'paused': False}}))['RecoveryRunwayObservationStale'].get('isPaused', False))
        explicit = {**off, 'serviceAlerts': {'paused': False}, 'grafanaAlerting': {'pauseRules': {'RecoveryRunwayObservationStale': False}}}
        self.assertFalse(grafana_rules(render_values(explicit))['RecoveryRunwayObservationStale']['isPaused'])
        self.assertIn('shadowfork', rules_of(native())['RecoveryRunwayObservationStale']['annotations']['description'])

    def test_external_targets_split_by_job(self):
        rules = rules_of(native({'attestationSignerMonitoring': {'enabled': True}, 'externalTargetAlerts': {'jobRegex': 'attestation-signer|other'}}))
        self.assertEqual(rules['MetricsTargetDown']['expr'], 'up{job!~"attestation-signer|other"} == 0')
        self.assertEqual(rules['MetricsTargetDown']['labels']['severity'], 'critical')
        self.assertEqual(rules['ExternalScrapeTargetDown']['expr'], 'up{job=~"attestation-signer|other"} == 0')
        self.assertEqual(rules['ExternalScrapeTargetDown']['labels']['severity'], 'warning')

    SIGNER_ALERTS = ('AttestationSignerNotReady', 'AttestationSignerTerminalFailure', 'AttestationSignerSigningFailures', 'AttestationSignerCallbackFailures')

    def test_attestation_signer_alerts_are_off_by_default(self):
        rules = rules_of(native())
        grafana = grafana_rules(render_values({}))
        for name in self.SIGNER_ALERTS:
            self.assertNotIn(name, rules)
            self.assertTrue(grafana[name]['isPaused'])
        self.assertEqual(rules['ExternalScrapeTargetDown']['expr'], 'up{job=~"attestation-signer",job!="attestation-signer"} == 0')
        self.assertEqual(rules['MetricsTargetDown']['expr'], 'up{job!~"attestation-signer"} == 0')

    def test_attestation_signer_switch_resumes_existing_rules(self):
        enabled = {'attestationSignerMonitoring': {'enabled': True}}
        rules = rules_of(native(enabled))
        grafana = grafana_rules(render_values(enabled))
        for name in self.SIGNER_ALERTS:
            self.assertIn(name, rules)
            self.assertIs(grafana[name]['isPaused'], False)
        explicit = {**enabled, 'grafanaAlerting': {'pauseRules': {'AttestationSignerNotReady': True}}}
        self.assertTrue(grafana_rules(render_values(explicit))['AttestationSignerNotReady']['isPaused'])

    def test_rejects_a_switch_that_is_not_a_boolean(self):
        with self.assertRaises(subprocess.CalledProcessError):
            render_values({'attestationSignerMonitoring': {'enabled': 'false'}})

    def test_external_job_regex_is_escaped_for_promql(self):
        rules = rules_of(native({'externalTargetAlerts': {'jobRegex': r'ext\.foo'}}))
        self.assertEqual(rules['MetricsTargetDown']['expr'], r'up{job!~"ext\\.foo"} == 0')
        with_quote = rules_of(native({'externalTargetAlerts': {'jobRegex': 'a"b'}}))
        self.assertEqual(with_quote['MetricsTargetDown']['expr'], r'up{job!~"a\"b"} == 0')

    def test_rejects_an_external_job_regex_that_breaks_the_rule(self):
        for value in ('a #b', 'a b', '(unclosed'):
            with self.subTest(value=value), self.assertRaises(subprocess.CalledProcessError):
                render_values({'externalTargetAlerts': {'jobRegex': value}})

    def test_l2_gate_compares_each_job_with_validated_da_height(self):
        expr = rules_of(native({'businessAlerts': {'l2BatchRequirePendingWork': True}}))['L2BatchHeightStalled']['expr']
        self.assertIn('unless on (namespace, job)', expr)
        self.assertIn('withdrawal_processor_protocol_snapshot_valid{source="l2"}', expr)
        self.assertNotIn('__WP_L2_VALID__', expr)
        self.assertNotIn('__TIME_', expr)

    def test_rejects_a_fractional_age_only_when_it_becomes_a_range(self):
        fractional = {'alertTiming': {'rules': {'ProofWorkerQueueStalled': {'maxAgeSeconds': 3600.5}}}}
        rules_of(native(fractional))
        with self.assertRaises(subprocess.CalledProcessError):
            render_values({**fractional, 'businessAlerts': {'proofQueueRequireNoProgress': True}})

    def test_rejects_a_quoted_switch_that_templates_would_treat_as_true(self):
        for values in [{'businessAlerts': {'l2BatchRequirePendingWork': 'false'}},
                       {'businessAlerts': {'proofQueueRequireNoProgress': 'false'}},
                       {'recoveryRunwayAlerts': {'observationStaleEnabled': 'false'}}]:
            with self.subTest(values=values), self.assertRaises(subprocess.CalledProcessError):
                render_values(values)

    def test_grafana_migrates_the_previous_target_rule(self):
        self.assertEqual(grafana_rules(render())['MetricsTargetDown']['previousExpr'], 'up == 0')

    def test_error_log_defaults_migrate_the_previously_shipped_rule(self):
        rule = grafana_rules(render())['ServiceErrorLogs']
        self.assertEqual((rule['for'], rule['previousFor']), ('5m', '0s'))
        self.assertTrue(rule['expr'].endswith('>= 5'))
        self.assertNotIn('__LOG_ERROR_EXCLUDES__', rule['expr'])
        self.assertTrue(any('alert_logfmt_severity' in previous and previous.endswith('> 0') for previous in rule['previousExpr']))

    def test_rejects_unsafe_log_exclusions(self):
        for patterns in ({'bad service!': ['x']}, {'svc': ['has`backtick']}, {'svc': ['']}, {'svc': ['(unclosed']}, {'svc': ['two\nlines']}):
            with self.subTest(patterns=patterns), self.assertRaises(subprocess.CalledProcessError):
                render_values({'logAlerts': {'excludePatterns': patterns}})

    def test_rejects_a_bad_line_threshold(self):
        for value in (0, 'five', 1.5):
            with self.subTest(value=value), self.assertRaises(subprocess.CalledProcessError):
                render_values({'alertTiming': {'rules': {'ServiceErrorLogs': {'minLines': value}}}})

    def test_rejects_an_empty_external_job_regex(self):
        with self.assertRaises(subprocess.CalledProcessError):
            render_values({'externalTargetAlerts': {'jobRegex': ''}})


@unittest.skipUnless(RUNTIME, 'requires Docker/promtool')
class PromtoolTests(unittest.TestCase):
    def firing(self, rules, name, input_series, minutes=25):
        with tempfile.TemporaryDirectory(prefix='scroll-monitor-gates-') as directory:
            root = Path(directory)
            root.chmod(0o755)
            groups = [{'name': 'selected', 'interval': '1m', 'rules': [{key: value for key, value in rules[name].items() if key in ('alert', 'expr', 'for', 'labels', 'annotations')}]}]
            (root / 'rules.yaml').write_text(yaml.safe_dump({'groups': groups}, sort_keys=False))
            case = {'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': [{'interval': '1m', 'input_series': input_series, 'alert_rule_test': [{'eval_time': f'{minutes}m', 'alertname': name, 'exp_alerts': []}]}]}
            (root / 'case.test.yaml').write_text(yaml.safe_dump(case, sort_keys=False))
            result = subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'promtool', '-v', f'{root}:/work:ro', '-w', '/work', 'prom/prometheus:v3.16.0', 'test', 'rules', 'case.test.yaml'], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return False
            self.assertIn('got:[', result.stdout + result.stderr, result.stdout + result.stderr)
            return True

    L2 = {'namespace': 'monitoring', 'job': 'withdrawal-processor', 'instance': 'wp'}

    def l2_series(self, latest, valid='1x30', height=f'5{FLAT_30M}'):
        heads = [series('withdrawal_processor_protocol_state_l2_batch_height', self.L2, height),
                 series('withdrawal_processor_protocol_snapshot_valid', {**self.L2, 'source': 'l2'}, valid),
                 series('withdrawal_processor_protocol_snapshot_timestamp_seconds', {**self.L2, 'source': 'l2'}, '0+60x30'),
                 series('up', self.L2, '1x30')]
        return heads + ([series('withdrawal_processor_protocol_latest_da_batch_height', self.L2, latest)] if latest else [])

    def test_l2_gate_does_not_treat_invalid_empty_or_other_job_evidence_as_idle(self):
        gated = rules_of(native({'businessAlerts': {'l2BatchRequirePendingWork': True, 'l2BatchStallSeconds': 600}}))
        self.assertTrue(self.firing(gated, 'L2BatchHeightStalled', self.l2_series(f'5{FLAT_30M}', valid='0x30')), 'invalid snapshot')
        self.assertTrue(self.firing(gated, 'L2BatchHeightStalled', self.l2_series(f'0{FLAT_30M}')), 'job has a height, DA inventory is empty')
        self.assertFalse(self.firing(gated, 'L2BatchHeightStalled', self.l2_series(f'0{FLAT_30M}', height=f'0{FLAT_30M}')), 'no batch published yet')
        advancing = '5+1x30'
        wedged = [series('l1_interface_protocol_state_l2_batch_height', {'namespace': 'monitoring', 'job': 'l1-interface', 'instance': 'l1'}, f'5{FLAT_30M}')]
        self.assertTrue(self.firing(gated, 'L2BatchHeightStalled', self.l2_series(advancing, height=advancing) + wedged), 'stuck job behind a healthy one')
        self.assertFalse(self.firing(gated, 'L2BatchHeightStalled', self.l2_series(advancing, height=advancing)), 'healthy job')

    def test_external_target_for_signer_needs_the_switch(self):
        signer = [series('up', {'job': 'attestation-signer', 'instance': 'signer'}, '0x30')]
        other = [series('up', {'job': 'other', 'instance': 'host'}, '0x30')]
        off = rules_of(native({'externalTargetAlerts': {'jobRegex': 'attestation-signer|other'}}))
        self.assertFalse(self.firing(off, 'ExternalScrapeTargetDown', signer), 'partner signer not collected')
        self.assertFalse(self.firing(off, 'MetricsTargetDown', signer))
        self.assertTrue(self.firing(off, 'ExternalScrapeTargetDown', other), 'other external jobs keep alerting')

    def test_l2_stall_distinguishes_idle_from_stalled(self):
        gated = rules_of(native({'businessAlerts': {'l2BatchRequirePendingWork': True, 'l2BatchStallSeconds': 600}}))
        plain = rules_of(native({'businessAlerts': {'l2BatchStallSeconds': 600}}))
        self.assertTrue(self.firing(plain, 'L2BatchHeightStalled', self.l2_series(f'5{FLAT_30M}')), 'default still fires when idle')
        self.assertFalse(self.firing(gated, 'L2BatchHeightStalled', self.l2_series(f'5{FLAT_30M}')), 'idle chain')
        self.assertTrue(self.firing(gated, 'L2BatchHeightStalled', self.l2_series(f'9{FLAT_30M}')), 'batch waiting all window')
        self.assertFalse(self.firing(gated, 'L2BatchHeightStalled', self.l2_series('5x20 9x10')), 'batch only just published')
        self.assertTrue(self.firing(gated, 'L2BatchHeightStalled', self.l2_series('')), 'missing evidence is not idle')

    WP = {'namespace': 'monitoring', 'job': 'withdrawal-processor', 'instance': 'wp'}

    def proof_series(self, phase, completion):
        age = series('withdrawal_processor_proof_work_oldest_age_seconds', {**self.WP, 'proof_family': 'chunk', 'phase': phase, 'status': 'pending'}, '90000x60')
        guards = [series('withdrawal_processor_protocol_snapshot_valid', {**self.WP, 'source': 'proof_work'}, '1x60'),
                  series('withdrawal_processor_protocol_snapshot_timestamp_seconds', {**self.WP, 'source': 'proof_work'}, '0+60x60'),
                  series('up', self.WP, '1x60')]
        return [age, *guards, *completion]

    def test_draining_queue_holds_until_completions_stop(self):
        gated = rules_of(native({'businessAlerts': {'proofQueueRequireNoProgress': True}}))
        coordinator = {'namespace': 'monitoring', 'job': 'proof-coordinator', 'instance': 'pc', 'proof_family': 'chunk'}
        cases = (('ProofWorkerQueueStalled', 'prove', 'proof_coordinator_prove_attempts_ended_total', {'cause': 'succeeded'}),
                 ('ProofMaterializationQueueStalled', 'materialize', 'proof_coordinator_work_items_total', {'phase': 'materialize', 'outcome': 'success'}))
        for name, phase, metric, labels in cases:
            with self.subTest(name=name):
                labelled = {**coordinator, **labels}
                self.assertFalse(self.firing(gated, name, self.proof_series(phase, [series(metric, labelled, '0+1x60')]), minutes=50), 'draining')
                self.assertTrue(self.firing(gated, name, self.proof_series(phase, [series(metric, labelled, '7x60')]), minutes=50), 'no completions')
                self.assertTrue(self.firing(gated, name, self.proof_series(phase, []), minutes=50), 'metric missing')
                elsewhere = {**labelled, 'namespace': 'other'}
                self.assertTrue(self.firing(gated, name, self.proof_series(phase, [series(metric, elsewhere, '0+1x60')]), minutes=50), 'another namespace draining')
        other = {**coordinator, 'proof_family': 'bundle', 'cause': 'succeeded'}
        self.assertTrue(self.firing(gated, 'ProofWorkerQueueStalled', self.proof_series('prove', [series('proof_coordinator_prove_attempts_ended_total', other, '0+1x60')]), minutes=50), 'prove: another family draining')

    def test_materialize_gate_counts_progress_of_any_family(self):
        # A batch waits in materialize while the proofs of its chunks finish one by one.
        gated = rules_of(native({'businessAlerts': {'proofQueueRequireNoProgress': True}}))
        name = 'ProofMaterializationQueueStalled'
        coordinator = {'namespace': 'monitoring', 'job': 'proof-coordinator', 'instance': 'pc', 'proof_family': 'bundle'}
        attempts = 'proof_coordinator_prove_attempts_ended_total'
        chunk_proofs = series(attempts, {**coordinator, 'cause': 'succeeded'}, '0+1x60')
        self.assertFalse(self.firing(gated, name, self.proof_series('materialize', [chunk_proofs]), minutes=50), 'other family proving')
        verified = series('proof_coordinator_work_items_total', {**coordinator, 'phase': 'verify', 'outcome': 'success'}, '0+1x60')
        self.assertFalse(self.firing(gated, name, self.proof_series('materialize', [verified]), minutes=50), 'other phase completing')
        lost = series(attempts, {**coordinator, 'cause': 'worker_lost'}, '0+1x60')
        self.assertTrue(self.firing(gated, name, self.proof_series('materialize', [lost]), minutes=50), 'only failed attempts')
        quiet = series(attempts, {**coordinator, 'cause': 'succeeded'}, '5x60')
        self.assertTrue(self.firing(gated, name, self.proof_series('materialize', [quiet]), minutes=50), 'no proof finished in the window')

    def test_external_target_failure_does_not_page_critical(self):
        rules = rules_of(native({'attestationSignerMonitoring': {'enabled': True}}))
        signer = [series('up', {'job': 'attestation-signer', 'instance': 'signer'}, '0x30')]
        service = [series('up', {'job': 'withdrawal-processor', 'instance': 'wp'}, '0x30')]
        self.assertFalse(self.firing(rules, 'MetricsTargetDown', signer))
        self.assertTrue(self.firing(rules, 'ExternalScrapeTargetDown', signer))
        self.assertTrue(self.firing(rules, 'MetricsTargetDown', service))
        self.assertFalse(self.firing(rules, 'ExternalScrapeTargetDown', service))


if __name__ == '__main__':
    unittest.main()
