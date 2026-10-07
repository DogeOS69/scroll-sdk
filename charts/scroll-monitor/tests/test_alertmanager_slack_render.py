"""Render Slack notifications with amtool, including stale Grafana annotations.

Set AMTOOL_BINARY to test with the deployed Alertmanager version.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

CHART = Path(__file__).resolve().parents[1]
AMTOOL = os.environ.get('AMTOOL_BINARY') or shutil.which('amtool')
RAW_SUMMARY = 'ERROR or panicked logs detected in {{ $labels.service }}.'
RAW_DESCRIPTION = '{{ $values.A.Value | printf "%.0f" }} matching log line(s) for {{ $labels.namespace }}/{{ $labels.pod }}.'


@unittest.skipUnless(AMTOOL, 'amtool is required for notification rendering')
class AlertmanagerSlackRenderTests(unittest.TestCase):
    def alert(self, state='resolved', annotations=None):
        return {
            'Status': state,
            'Labels': {'alertname': 'ServiceErrorOrPanickedLogs', 'service': 'grafana',
                       'namespace': 'default', 'pod': 'grafana-example', 'container': 'grafana'},
            'Annotations': annotations if annotations is not None else {
                'summary': RAW_SUMMARY, 'description': RAW_DESCRIPTION},
            'StartsAt': '2026-10-06T13:00:00Z', 'EndsAt': '2026-10-06T13:05:00Z',
            'GeneratorURL': 'http://internal-prometheus.invalid:9090/graph',
        }

    def render(self, alerts):
        payload = {
            'Receiver': 'slack-alerts', 'Status': 'firing' if any(a['Status'] == 'firing' for a in alerts) else 'resolved',
            'Alerts': alerts, 'GroupLabels': {}, 'CommonLabels': {}, 'CommonAnnotations': {},
            'ExternalURL': 'http://internal-alertmanager.invalid:9093',
        }
        template = ((CHART / 'notifications/annotation-helpers.tmpl').read_text() + '\n' +
                    (CHART / 'notifications/alertmanager-slack.tmpl').read_text()).replace(
            '__GRAFANA_URL__', 'https://grafana.example.invalid').replace('__ENVIRONMENT__', 'testnet')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'notifications.tmpl').write_text(template)
            (path / 'data.json').write_text(json.dumps(payload))
            text = subprocess.check_output([
                AMTOOL, 'template', 'render', '--template.glob=' + str(path / 'notifications.tmpl'),
                '--template.data=' + str(path / 'data.json'),
                '--template.text={{ template "scroll-monitor.slack.text" . }}',
            ], text=True)
        self.assertNotIn('{{', text)
        self.assertNotIn('$labels', text)
        self.assertNotIn('$values', text)
        self.assertNotIn('<no value>', text)
        self.assertNotIn('internal-prometheus', text)
        self.assertNotIn('internal-alertmanager', text)
        return text

    def test_resolved_raw_annotations_use_labels_without_a_log_count(self):
        text = self.render([self.alert()])
        self.assertIn('RESOLVED: Log error alert resolved for grafana.', text)
        self.assertIn('default/grafana-example (container grafana) is resolved.', text)
        self.assertNotIn('matching log line(s)', text)
        self.assertNotIn('|Silence>', text)

    def test_missing_series_is_not_claimed_as_service_recovery(self):
        alert = self.alert()
        alert['Annotations']['grafana_state_reason'] = 'MissingSeries'
        text = self.render([alert])
        self.assertIn('no longer receives this alert series', text)
        self.assertIn('does not by itself confirm service recovery', text)

    def test_resolved_rendered_annotation_does_not_reuse_a_stale_count(self):
        alert = self.alert(annotations={'summary': 'Errors in grafana.',
                                       'description': '9 matching log line(s) in the last 5 minutes.'})
        self.assertNotIn('9 matching', self.render([alert]))

    def test_firing_retains_valid_count_and_silence_link(self):
        alert = self.alert('firing', {'summary': 'Errors in grafana.',
                                    'description': '3 matching log line(s) in the last 5 minutes.'})
        text = self.render([alert])
        self.assertIn('FIRING: ERROR or panicked logs detected in grafana.', text)
        self.assertIn('3 matching log line(s)', text)
        self.assertIn('|Silence>', text)

    def test_firing_raw_annotations_do_not_invent_a_count(self):
        text = self.render([self.alert('firing')])
        self.assertIn('Matching ERROR or panicked logs were detected for default/grafana-example', text)
        self.assertNotIn('matching log line(s)', text)

    def test_missing_labels_have_readable_fallbacks(self):
        alert = self.alert()
        alert['Labels'] = {'alertname': 'ServiceErrorOrPanickedLogs'}
        self.assertIn('resolved for the monitored service.', self.render([alert]))

    def test_other_alerts_preserve_valid_annotations_and_reject_raw_templates(self):
        alert = self.alert('firing', {'summary': 'Balance is low.', 'description': 'Balance is 3 DOGE.'})
        alert['Labels']['alertname'] = 'FeeWalletBalanceLow'
        text = self.render([alert])
        self.assertIn('Balance is low.', text)
        self.assertIn('Balance is 3 DOGE.', text)
        alert['Annotations'] = {'summary': RAW_SUMMARY, 'description': RAW_DESCRIPTION}
        text = self.render([alert])
        self.assertIn('FIRING: FeeWalletBalanceLow', text)
        self.assertIn('Open the alert in Grafana', text)

    def test_unexpanded_link_annotations_are_omitted(self):
        alert = self.alert()
        alert['Annotations'].update({
            'dashboard_url': 'https://grafana.example.invalid/d/{{ $labels.dashboard }}',
            'runbook_url': 'https://docs.example.invalid/$labels.service',
        })
        text = self.render([alert])
        self.assertNotIn('|Dashboard>', text)
        self.assertNotIn('|Runbook>', text)
        alert['Annotations']['dashboard_url'] = 'https://grafana.example.invalid/d/service'
        alert['Annotations']['runbook_url'] = 'https://docs.example.invalid/runbook'
        text = self.render([alert])
        self.assertIn('|Dashboard>', text)
        self.assertIn('|Runbook>', text)

    def test_other_alerts_reject_missing_value_markers(self):
        for marker in ('<no value>', '[no value]', '$labels.service', '$values.A.Value'):
            with self.subTest(marker=marker):
                alert = self.alert('firing', {'summary': marker, 'description': marker})
                alert['Labels']['alertname'] = 'OtherAlert'
                text = self.render([alert])
                self.assertNotIn(marker, text)
                self.assertIn('FIRING: OtherAlert', text)

    def test_mixed_group_uses_each_alert_status(self):
        firing = self.alert('firing', {'summary': 'Errors in grafana.', 'description': '2 matching log line(s).'})
        resolved = copy.deepcopy(firing)
        resolved['Status'] = 'resolved'
        text = self.render([firing, resolved])
        self.assertIn('FIRING: ERROR or panicked logs detected in grafana.', text)
        self.assertIn('RESOLVED: Log error alert resolved for grafana.', text)
        self.assertEqual(text.count('2 matching log line(s)'), 1)
        self.assertEqual(text.count('|Silence>'), 1)


if __name__ == '__main__':
    unittest.main()
