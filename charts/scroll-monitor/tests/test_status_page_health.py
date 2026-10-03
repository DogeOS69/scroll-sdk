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


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import status_page_health as health


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

    def test_modes_and_unconfigured_rules(self):
        c = config()
        c['components']['deposits']['mode'] = 'manual'
        self.assertEqual(health.queries(c, 'deposits'), {})
        c['components']['deposits'] = {'rule': {'expr': 'my_health'}}
        self.assertEqual(health.queries(c, 'deposits'), {'custom': 'my_health'})
        c['health']['depositDeadlineSeconds'] = 0
        self.assertEqual(health.queue_query(c, 'deposits'), '')
        self.assertIn('namespace="monitoring"', health.workflow_query(c))

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
