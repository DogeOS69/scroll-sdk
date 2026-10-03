"""Render actual rules and run Prometheus semantic tests; no cluster/provider access.

Usage: python3 charts/scroll-monitor/tests/check_dstack_alerts.py
Requires Docker with prom/prometheus:v2.52.0 cached and PyYAML.
"""
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

CHART = Path(__file__).resolve().parents[1]
output = subprocess.check_output([
    'helm', 'template', 'monitor', str(CHART), '--namespace', 'monitoring',
    '-f', str(CHART / 'values/dstack.yaml'), '--set', 'dstack.gpuHosts.enabled=true',
    '--set', 'dstack.gpuHosts.expectedHosts[0]=gpu-01',
    '--set', 'dstack.gpuHosts.expectedHosts[1]=gpu-02',
], text=True)
config = next(d for d in yaml.safe_load_all(output) if d and d['kind'] == 'ConfigMap'
              and d['metadata']['name'] == 'monitor-grafana-alerts')
groups = [g for g in json.loads(config['data']['rules.json'])['groups'] if g['name'].startswith('dogeos.dstack')]
annotations = {r['alert']: r['annotations'] for g in groups for r in g['rules']}
suite = yaml.safe_load((CHART / 'tests/dstack-alerts.test.yaml').read_text())
for test in suite['tests']:
    for check in test['alert_rule_test']:
        for expected in check['exp_alerts']:
            expected['exp_annotations'] = annotations[check['alertname']]
with tempfile.TemporaryDirectory(prefix='dstack-promtool-') as directory:
    root = Path(directory)
    root.chmod(0o755)  # promtool container uses an unprivileged uid.
    (root / 'rules.yaml').write_text(yaml.safe_dump({'groups': groups}))
    (root / 'tests.yaml').write_text(yaml.safe_dump(suite))
    subprocess.run(['docker', 'run', '--rm', '--network', 'none', '-v', f'{directory}:/tests:ro',
                    '-w', '/tests', '--entrypoint', 'promtool', 'prom/prometheus:v2.52.0',
                    'test', 'rules', '/tests/tests.yaml'], check=True)
