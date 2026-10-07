"""Rule tests live with the evaluator. Opt-in PromQL execution needs Docker/promtool."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import status_page_health as health

# Helm supplies this field in the mounted shared definition. Local fixtures use
# the chart's default instead of maintaining another hard-coded runtime default.
health.L2_PROGRESS['windowSeconds'] = yaml.safe_load((SCRIPTS.parent / 'values.yaml').read_text())['businessAlerts']['l2BatchStallSeconds']


def config():
    return {'environment': 'testnet', 'chainId': '123', 'sourceNamespace': 'monitoring',
            'health': health.policy({'depositDeadlineSeconds': 600, 'withdrawalDeadlineSeconds': 900,
                                     'batchPublicationDeadlineSeconds': 300, 'wfStallSeconds': 300}),
            'components': {key: {'mode': 'observe', 'rule': {'builtin': True}} for key in health.COMPONENTS}}


class PolicyTests(unittest.TestCase):
    def test_unknown_does_not_hide_failure_or_manufacture_recovery(self):
        for facts, status, observation in [({}, 'unknown', 'partial'),
                ({'queue_deadline': None, 'workflow_stalled': 1}, 'unavailable', 'partial'),
                ({'queue_deadline': 1, 'workflow_stalled': None}, 'degraded', 'partial'),
                ({'queue_deadline': 2, 'workflow_stalled': 0}, 'degraded', 'partial'),
                ({'workflow_stalled': 2, 'queue_deadline': 0}, 'unavailable', 'partial'),
                ({'withdrawal_processor_unready': 1, 'queue_deadline': None}, 'unavailable', 'partial'),
                ({'tso_unready': 1, 'queue_deadline': 0}, 'unavailable', 'complete'),
                ({'l2_progress_stalled': 1, 'workflow_stalled': 0, 'queue_deadline': 0}, 'unavailable', 'complete'),
                ({'l2_progress_stalled': 2, 'workflow_stalled': 0}, 'unavailable', 'partial'),
                ({'l2_progress_stalled': None, 'queue_deadline': 0}, 'unknown', 'partial'),
                ({'queue_deadline': 0, 'workflow_stalled': None}, 'unknown', 'partial'),
                ({'queue_deadline': 0, 'workflow_stalled': 0}, 'operational', 'complete')]:
            with self.subTest(facts=facts):
                result = health.evaluate(facts)
                self.assertEqual((result['status'], result['observation']), (status, observation))
                self.assertEqual(result['assurance'], 'pipeline')

    def test_policy_inputs_are_validated(self):
        for value in [{'typo': 1}, {'freshnessSeconds': float('nan')}, {'failureFor': '0m'},
                      {'minimumProbeLocations': 1}, {'depositDeadlineSeconds': -1},
                      {'withdrawalProcessorExpectedTargets': 33}, {'freshnessSeconds': True}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                health.policy(value)
        self.assertEqual(health.seconds('12m'), 720)
        self.assertEqual(health.policy({})['depositDeadlineSeconds'], 0)
        self.assertEqual(health.L2_PROGRESS['windowSeconds'], 7500)

    def test_modes_and_unconfigured_rules(self):
        c = config()
        c['components']['deposits']['mode'] = 'manual'
        self.assertEqual(health.queries(c, 'deposits'), {})
        c['components']['deposits'] = {'rule': {'expr': 'my_health'}}
        self.assertEqual(health.queries(c, 'deposits'), {'custom': 'my_health'})
        c['health']['depositDeadlineSeconds'] = 0
        self.assertEqual(health.queue_query(c, 'deposits'), '')
        self.assertIn('namespace="monitoring"', health.workflow_query(c))
        self.assertIn('l2_progress_stalled', health.queries(c, 'withdrawals'))
        self.assertNotIn('l2_progress_stalled', health.queries(config(), 'deposits'))

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_l2_adoption_with_real_prometheus(self):
        labels = '{namespace="monitoring",job="withdrawal-processor",instance="writer"}'
        head = 'withdrawal_processor_protocol_state_l2_batch_height' + labels
        latest = 'withdrawal_processor_protocol_latest_da_batch_height' + labels
        base = {'up'+labels: '1x130', head: '137x130', latest: '346x130'}
        for source in ('l2', 'replay'):
            scoped = labels[:-1] + ',source="'+source+'"}'
            base['withdrawal_processor_protocol_snapshot_valid'+scoped] = '1x130'
            base['withdrawal_processor_protocol_snapshot_timestamp_seconds'+scoped] = '0+60x130'
        tests = []
        def scenario(name, series, expected, at='125m', cfg=None, window_seconds=None):
            with patch.dict(health.L2_PROGRESS, windowSeconds=window_seconds or health.L2_PROGRESS['windowSeconds']):
                expr = health.l2_progress_query(cfg or config())
            tests.append({'name': name, 'interval': '1m',
                'input_series': [{'series': k, 'values': v} for k, v in series.items()],
                'promql_expr_test': [{'expr': expr+'\n# '+name, 'eval_time': at,
                    'exp_samples': [] if expected is None else [{'labels': '{}', 'value': expected}]}]})
        scenario('l2-stalled-125m-even-with-empty-withdrawal-queue', base, 1)
        scenario('l2-not-yet-125m', base, None, '124m')
        scenario('l2-custom-600s-before-deadline', base, None, '9m', window_seconds=600)
        scenario('l2-custom-600s-at-deadline', base, 1, '10m', window_seconds=600)
        scenario('l2-custom-1800s-at-deadline', base, 1, '30m', window_seconds=1800)
        scenario('l2-non-minute-evaluation', base, 1, '125m30s')
        scenario('l2-idle', {**base, latest: '137x130'}, 0)
        scenario('l2-new-da-after-idle', {**base, latest: '137x120 346x9'}, 0)
        scenario('l2-new-target-insufficient-history', {
            k: '_x10 ' + ('600+60x120' if 'timestamp_seconds' in k else v)
            for k,v in base.items()}, None)
        scenario('l2-forward-progress', {**base, head: '137x120 138x9'}, 0)
        scenario('l2-rollback-is-not-recovery', {**base, head: '137x120 136x9'}, 1)
        scenario('l2-missing', {}, None)
        scenario('l2-wrong-namespace', {k.replace('monitoring','another'): v for k,v in base.items()}, None)
        scenario('l2-wrong-job', {k.replace('withdrawal-processor','proof-worker'): v for k,v in base.items()}, None)
        scenario('l2-down', {**base, 'up'+labels: '0x130'}, None)
        scenario('l2-invalid-height', {**base, head: '-1x130'}, None)
        scenario('l2-fractional-height', {**base, head: '137.5x130'}, None)
        for source in ('replay', 'l2'):
            scoped = labels[:-1] + ',source="'+source+'"}'
            valid = 'withdrawal_processor_protocol_snapshot_valid'+scoped
            stamp = 'withdrawal_processor_protocol_snapshot_timestamp_seconds'+scoped
            for name, metric, values in [('invalid', valid, '0x130'), ('stale', stamp, '0x130'),
                    ('future', stamp, '1+60x130'), ('gap', valid, '1x60 0 1x68'),
                    ('missing', valid, None)]:
                series = dict(base)
                if values is None: del series[metric]
                else: series[metric] = values
                scenario('l2-'+source+'-'+name, series, 2 if name == 'gap' else None)
        replaced = {}
        for k,v in base.items():
            replaced[k] = ('0+60x119' if 'timestamp_seconds' in k else v.split('x')[0]+'x119') + ' stale'
            replaced[k.replace('writer', 'replacement')] = '_x120 ' + ('7200+60x10' if 'timestamp_seconds' in k else v.split('x')[0]+'x10')
        scenario('l2-pod-ip-change-preserves-service-history', replaced, 1)
        interrupted = {k: v.replace('_x120 ', '_x121 ') for k,v in replaced.items()}
        # The replacement timestamp must match the later first observation.
        interrupted = {k: v.replace('7200+60x10', '7260+60x9') for k,v in interrupted.items()}
        scenario('l2-pod-ip-change-with-gap-is-partial-failure', interrupted, 2)
        recovered = {**interrupted, head.replace('writer', 'replacement'): '_x121 149x9'}
        scenario('l2-forward-progress-after-pod-replacement-proves-recovery', recovered, 0)
        rolled_back = {**base, head: '137x118 149x1 137x9'}
        scenario('l2-forward-then-rollback-does-not-prove-recovery', rolled_back, None)
        partial = {**base, 'up'+labels.replace('writer','missing'): '1x130'}
        scenario('l2-confirmed-failure-partial-coverage', partial, 2)
        scenario('l2-idle-partial-cannot-recover', {**partial, latest: '137x130'}, None)
        extra = copy.deepcopy(config()); extra['health']['withdrawalProcessorExpectedTargets'] = 2
        scenario('l2-vanished-target-still-failure', base, 2, cfg=extra)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'rules.json').write_text(json.dumps({'rule_files': [], 'evaluation_interval': '1m', 'tests': tests}))
            result = subprocess.run(['docker', 'run', '--rm', '--user', str(os.getuid()), '--entrypoint', 'promtool',
                '-v', directory+':/fixtures:ro', 'prom/prometheus:v2.52.0', 'test', 'rules', '/fixtures/rules.json'],
                text=True, capture_output=True, timeout=180)
            detail = '\n'.join(line.rsplit('# ', 1)[-1] if line.lstrip().startswith('expr:') else line
                               for line in (result.stdout+result.stderr).splitlines())
            self.assertEqual(result.returncode, 0, detail)

    @unittest.skipUnless(os.environ.get('SCROLL_STATUS_RUNTIME_TEST') == '1', 'requires Docker/promtool')
    def test_real_prometheus_evidence(self):
        c = config()
        tests = []
        def scenario(name, expression, series, expected, interval='1m', at='10m'):
            tests.append({'name': name, 'interval': interval,
                'input_series': [{'series': k, 'values': v} for k, v in series.items()],
                'promql_expr_test': [{'expr': expression, 'eval_time': at,
                    'exp_samples': [] if expected is None else [{'labels': '{}', 'value': expected}]}]})
        labels = '{namespace="monitoring",job="withdrawal-processor",instance="writer"}'
        def queue(backlog='0', age='0', stamp='600', valid='1'):
            return {k: (' '.join([v]*11) if v == 'NaN' else v+'x10') for k, v in {
                'up'+labels: '1', 'withdrawal_processor_public_deposit_eligible_backlog'+labels: backlog,
                'withdrawal_processor_public_deposit_oldest_eligible_age_seconds'+labels: age,
                'withdrawal_processor_public_deposit_snapshot_timestamp_seconds'+labels: stamp,
                'withdrawal_processor_public_deposit_snapshot_valid'+labels: valid}.items()}
        q = health.queue_query(c, 'deposits')
        for name, args, expected in [('idle', (), 0), ('deadline', ('1','600'), 0),
                ('overdue', ('1','601'), 1), ('stale', ('1','601','100'), None),
                ('invalid', ('1','601','600','0'), None), ('future', ('1','601','601'), None),
                ('nan', ('1','NaN'), None), ('negative', ('-1','0'), None), ('fractional', ('0.5','0'), None)]:
            scenario('queue-'+name, q, queue(*args), expected)
        for failed in (False, True):
            s = queue('1','601') if failed else queue()
            s['up{namespace="monitoring",job="withdrawal-processor",instance="missing"}'] = '1x10'
            scenario('partial-'+str(failed), q, s, 2 if failed else None)
        s = queue(); s['up'+labels] = '0x10'
        scenario('failed-scrape-not-process-death', q, s, None)
        scenario('no-targets', q, {}, None)
        scenario('wrong-network-namespace', q, {k.replace('monitoring','mainnet'): v for k,v in queue().items()}, None)
        more = copy.deepcopy(c); more['health']['withdrawalProcessorExpectedTargets'] = 2
        scenario('vanished-target', health.queue_query(more, 'deposits'), queue(), None)
        wf = health.workflow_query(c)
        def workflow(age='0', unchanged='599', head='1', valid='1'):
            jobs = labels[:-1]+',source="jobs"}'
            return {k: (' '.join([v]*11) if v == 'NaN' else v+'x10') for k,v in {
                'up'+labels: '1', 'withdrawal_processor_public_workflow_snapshot_valid'+labels: valid,
                'withdrawal_processor_public_workflow_snapshot_timestamp_seconds'+labels: '600',
                'withdrawal_processor_public_workflow_unchanged_seconds'+labels: unchanged,
                'withdrawal_processor_public_workflow_head_observed_timestamp_seconds'+labels: head,
                'withdrawal_processor_protocol_snapshot_valid'+jobs: '1',
                'withdrawal_processor_protocol_snapshot_timestamp_seconds'+jobs: '600',
                'withdrawal_processor_protocol_job_oldest_age_seconds'+labels[:-1]+',status="built",action_kind="advance_l2_build"}': age}.items()}
        for name,args,expected in [('idle', (),0), ('stalled',('601',),1),
                ('recent-progress',('601','0','590'),0), ('deadline',('300',),0),
                ('invalid-age',('NaN',),None), ('restart-idle',('0','0'),0),
                ('restart-overdue',('601','0'),None), ('invalid-head',('601','599','0'),None),
                ('future-head',('0','0','601'),None), ('invalid-snapshot',('0','599','1','0'),None),
                ('invalid-continuity',('0','NaN'),None), ('impossible-continuity',('601','599','590'),None)]:
            scenario('workflow-'+name, wf, workflow(*args), expected)
        for field, value in [('valid', '0x10'), ('timestamp_seconds', '100x10'),
                             ('timestamp_seconds', '601x10'), ('valid', None),
                             ('timestamp_seconds', None)]:
            for age in ('0', '601'):
                s = workflow(age)
                key = 'withdrawal_processor_protocol_snapshot_'+field+labels[:-1]+',source="jobs"}'
                if value is None:
                    s.pop(key)
                else:
                    s[key] = value
                scenario('retained-jobs-'+field+str(value)+age, wf, s, None)
        scenario('missing-workflow', wf, {}, None)
        wp = health.processor_query(c)
        ls = '{namespace="monitoring",statefulset="withdrawal-processor",job="kube-state-metrics",instance="ksm"}'
        supervisor = {name+ls: value for name,value in [
            ('kube_statefulset_status_replicas_ready','1x10'), ('kube_statefulset_replicas','1x10'),
            ('kube_statefulset_metadata_generation','2x10'), ('kube_statefulset_status_observed_generation','2x10')]}
        ksm_up = 'up{job="kube-state-metrics",instance="ksm"}'
        supervisor[ksm_up] = '1x10'
        scenario('processor-ready',wp,supervisor,0)
        scenario('processor-unready',wp,{**supervisor,'kube_statefulset_status_replicas_ready'+ls:'0x10'},1)
        scenario('processor-missing',wp,{},None)
        scenario('supervisor-down',wp,{**supervisor,ksm_up:'0x10'},None)
        scenario('supervisor-wrong-exporter',wp,{k.replace('instance="ksm"','instance="other"') if k==ksm_up else k:v for k,v in supervisor.items()},None)
        scenario('supervisor-stale',wp,{k:'1x4 _x6' for k in supervisor},None)
        scenario('supervisor-generation-unobserved',wp,{**supervisor,'kube_statefulset_metadata_generation'+ls:'3x10'},None)
        scenario('supervisor-duplicate',wp,{**supervisor,'kube_statefulset_status_replicas_ready'+ls.replace('ksm','duplicate'):'0x10'},None)
        tq = health.tso_query(c)
        ls = '{namespace="monitoring",job="tso-service",instance="tso"}'
        tso = {name+ls:value for name,value in [('up','1x10'),('tso_service_ready','1x10'),
            ('tso_service_readiness_snapshot_valid','1x10'),('tso_service_readiness_timestamp_seconds','600x10')]}
        scenario('tso-ready',tq,tso,0)
        scenario('tso-not-ready',tq,{**tso,'tso_service_ready'+ls:'0x10'},1)
        for metric,value in [('up','0x10'),('tso_service_ready','2x10'),('tso_service_readiness_snapshot_valid','0x10'),
                ('tso_service_readiness_timestamp_seconds','1x10'),('tso_service_readiness_timestamp_seconds','601x10')]:
            scenario('tso-invalid-'+metric+value,tq,{**tso,metric+ls:value},None)
        scenario('tso-missing',tq,{},None)
        def probes(a='0', b='0', stamp='600', official=False):
            prefix = 'scroll_status_node_sync' if official else 'scroll_status_probe'
            entries = [('collector',a)] if official else [('a',a),('b',b)]
            out = {}
            for location,value in entries:
                ls = '{environment="testnet",chain_id="123",component_key="'+('node-sync' if official else 'public-rpc')+'",location="'+location+'"}'
                out[prefix+'_affected'+ls] = ' '.join([value]*11)
                out[prefix+'_timestamp_seconds'+ls] = stamp+'x10'
            return out
        p = health.probe_query(c, 'public-rpc')
        for name,args,expected in [('healthy',(),0),('failed',('1','1'),1),('disagree',('0','1'),None),
                ('nan',('0','NaN'),None),('stale',('0','0','100'),None),('future',('0','0','601'),None)]:
            scenario('probe-'+name,p,probes(*args),expected)
        s=probes(); key=next(iter(s));s[key.replace('}',',instance="duplicate"}')]='0x10'
        scenario('duplicate-location',p,s,None)
        c['nodeSyncMode']='official';p=health.probe_query(c,'node-sync')
        for value,expected in [('0',0),('1',1),('2',None),('NaN',None)]:
            scenario('official-'+value,p,probes(value,official=True),expected)
        c['alloyProbes']={'targets':[{'environment':'testnet','chain_id':'123','component_key':'public-rpc',
              'check_id':'rpc-http','status_probe_config':'revision-a'}]}
        p=health.alloy_query(c,'public-rpc')
        ls='{job="status-page-alloy",environment="testnet",chain_id="123",component_key="public-rpc",check_id="rpc-http",status_probe_config="revision-a"}'
        base={name+ls:value for name,value in [('probe_success','1x10'),('probe_duration_seconds','0.1x10'),('up','1x10')]}
        scenario('alloy-healthy',p,base,0,'30s','5m')
        for metric,value,expected in [('probe_success','0x10',1),('probe_duration_seconds','3x10',1),
                ('probe_success',None,None),('probe_success','NaN NaN NaN NaN NaN NaN NaN NaN NaN NaN NaN',None),
                ('probe_success','2x10',None),('up','0x10',None),('probe_success','1x4 _x6',None),
                ('probe_success','stale',None),('probe_duration_seconds','0.1x4 _x6',None)]:
            s=dict(base)
            if value is None: del s[metric+ls]
            else: s[metric+ls]=value
            scenario('alloy-'+metric+'-'+str(value),p,s,expected,'30s','5m')
        s=dict(base);s['probe_success'+ls.replace('}',',instance="duplicate"}')]='1x10'
        scenario('alloy-duplicate',p,s,None,'30s','5m')
        scenario('alloy-old-revision',p,{k.replace('revision-a','revision-old'):v for k,v in base.items()},None,'30s','5m')
        c['alloyProbes']['targets'].append({**c['alloyProbes']['targets'][0], 'check_id':'second-rpc'})
        p = health.alloy_query(c,'public-rpc')
        scenario('alloy-missing-target-prevents-recovery',p,base,None,'30s','5m')
        scenario('alloy-confirmed-failure-survives-missing-target',p,{**base,'probe_success'+ls:'0x10'},2,'30s','5m')
        dashboard = json.loads((SCRIPTS.parent / 'grafana/dogeos-dashboards/status-health.json').read_text())
        for panel in dashboard['panels']:
            for target in panel['targets']:
                scenario('dashboard-'+str(panel['id'])+target['refId'],target['expr'],{},None)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'alerts.yaml').write_text((SCRIPTS.parent / 'alerts/status-page.yaml').read_text())
            Path(directory,'rules.json').write_text(json.dumps({'rule_files':['/fixtures/alerts.yaml'],'evaluation_interval':'1m','tests':tests}))
            result=subprocess.run(['docker','run','--rm','--user',str(os.getuid()),'--entrypoint','promtool','-v',directory+':/fixtures:ro',
                    'prom/prometheus:v2.52.0','test','rules','/fixtures/rules.json'],text=True,capture_output=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
