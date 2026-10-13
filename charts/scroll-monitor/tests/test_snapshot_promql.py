"""Evaluate cached-fact guards using shipped alert and dashboard expressions.

Run with SCROLL_STATUS_RUNTIME_TEST=1; requires Helm, Docker and PyYAML.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml
from test_monitoring_templates import grafana_rules, render

CHART = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
class SnapshotPromQLTests(unittest.TestCase):
    def test_head_jobs_rolling_upgrade_and_observation_alert(self):
        rules = grafana_rules(render())
        queue = rules['WFBuildQueueStalled']
        observation = rules['WPProtocolObservationUnavailable']
        self.assertEqual(queue['for'], '10m')
        self.assertEqual(observation['for'], '5m')
        prefix = 'withdrawal_processor_protocol_'
        target = {'namespace': 'monitoring', 'job': 'withdrawal-processor', 'instance': 'writer'}
        job_labels = {**target, 'status': 'bug', 'action_kind': 'advance_l1_build', 'pod': 'wp-0'}

        def labels(values):
            return '{'+','.join(f'{k}="{v}"' for k, v in sorted(values.items()))+'}'

        def key(metric, extra=None, on=None):
            return prefix+metric+labels({**(on or target), **(extra or {})})

        def controls(source, on=None):
            return {key('snapshot_valid', {'source': source}, on): '1x20',
                    key('snapshot_timestamp_seconds', {'source': source}, on): '0+60x20',
                    'up'+labels(on or target): '1x20'}

        old = key('job_oldest_age_seconds', job_labels)
        head = key('job_head_oldest_age_seconds', job_labels)
        base = {old: '10000x20', **controls('jobs')}
        new = {**base, head: '0x20', **controls('job_head')}
        cases = []

        def check(name, series, expected, expression=None):
            cases.append({'name': name, 'interval': '1m', 'input_series': [
                {'series': k, 'values': v} for k, v in series.items()],
                'promql_expr_test': [{'expr': expression or queue['expr'], 'eval_time': '10m',
                    'exp_samples': expected}]})

        sample = {'labels': prefix+'job_oldest_age_seconds'+labels(job_labels), 'value': 10000}
        check('old image keeps original labels and fallback', base, [sample])
        check('historical bug no longer blocks canonical head', new, [])
        for status in ('queued', 'building', 'built', 'failed_retryable', 'bug'):
            current_labels = {**job_labels, 'status': status}
            current = key('job_head_oldest_age_seconds', current_labels)
            check('current head '+status, {**new, current: '1801x20'}, [
                {'labels': prefix+'job_head_oldest_age_seconds'+labels(current_labels), 'value': 1801}])
        for status in ('awaiting_replay', 'succeeded'):
            current = key('job_head_oldest_age_seconds', {**job_labels, 'status': status})
            check('excluded status '+status, {**new, current: '10000x20'}, [])

        # A new image on a neighbor must not suppress a legacy target's fallback.
        for field, value in (('namespace', 'mainnet'), ('job', 'wp-other'), ('instance', 'neighbor')):
            neighbor = {**target, field: value}
            series = {**base, **controls('job_head', neighbor),
                      key('job_head_oldest_age_seconds', {'status': 'bug'}, neighbor): '0x20'}
            check('mixed versions isolated by '+field, series, [sample])

        # Seeing any part of the new contract establishes support, even on failed refresh.
        for marker, value in ((head, '0x20'),
                              (key('snapshot_valid', {'source': 'job_head'}), '0x20'),
                              (key('snapshot_timestamp_seconds', {'source': 'job_head'}), '0x20')):
            check('partial new contract blocks legacy fallback '+marker, {**base, marker: value}, [])
        valid = key('snapshot_valid', {'source': 'job_head'})
        stamp = key('snapshot_timestamp_seconds', {'source': 'job_head'})
        for marker, value in ((valid, '0x20'), (valid, None), (stamp, None),
                              (stamp, '0x20'), (stamp, '1200x20'), ('up'+labels(target), '0x20')):
            series = {**new, head: '10000x20'}
            if value is None:
                series.pop(marker)
            else:
                series[marker] = value
            check('invalid head never falls back '+marker+str(value), series, [])

        # Evaluate the actual alert timers and inclusive boundary, not just expressions.
        for metric, source in ((old, 'jobs'), (head, 'job_head')):
            for age in (1800, 1801):
                series = {metric: f'{age}x20', **controls(source)}
                case = {'name': f'{source} age {age} pending duration', 'interval': '1m',
                        'input_series': [{'series': k, 'values': v} for k, v in series.items()],
                        'promql_expr_test': []}
                for minute in (9, 10):
                    case['promql_expr_test'].append({
                        'expr': 'ALERTS{alertname="WFBuildQueueStalled",alertstate="firing"}',
                        'eval_time': f'{minute}m', 'exp_samples': [{
                            'labels': 'ALERTS'+labels({**job_labels, **queue['labels'],
                                'alertname': 'WFBuildQueueStalled', 'alertstate': 'firing'}),
                            'value': 1}] if age > 1800 and minute >= 10 else []})
                cases.append(case)

        # Existing independent snapshot warning covers job_head without duplicate rules.
        for mode in ('invalid', 'stale', 'future', 'missing timestamp', 'healthy', 'legacy'):
            series = dict(new)
            if mode == 'invalid': series[valid] = '0x20'
            if mode == 'stale': series[stamp] = '-120x20'
            if mode == 'future': series[stamp] = '1200x20'
            if mode == 'missing timestamp': series.pop(stamp)
            if mode == 'legacy': series = dict(base)
            case = {'name': 'job_head observation '+mode, 'interval': '1m',
                    'input_series': [{'series': k, 'values': v} for k, v in series.items()],
                    'promql_expr_test': []}
            for minute in (4, 5):
                case['promql_expr_test'].append({
                    'expr': 'ALERTS{alertname="WPProtocolObservationUnavailable",source="job_head",alertstate="firing"}',
                    'eval_time': f'{minute}m', 'exp_samples': [{
                        'labels': 'ALERTS'+labels({**target, **observation['labels'], 'source': 'job_head',
                            'alertname': 'WPProtocolObservationUnavailable', 'alertstate': 'firing'}),
                        'value': 1}] if mode not in ('healthy', 'legacy') and minute >= 5 else []})
            cases.append(case)
        with tempfile.TemporaryDirectory(prefix='scroll-head-job-promql-') as directory:
            root = Path(directory)
            root.chmod(0o755)
            native = [{k: v for k, v in rule.items() if k in ('alert', 'expr', 'for', 'labels', 'annotations')}
                      for rule in (queue, observation)]
            (root/'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'wf', 'rules': native}]}))
            (root/'tests.yaml').write_text(yaml.safe_dump({
                'rule_files': ['/work/rules.yaml'], 'evaluation_interval': '1m', 'tests': cases}))
            subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'promtool',
                '-v', f'{root}:/work:ro', 'prom/prometheus:v2.52.0', 'test', 'rules', '/work/tests.yaml'], check=True)

    def test_cached_evidence_is_scoped_and_fresh(self):
        rules = grafana_rules(render('--set', 'businessAlerts.requiredSignersByRole.Correctness=2'))
        cases = []
        def check(name, expr, series, present):
            cases.append({'name': name, 'interval': '1m',
                'input_series': [{'series': k, 'values': v+'x10'} for k,v in series.items()],
                'promql_expr_test': [{'expr': 'count('+expr+') or vector(0)', 'eval_time': '10m',
                    'exp_samples': [{'labels': '{}', 'value': int(present)}]}]})
        def exercise(name, expr, payload, source):
            ls = '{namespace="monitoring",job="tso-service",instance="writer"}'
            extra = ',source="'+source+'"' if source not in ('registry','status') else ''
            controls = ls[:-1]+extra+'}'
            valid, stamp = {
                'registry': ('tso_core_registry_snapshot_valid','tso_core_registry_snapshot_timestamp_seconds'),
                'status': ('tso_core_metrics_snapshot_valid','tso_core_observation_timestamp_seconds'),
            }.get(source, ('withdrawal_processor_protocol_snapshot_valid',
                           'withdrawal_processor_protocol_snapshot_timestamp_seconds'))
            s = {metric+ls[:-1]+labels+'}': value for metric,labels,value in payload}
            s.update({'up'+ls: '1', valid+controls:'1', stamp+controls:'600'})
            check(name+'-fresh',expr,s,True)
            for key,value in [(valid+controls,'0'),(stamp+controls,'480'),(stamp+controls,'601'),
                              ('up'+ls,'0'),(valid+controls,None),(stamp+controls,None)]:
                bad=copy.deepcopy(s)
                if value is None: bad.pop(key)
                else: bad[key]=value
                # A healthy other instance or network cannot validate retained payload.
                for metric in ['up'+ls,valid+controls,stamp+controls]:
                    bad[metric.replace('writer','neighbor')]=s[metric]
                    bad[metric.replace('monitoring','mainnet')]=s[metric]
                if extra:
                    bad[valid+controls.replace(source,'unrelated')]='1'
                    bad[stamp+controls.replace(source,'unrelated')]='600'
                check(name+'-'+key+str(value),expr,bad,False)
        specs = [
            ('TSONoRegisteredSigners','tso_core_registered_signers_count','','0','registry'),
            ('TSOCorrectnessQuorumUnavailable','tso_core_registered_signers_by_role',',role="Correctness"','1','registry'),
            ('TSOSigningQueueLarge','tso_core_transactions_by_status',',status="collecting_signatures"','10000','status'),
            ('TSOSigningProgressStalled','tso_core_transactions_by_status',',status="proposed"','1','status'),
            ('WFJobStalled','withdrawal_processor_protocol_job_oldest_age_seconds',',status="awaiting_replay",action_kind="advance_l2"','10000','jobs'),
            ('WFBuildQueueStalled','withdrawal_processor_protocol_job_oldest_age_seconds',',status="building",action_kind="advance_l2"','10000','jobs'),
            ('WFBuildQueueStalled','withdrawal_processor_protocol_job_head_oldest_age_seconds',',status="building",action_kind="advance_l2"','10000','job_head'),
            ('ProofWorkRetryBudgetExhausted','withdrawal_processor_proof_work_stuck_item_count',',proof_family="scroll_batch"','1','proof_work'),
        ]
        for alert,phase in [('ProofMaterializationQueueStalled','materialize'),
                            ('ProofVerificationQueueStalled','verify'),('ProofWorkerQueueStalled','prove')]:
            specs.append((alert,'withdrawal_processor_proof_work_oldest_age_seconds',
                          ',phase="'+phase+'",status="pending",proof_family="scroll_batch"','10000','proof_work'))
        for name,metric,labels,value,source in specs:
            exercise(name,rules[name]['expr'],[(metric,labels,value)],source)
        # Use real dashboard expressions, including the independent WP namespace selector.
        for dashboard,panel_id,metric,labels,source in [
            ('withdrawal-processor',10,'withdrawal_processor_protocol_job_count',',status="queued",action_kind="advance_l2"','jobs'),
            ('withdrawal-processor',1,'withdrawal_processor_protocol_state_wf_tx_number','','replay'),
            ('withdrawal-processor',24,'withdrawal_processor_protocol_latest_da_batch_height','','l2'),
            ('withdrawal-processor',43,'withdrawal_processor_advance_l2_l2_end_block',',stage="completed"','advance_l2'),
            ('proof-coordinator',112,'withdrawal_processor_proof_work_item_count',',phase="prove",status="pending",proof_family="scroll_batch"','proof_work'),
            ('tso-service',1,'tso_core_registered_signers_count','','registry'),
            ('tso-service',6,'tso_core_transactions_by_status',',status="proposed"','status'),
        ]:
            doc=json.loads((CHART/'grafana/dogeos-dashboards'/f'{dashboard}.json').read_text())
            panel=next(p for p in doc['panels'] if p['id']==panel_id)
            expr=next(t['expr'] for t in panel['targets'] if metric+'{' in t['expr'])
            expr=expr.replace('$wp_namespace','monitoring').replace('$namespace',
                'coordinator' if dashboard=='proof-coordinator' else 'monitoring')
            expr=expr.replace('$job','.*').replace('$instance','.*')
            exercise(dashboard+str(panel_id),expr,[(metric,labels,'42')],source)
        with tempfile.TemporaryDirectory(prefix='scroll-snapshot-promql-') as directory:
            root=Path(directory);root.chmod(0o755)
            (root/'tests.yaml').write_text(yaml.safe_dump({'rule_files':[], 'tests':cases}))
            subprocess.run(['docker','run','--rm','--network','none','--entrypoint','promtool',
                '-v',f'{root}:/work:ro','prom/prometheus:v2.52.0','test','rules','/work/tests.yaml'],check=True)
