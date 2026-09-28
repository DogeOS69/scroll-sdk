"""Dashboard wiring and query-shape checks; no service exposition snapshots.

Metric definitions belong in dogeos-core. Recheck names, labels and exporter
configuration against the intended source revision as described in
DASHBOARD_REVIEW.md; these structural tests do not replace that source review.
"""
import json
from pathlib import Path
import re
import unittest


CHART = Path(__file__).resolve().parents[1]
FILES = sorted((CHART / 'grafana/dogeos-dashboards').glob('*.json')) + [CHART / 'grafana/dstack.json']


def walk(panels):
    for panel in panels:
        yield panel
        yield from walk(panel.get('panels', []))


def dashboards():
    return [(path.stem, json.loads(path.read_text())) for path in FILES]


class DogeosDashboardTests(unittest.TestCase):
    def test_unique_ids_declared_variables_and_no_embedded_metrics(self):
        uids = set()
        for name, dashboard in dashboards():
            with self.subTest(dashboard=name):
                self.assertNotIn(dashboard['uid'], uids)
                uids.add(dashboard['uid'])
                ids = set()
                variables = {v['name'] for v in dashboard['templating']['list']}
                for panel in walk(dashboard['panels']):
                    self.assertNotIn(panel['id'], ids)
                    ids.add(panel['id'])
                    for target in panel.get('targets', []):
                        expr = target.get('expr', '')
                        for var in re.findall(r'\$\{?(\w+)', expr):
                            self.assertTrue(var.startswith('__') or var in variables, (name, var))
                        self.assertNotIn('# TYPE', expr)
                        self.assertNotIn('# HELP', expr)

    def test_current_stat_panels_do_not_reuse_historical_healthy_values(self):
        for name, dashboard in dashboards():
            for panel in walk(dashboard['panels']):
                if panel['type'] in ('text', 'row'):
                    continue
                with self.subTest(dashboard=name, panel=panel['id']):
                    defaults = panel['fieldConfig']['defaults']
                    self.assertEqual(defaults['noValue'], 'No data')
                    self.assertFalse(defaults.get('custom', {}).get('spanNulls', False))
                    if panel['type'] in ('stat', 'table'):
                        for target in panel.get('targets', []):
                            ds = target.get('datasource', panel.get('datasource', {}))
                            if ds.get('type') == 'prometheus':
                                self.assertTrue(target.get('instant'))
                                self.assertFalse(target.get('range', False))

    def test_all_job_selection_remains_scoped_when_no_service_targets_exist(self):
        for name in ['attestation-signer', 'cubesigner-signer', 'proof-coordinator']:
            dashboard = dict(dashboards())[name]
            var = next(v for v in dashboard['templating']['list'] if v['name'] == 'job')
            self.assertIsNotNone(re.fullmatch(var['allValue'], name))
            self.assertIsNone(re.fullmatch(var['allValue'], 'prometheus'))
            self.assertIsNone(re.fullmatch(var['allValue'], ''))

    def test_time_histograms_are_not_queried_as_summary_quantiles(self):
        for name, dashboard in dashboards():
            for panel in walk(dashboard['panels']):
                for target in panel.get('targets', []):
                    expr = target.get('expr', '')
                    self.assertIsNone(re.search(
                        r'\b\w+(?:_seconds|_latency_ms)\{[^}]*quantile=', expr),
                        (name, panel['id'], expr))
                    if 'histogram_quantile(' in expr:
                        self.assertIn('_bucket{', expr)
                        self.assertIn('rate(', expr)
                        self.assertRegex(expr, r'by \([^)]*\ble\b')

    def test_overview_logs_accept_all_and_respect_service_selection(self):
        dashboard = dict(dashboards())['overview']
        variables = {v['name']: v for v in dashboard['templating']['list']}
        # Loki rejects selectors whose matchers all accept the empty string.
        self.assertIsNone(re.fullmatch(variables['namespace']['allValue'], ''))
        self.assertIsNone(re.fullmatch(variables['service']['allValue'], 'prometheus'))
        for panel in walk(dashboard['panels']):
            for target in panel.get('targets', []):
                ds = target.get('datasource', panel.get('datasource', {}))
                if ds.get('type') == 'loki':
                    self.assertIn('namespace=~"$namespace"', target['expr'])
                    self.assertIn('service=~"$service"', target['expr'])

    def test_pending_core_instrumentation_is_retained_and_explained(self):
        for name in ['attestation-signer', 'proof-coordinator']:
            dashboard = dict(dashboards())[name]
            rows = [p for p in dashboard['panels'] if p['type'] == 'row' and '#1007' in p['title']]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]['collapsed'])
            self.assertTrue(rows[0]['panels'])
            for panel in rows[0]['panels']:
                self.assertIn('#1007', panel['description'])

    def test_mixed_dimensions_use_explicit_units(self):
        for name, panel_id, ref, unit in [
            ('eth-da-submitter', 8, 'D', 's'),
            ('eth-da-submitter', 14, 'A', 'ops'),
            ('withdrawal-processor', 18, 'B', 'suffix:DOGE'),
            ('withdrawal-processor', 19, 'B', 'suffix:DOGE'),
            ('withdrawal-processor', 36, 'B', 's'),
        ]:
            panel = next(p for p in walk(dict(dashboards())[name]['panels']) if p['id'] == panel_id)
            override = next(o for o in panel['fieldConfig']['overrides']
                            if o['matcher'] == {'id': 'byFrameRefID', 'options': ref})
            self.assertIn({'id': 'unit', 'value': unit}, override['properties'])

    def test_native_dstack_gpu_labels_and_host_isolation(self):
        dashboard = dict(dashboards())['dstack']
        for panel in walk(dashboard['panels']):
            for target in panel.get('targets', []):
                expr = target.get('expr', '')
                self.assertNotIn('dstack_gpu_name', expr)
                if 'DCGM_' in expr:
                    source = 'host' if 'optional DCGM' in panel['title'] else 'native'
                    self.assertIn(f'dstack_source="{source}"', expr)


if __name__ == '__main__':
    unittest.main()
