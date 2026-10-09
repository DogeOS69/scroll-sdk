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
