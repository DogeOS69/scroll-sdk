"""Local-only integration: rendered Alloy -> Prometheus, plus HTTP/RPC failures.

Invoked by the CLI acceptance suite with rendered config.alloy and probes.json.
Requires the pinned Docker images locally. Never contacts real public endpoints.
"""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


root = Path(sys.argv[1])
config = json.loads((root / 'probes.json').read_text())
targets = {target['check_id']: target for target in config['targets']}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        key = parsed.path.rsplit('/', 1)[-1]
        case = urllib.parse.parse_qs(parsed.query).get('case', ['ok'])[0]
        status = {'failure': 500, 'redirect': 302}.get(case, 200)
        self.send_response(status)
        self.send_header('Content-Type', 'text/html' if '-page-' in key else 'application/json')
        if case == 'redirect':
            self.send_header('Location', '/check/' + key)
        self.end_headers()
        body = '<html>healthy</html>' if '-page-' in key else json.dumps({'results': [], 'total': 0, 'healthy': True})
        self.wfile.write(body.encode())

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        key = parsed.path.rsplit('/', 1)[-1]
        case = urllib.parse.parse_qs(parsed.query).get('case', ['ok'])[0]
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        self.send_header('Content-Type', 'text/html' if case == 'html' else 'application/json')
        self.end_headers()
        value = hex(int(targets[key]['chain_id'])) if request['method'] == 'eth_chainId' else '0x2a'
        if case == 'wrong-chain':
            value = '0x1'
        result = {'jsonrpc': '2.0', 'id': 1, 'result': value}
        if case == 'rpc-error':
            result['error'] = {'code': -32000, 'message': 'unavailable'}
        if case == 'malformed':
            result = {'unexpected': True}
        body = json.dumps(result)
        if case == 'duplicate':
            body = body[:-1] + ', \"result\": \"0x1\"}'
        if case == 'malformed-text':
            body = body[1:-1]
        if case == 'reordered':
            body = json.dumps(dict(reversed(list(result.items()))), indent=2)
        self.wfile.write(body.encode())


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def get(url):
    with urllib.request.urlopen(url, timeout=12) as response:
        return response.read().decode()


def eventually(check, seconds=45):
    deadline = time.monotonic() + seconds
    error = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except Exception as exc:
            error = exc
        time.sleep(0.2)
    raise AssertionError(f'Local runtime did not become ready: {error}')


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
origin = f'http://127.0.0.1:{server.server_port}'
prom_port, alloy_port = port(), port()
prom_url, alloy_url = f'http://127.0.0.1:{prom_port}', f'http://127.0.0.1:{alloy_port}'
source = (root / 'config.alloy').read_text()
for target in config['targets']:
    # Replace each address inside its own target block, including repeated RPC URLs.
    pattern = r'(name\s*=\s*' + re.escape(json.dumps(target['name'])) + r'\s+address\s*=\s*)"[^"\n]+"'
    source, count = re.subn(pattern, lambda m: m[1] + json.dumps(origin + '/check/' + target['check_id']), source)
    assert count == 1
source = source.replace('http://prometheus-prometheus:9090/api/v1/write', prom_url + '/api/v1/write')
assert 'discovery.kubernetes' not in source and 'loki.write' not in source
(root / 'runtime.alloy').write_text(source)
(root / 'prometheus.yaml').write_text('global:\n  scrape_interval: 30s\nscrape_configs: []\n')
containers = []


def start(image, *args):
    command = ['docker', 'run', '-d', '--rm', '--network', 'host', '--read-only',
               '--tmpfs', '/tmp:rw,size=256m', '--user', str(os.getuid()),
               '-v', f'{root}:/fixtures:ro', image, *args]
    container = subprocess.check_output(command, text=True).strip()
    containers.append(container)
    return container


try:
    start('prom/prometheus:v2.52.0', '--config.file=/fixtures/prometheus.yaml',
          '--storage.tsdb.path=/tmp/prometheus', '--web.enable-remote-write-receiver',
          f'--web.listen-address=127.0.0.1:{prom_port}')
    eventually(lambda: get(prom_url + '/-/ready'))
    start('grafana/alloy:v1.8.2', 'run', '--disable-reporting', '--storage.path=/tmp/alloy',
          f'--server.http.listen-addr=127.0.0.1:{alloy_port}', '/fixtures/runtime.alloy')
    eventually(lambda: get(alloy_url + '/-/ready'))
    query = urllib.parse.urlencode({'query': 'probe_success{job="status-page-alloy"}'})

    def received():
        rows = json.loads(get(prom_url + '/api/v1/query?' + query))['data']['result']
        return rows if len(rows) == len(targets) else None

    rows = eventually(received)
    for row in rows:
        labels = row['metric']
        expected = targets[labels['check_id']]
        for label in ['environment', 'chain_id', 'component_key', 'status_probe_config']:
            assert labels[label] == expected[label], (label, labels)
        assert row['value'][1] == '1', row

    rpc_target = next(t for t in targets.values() if '-chain-id-' in t['name'])
    page_target = next(t for t in targets.values() if '-page-' in t['name'])

    def probe(target, case, expected):
        url = origin + '/check/' + target['check_id'] + '?case=' + case
        query = urllib.parse.urlencode({'target': url, 'module': target['module']})
        metrics = get(alloy_url + '/api/v0/component/prometheus.exporter.blackbox.status_page/metrics?' + query)
        assert re.search(r'^probe_success ' + str(expected) + '$', metrics, re.M), (case, metrics)

    probe(rpc_target, 'ok', 1)
    probe(rpc_target, 'reordered', 1)
    for case in ['wrong-chain', 'rpc-error', 'malformed', 'html', 'duplicate', 'malformed-text']:
        probe(rpc_target, case, 0)
    probe(page_target, 'ok', 1)
    for case in ['failure', 'redirect']:
        probe(page_target, case, 0)
    print(f'Alloy v1.8.2: {len(rows)} checks reached Prometheus with correct labels; HTTP/RPC failures rejected.')
except Exception:
    for container in containers:
        print(subprocess.run(['docker', 'logs', '--tail', '25', container], capture_output=True, text=True).stderr, file=sys.stderr)
    raise
finally:
    for container in reversed(containers):
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True, check=False)
    server.shutdown()
