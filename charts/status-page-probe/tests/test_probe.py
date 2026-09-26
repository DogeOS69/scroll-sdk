import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('probe', Path(__file__).resolve().parents[1] / 'scripts/probe.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.chain = '0x7b'
        self.rpc_error = False
        self.site_broken = False
        self.api_ok = True
        test = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(self.rpc_response(data)).encode())
            def rpc_response(self, data):
                value = {'eth_chainId': test.chain, 'eth_blockNumber': '0x1', 'eth_getBlockByNumber': {
                    'number': '0x1', 'hash': '0x' + 'ab'*32, 'timestamp': hex(int(time.time()))}}[data['method']]
                payload = {'jsonrpc': '2.0', 'id': 1, **({'error': {'code': -32603}} if test.rpc_error else {'result': value})}
                return payload
            def do_GET(self):
                if self.headers.get('Upgrade', '').lower() == 'websocket':
                    accept = base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                    self.send_response(101)
                    self.send_header('Upgrade', 'websocket')
                    self.send_header('Connection', 'Upgrade')
                    self.send_header('Sec-WebSocket-Accept', accept)
                    self.end_headers()
                    _, size = self.rfile.read(2)
                    masked, size = size & 128, size & 127
                    if size == 126:
                        size = struct.unpack('!H', self.rfile.read(2))[0]
                    mask = self.rfile.read(4) if masked else None
                    raw = self.rfile.read(size)
                    if mask:
                        raw = bytes(value ^ mask[index % 4] for index, value in enumerate(raw))
                    payload = json.dumps(self.rpc_response(json.loads(raw))).encode()
                    header = bytes([129, len(payload)]) if len(payload) < 126 else bytes([129, 126]) + struct.pack('!H', len(payload))
                    self.wfile.write(header + payload)
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json' if self.path == '/api' else 'text/html')
                self.end_headers()
                if self.path == '/api':
                    self.wfile.write(json.dumps({'ok': test.api_ok}).encode())
                elif test.site_broken:
                    self.wfile.write(b'<html><div id="root"></div><script>throw Error("broken bundle")</script></html>')
                else:
                    self.wfile.write(b'''<html><script>window.REACT_APP_CHAIN_ID_L2='123'</script>
                    <button role="tab">Deposit to DogeOS</button><button role="tab">Withdraw to Dogecoin</button>
                    <input placeholder="Enter 0x... address" oninput="document.querySelector('code').textContent='00'+this.value.slice(2)">
                    <code></code><div role="tabpanel">Working application</div></html>''')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.config = {'environment': 'testnet', 'chainId': '123', 'rpcUrls': [self.url], 'maxRpcLatencySeconds': 2,
                       'maxBlockAgeSeconds': 120, 'maxIndexLagSeconds': 120, 'maxNodeLagSeconds': 120,
                       'sequencingMode': 'continuous', 'bridgeUrls': [self.url], 'explorerUrls': [],
                       'bridgeChecks': [{'url': self.url+'/api','path': ['ok'], 'equals': True}]}
        self.probe = module.Probe(self.config, 'fixture-location')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_http_200_wrong_chain_or_jsonrpc_error_is_a_real_failure(self):
        self.assertEqual(module.block(self.url, '123')['height'], 1)
        self.chain = '0x1'
        with self.assertRaises(module.TargetFailure):
            module.block(self.url, '123')
        self.chain = '0x7b'
        self.rpc_error = True
        with self.assertRaises(module.TargetFailure):
            module.block(self.url, '123')

    def test_real_websocket_transport_validates_chain_and_rpc_errors(self):
        url = self.url.replace('http:', 'ws:')
        self.assertEqual(module.block(url, '123')['height'], 1)
        self.chain = '0x1'
        with self.assertRaises(module.TargetFailure):
            module.block(url, '123')
        self.chain = '0x7b'
        self.rpc_error = True
        with self.assertRaises(module.TargetFailure):
            module.block(url, '123')

    def test_missing_browser_or_optional_inputs_are_unknown_without_hiding_rpc(self):
        with patch.object(self.probe, 'browser', side_effect=module.Unknown):
            self.probe.cycle()
        self.assertEqual(self.probe.samples['public-rpc'][0], 0)
        self.assertEqual(self.probe.samples['sequencing'][0], 0)
        for key in ['bridge-portal','block-explorer','node-sync']:
            self.assertNotIn(key,self.probe.samples)

    def test_failed_rpc_does_not_accuse_sequencing(self):
        self.rpc_error = True
        with patch.object(self.probe, 'browser', side_effect=module.Unknown):
            self.probe.cycle()
        self.assertEqual(self.probe.samples['public-rpc'][0],1)
        self.assertNotIn('sequencing',self.probe.samples)

    def test_idle_on_demand_chain_requires_eligible_work_rule(self):
        self.config['sequencingMode']='on-demand'
        with patch.object(self.probe, 'browser', side_effect=module.Unknown):
            self.probe.cycle()
        self.assertNotIn('sequencing',self.probe.samples)

    def test_json_checks_validate_content(self):
        module.check_json(self.config['bridgeChecks'][0])
        self.api_ok = False
        with self.assertRaises(module.TargetFailure):
            module.check_json(self.config['bridgeChecks'][0])

    @unittest.skipUnless(os.environ.get('STATUS_PROBE_BROWSER_TEST') == '1', 'opt-in Chromium integration')
    def test_real_browser_checks_rendered_interactions_and_supporting_api(self):
        self.probe.browser(self.url, bridge=True)
        self.api_ok = False
        with self.assertRaises(module.TargetFailure):
            self.probe.browser(self.url, bridge=True)
        self.api_ok = True
        self.site_broken = True
        with self.assertRaises(module.TargetFailure):
            self.probe.browser(self.url, bridge=True)


if __name__ == '__main__':
    unittest.main()
