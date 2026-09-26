#!/usr/bin/env python3
"""Opt-in real Grafana 11.1.5 -> verifier -> local HTTP receiver acceptance.

Called by the CLI publication test with its actual generated values. Requires
Docker with host networking and PyYAML. No requests leave the local test servers.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml

spec = importlib.util.spec_from_file_location('delivery', Path(__file__).parents[1] / 'scripts/status-page-delivery.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def wait_for(predicate, description, timeout=75):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError(description)


def run(values):
    captured = []
    notifications = []
    state = {'value': 1}
    stopped = threading.Event()
    delivery = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.reply({'status': 'success', 'data': {'resultType': 'vector', 'result': [] if state['value'] is None else [{'metric': {}, 'value': [time.time(), str(state['value'])]}]}})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path.startswith('/notify/'):
                payload = json.loads(body)
                notifications.append(payload)
                assert delivery.notify('public-rpc', payload, time.time()), payload
                self.reply({})
            elif self.path == '/provider':
                captured.append(json.loads(body))
                self.reply({})
            else:
                self.do_GET()

        def reply(self, body):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        grafana_port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='status-grafana-') as directory:
        root = Path(directory)
        config = copy.deepcopy(values['statusPage']['generated']['delivery'])
        config.update(prometheusUrl=url, intervalSeconds=0.5)
        config['components'] = {'public-rpc': config['components']['public-rpc']}
        component = config['components']['public-rpc']
        component.update(failureSeconds=1, recoverySeconds=3)
        os.environ[component['webhookEnv']] = url + '/provider'
        delivery = module.Delivery(config, root / 'delivery.sqlite3')
        def collect():
            while not stopped.is_set():
                delivery.collect()
                stopped.wait(0.5)
        collector = threading.Thread(target=collect, daemon=True)
        collector.start()
        provision = copy.deepcopy(values['grafana']['alerting']['instatus-component-publication.yaml'])
        provision['contactPoints'] = [p for p in provision['contactPoints'] if p['name'] == 'instatus-public-rpc']
        provision['contactPoints'][0]['receivers'][0]['settings']['url'] = url + '/notify/public-rpc'
        group = provision['groups'][0]
        group['interval'] = '10s'
        group['rules'] = [r for r in group['rules'] if r['uid'] == 'status-public-rpc']
        rule = group['rules'][0]
        rule['for'] = '0s'
        rule['notification_settings'].update(group_wait='0s', group_interval='10s', repeat_interval='1m')
        datasource_uid = rule['data'][0]['datasourceUid']
        for subdir in ['alerting', 'datasources']:
            (root / subdir).mkdir()
        (root / 'alerting/status.yaml').write_text(yaml.safe_dump(provision))
        (root / 'datasources/prometheus.yaml').write_text(yaml.safe_dump({'apiVersion': 1, 'datasources': [{'name': 'Prometheus', 'uid': datasource_uid, 'type': 'prometheus', 'url': url, 'access': 'proxy', 'jsonData': {'httpMethod': 'GET'}}]}))
        name = f'status-grafana-{os.getpid()}'
        try:
            subprocess.run(['docker', 'run', '-d', '--rm', '--name', name, '--network', 'host', '--user', str(os.getuid()), '-e', f'GF_SERVER_HTTP_PORT={grafana_port}', '-e', 'GF_ANALYTICS_REPORTING_ENABLED=false', '-e', 'GF_ANALYTICS_CHECK_FOR_UPDATES=false', '-e', 'GF_PATHS_PROVISIONING=/fixtures', '-e', 'GF_PATHS_DATA=/tmp/grafana-data', '-e', 'GF_PATHS_LOGS=/tmp/grafana-logs', '-v', f'{root}:/fixtures:ro', 'grafana/grafana:11.1.5'], check=True, capture_output=True)
            wait_for(lambda: bool(captured), 'Grafana firing was not accepted by verifier')
            assert len(captured) == 1 and captured[0]['status'] == 'firing'
            assert notifications and notifications[0]['alerts'][0]['labels']['managed_by'] == 'scroll-sdk-status-page'
            assert captured[0]['alerts'][0]['annotations'] == {}
            assert captured[0]['externalURL'] == ''
            state['value'] = None
            time.sleep(12)  # Grafana evaluates NoData, verifier sees unknown.
            assert len(captured) == 1, 'NoData incorrectly resolved the public incident'
            assert not delivery.notify('public-rpc', {'status': 'resolved'}, time.time())
            state['value'] = 0
            time.sleep(1)
            assert len(captured) == 1, 'recovery window was bypassed'
            wait_for(lambda: len(captured) == 2, 'continuous health did not resolve', timeout=15)
            assert captured[1]['status'] == 'resolved'
            assert captured[1]['alerts'][0]['startsAt'] == captured[0]['alerts'][0]['startsAt']
            assert captured[1]['groupKey'] == captured[0]['groupKey']
            print('PASS: actual Grafana firing, NoData hold, verified recovery, sanitized stable HTTP events')
        except Exception:
            logs = subprocess.run(['docker', 'logs', '--tail', '40', name], capture_output=True, text=True)
            print(logs.stdout + logs.stderr, file=sys.stderr)
            raise
        finally:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            stopped.set()
            collector.join(timeout=15)
            delivery.db.close()
            server.shutdown()
            server.server_close()
            os.environ.pop(component['webhookEnv'], None)


if __name__ == '__main__':
    run(yaml.safe_load(Path(sys.argv[1]).read_text()))
