"""Prometheus HTTP -> evaluator -> durable journal -> local provider, no Grafana."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('runtime_delivery', SCRIPTS / 'status-page-delivery.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.state = {'value': 1, 'query_count': 0, 'sent': []}
        state = self.state
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                state['query_count'] += 1
                self.reply({'status':'success', 'data':{'resultType':'vector', 'result':
                    [] if state['value'] is None else [{'value':[time.time(),str(state['value'])]}]}})
            def do_POST(self):
                state['sent'].append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.reply({})
            def reply(self, body):
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(body).encode())
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.env = patch.dict(os.environ, TEST_PROVIDER=self.url+'/provider', INSTATUS_MONITORING_HEARTBEAT_URL=self.url+'/heartbeat')
        self.env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.config = {'schemaVersion':3,'environment':'testnet','chainId':'123','orgId':1,'groupName':'Testnet',
            'prometheusUrl':self.url,'heartbeatEnabled':True,'intervalSeconds':30,
            'components':{'public-rpc':{'name':'Public RPC','pageId':'page','componentId':'rpc',
                'mode':'automatic','rule':{'expr':'fixture_health'},'failureSeconds':0,'recoverySeconds':0,'webhookEnv':'TEST_PROVIDER'},
                'deposits':{'name':'Deposits','pageId':'page','componentId':'','mode':'observe','rule':{'builtin':True},'missing':'deadline-unconfigured'},
                'withdrawals':{'name':'Withdrawals','pageId':'page','componentId':'','mode':'manual'}}}
        self.dbpath = str(Path(self.temp.name)/'delivery.sqlite3')
        self.runtime = module.Delivery(self.config,self.dbpath)
    def tearDown(self):
        self.runtime.db.close(); self.server.shutdown(); self.server.server_close(); self.env.stop(); self.temp.cleanup()
    def collect(self):
        self.runtime.collect()
        self.runtime.deliver_once()
        self.runtime.deliver_once()  # heartbeat when no pending event remains
    def events(self, path):
        return [event for url,event in self.state['sent'] if url == path]
    def test_publication_and_recovery_work_without_grafana(self):
        self.collect()
        first = self.events('/provider')[0]
        self.assertEqual(first['status'],'firing')
        self.assertEqual(first['alerts'][0]['labels']['environment'],'testnet')
        self.assertEqual(len(self.events('/heartbeat')),1) # Known fault is not monitoring loss.
        self.state['value'] = None
        self.collect()
        self.assertEqual(len(self.events('/provider')),1)
        self.assertEqual(len(self.events('/heartbeat')),1)
        self.assertEqual(self.runtime.decisions['public-rpc']['status'],'unknown')
        self.runtime.db.close()
        self.runtime = module.Delivery(self.config,self.dbpath)
        self.state['value'] = 0
        self.collect()
        recovered = self.events('/provider')[-1]
        self.assertEqual(recovered['status'],'resolved')
        self.assertEqual(recovered['groupKey'],first['groupKey'])
        self.assertEqual(recovered['alerts'][0]['startsAt'],first['alerts'][0]['startsAt'])
        before = self.state['query_count']
        self.assertIn('status="operational"} 1',self.runtime.metrics())
        self.runtime.metrics()
        self.assertEqual(self.state['query_count'],before) # Metrics scrapes never re-evaluate.
    def test_unbound_observe_can_be_bound_later_without_replacing_journal(self):
        self.collect()
        self.runtime.db.close()
        self.config['components']['deposits'].update(componentId='deposit-real-id',mode='automatic',webhookEnv='TEST_PROVIDER',rule={'expr':'fixture_health'})
        del self.config['components']['deposits']['missing']
        self.runtime = module.Delivery(self.config,self.dbpath)
        self.assertEqual(self.runtime.db.execute('SELECT count(*) FROM events').fetchone()[0],2)
    def test_partial_builtin_fault_keeps_failure_but_stops_heartbeat(self):
        self.runtime.components['public-rpc']['rule'] = {'builtin': True}
        self.state['value'] = 2
        self.collect()
        self.assertEqual(self.events('/provider')[0]['status'], 'firing')
        self.assertEqual(self.runtime.decisions['public-rpc']['observation'], 'partial')
        self.assertEqual(self.events('/heartbeat'), [])
    def test_custom_expression_cannot_use_internal_partial_code(self):
        self.state['value'] = 2
        self.collect()
        self.assertEqual(self.runtime.decisions['public-rpc']['status'], 'unknown')
        self.assertEqual(self.events('/provider'), [])
    def test_shared_queries_are_deduplicated_and_delivery_error_stops_heartbeat(self):
        self.runtime.components['deposits'].update(rule={'expr':'fixture_health'})
        del self.runtime.components['deposits']['missing']
        def unavailable(*_):
            raise TimeoutError('not logged')
        self.runtime.send = unavailable
        self.collect()
        self.assertEqual(self.state['query_count'],1)
        self.assertEqual(self.events('/heartbeat'),[])
        self.assertIn('scroll_status_delivery_error{component_key="public-rpc"} 1',self.runtime.metrics())


if __name__ == '__main__':
    unittest.main()
