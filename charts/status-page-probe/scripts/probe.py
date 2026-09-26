#!/usr/bin/env python3
"""Public, read-only checks. Never send transactions or connect a wallet."""
import collections
from contextlib import closing
import json
import math
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class TargetFailure(Exception):
    pass


class Unknown(Exception):
    pass


def need(condition):
    if not condition:
        raise TargetFailure()


def http_json(url, payload=None, timeout=5):
    try:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        # Redirects must not hide a broken endpoint behind a login/error page.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            need(len(raw) <= 2 * 1024 * 1024)
            return json.loads(raw)
    except Exception as exc:
        raise TargetFailure() from exc


def rpc(url, method, params=None):
    request = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or []}
    if url.startswith(('ws:', 'wss:')):
        try:
            import websocket
            with closing(websocket.create_connection(url, timeout=5)) as connection:
                connection.send(json.dumps(request))
                raw = connection.recv()
                need(len(raw) <= 2 * 1024 * 1024)
                result = json.loads(raw)
        except ImportError as exc:
            raise Unknown() from exc
        except Exception as exc:
            raise TargetFailure() from exc
    else:
        result = http_json(url, request)
    need(isinstance(result, dict) and result.get('jsonrpc') == '2.0' and result.get('id') == 1 and 'error' not in result and 'result' in result)
    return result['result']


def quantity(value):
    need(isinstance(value, str) and re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', value))
    return int(value, 16)


def block(url, chain_id):
    need(quantity(rpc(url, 'eth_chainId')) == int(chain_id))
    height = quantity(rpc(url, 'eth_blockNumber'))
    result = rpc(url, 'eth_getBlockByNumber', [hex(height), False])
    need(isinstance(result, dict))
    need(quantity(result.get('number')) == height)
    need(isinstance(result.get('hash'), str) and re.fullmatch(r'0x[0-9a-fA-F]{64}', result['hash']) is not None)
    timestamp = quantity(result.get('timestamp'))
    need(0 < timestamp <= time.time() + 10)
    return {'height': height, 'hash': result['hash'].lower(), 'timestamp': timestamp, 'url': url}


def check_json(check):
    value = http_json(check['url'])
    for part in check['path']:
        need(isinstance(value, (list, dict)))
        try:
            value = value[part]
        except (KeyError, IndexError, TypeError) as exc:
            raise TargetFailure() from exc
    need(value == check['equals'])


class Probe:
    def __init__(self, config, location):
        self.config = config
        self.location = location
        self.samples = {}
        self.latencies = collections.defaultdict(collections.deque)
        self.lock = threading.Lock()
        self.last_tick = 0

    def browser(self, url, bridge=False):
        # Missing/crashed local browser is observer failure, never site downtime.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            try:
                options = {'headless': True}
                if os.environ.get('STATUS_PROBE_CHROMIUM_PATH'):
                    options['executable_path'] = os.environ['STATUS_PROBE_CHROMIUM_PATH']
                browser = runtime.chromium.launch(**options)
                context = browser.new_context()
            except Exception as exc:
                raise Unknown() from exc
            try:
                page = context.new_page()
                page.set_default_timeout(8000)
                response = page.goto(url, wait_until='domcontentloaded', timeout=15000)
                need(response is not None and response.status == 200)
                if bridge:
                    page.get_by_role('tab', name=re.compile(r'^Deposit to ')).wait_for()
                    field = page.get_by_placeholder('Enter 0x... address')
                    field.fill('0x1111111111111111111111111111111111111111')
                    page.get_by_text('00' + '11' * 20, exact=True).wait_for()
                    chain_id = page.evaluate('window.REACT_APP_CHAIN_ID_L2')
                    need(str(chain_id) == str(self.config['chainId']))
                    page.get_by_role('tab', name=re.compile(r'^Withdraw to ')).click()
                    page.get_by_role('tabpanel').wait_for()
                    for check in self.config['bridgeChecks']:
                        value = page.evaluate("""async url => {
                            const r = await fetch(url, {cache: 'no-store', signal: AbortSignal.timeout(5000)});
                            if (!r.ok) throw new Error('API unavailable');
                            return await r.json();
                        }""", check['url'])
                        for part in check['path']:
                            value = value[part]
                        need(value == check['equals'])
                else:
                    # A reviewed deployment-specific rendered UI element is mandatory.
                    selector = self.config.get('explorerSelector')
                    if not selector:
                        raise Unknown()
                    page.locator(selector).first.wait_for(state='visible')
            except Unknown:
                raise
            except Exception as exc:
                if not browser.is_connected():
                    raise Unknown() from exc
                raise TargetFailure() from exc
            finally:
                browser.close()

    def cycle(self):
        config = self.config
        now = time.time()
        results = {}
        heads = []
        rpc_failed = False
        for url in config['rpcUrls']:
            try:
                started = time.monotonic()
                heads.append(block(url, config['chainId']))
                history = self.latencies[url]
                history.append((now, time.monotonic() - started))
                while history and now - history[0][0] > 300:
                    history.popleft()
                if len(history) >= 10:
                    p95 = sorted(v for _, v in history)[math.ceil(len(history) * .95) - 1]
                    rpc_failed |= p95 > config['maxRpcLatencySeconds']
            except TargetFailure:
                rpc_failed = True
            except Exception:
                results['public-rpc'] = None
        if config['rpcUrls'] and 'public-rpc' not in results:
            results['public-rpc'] = int(rpc_failed)
        if len(heads) == len(config['rpcUrls']) and heads:
            if config.get('sequencingMode') == 'continuous':
                results['sequencing'] = int(now - max(h['timestamp'] for h in heads) > config['maxBlockAgeSeconds'])
            references = [h for h in heads if h['url'].startswith(('http:', 'https:'))]
            if references:
                reference = max(references, key=lambda h: h['height'])
                for key, action in [('block-explorer', lambda: self.explorer(reference)), ('node-sync', lambda: self.node_sync(reference))]:
                    try:
                        action()
                        results[key] = 0
                    except TargetFailure:
                        results[key] = 1
                    except Exception:
                        results[key] = None
        try:
            checks = config.get('bridgeChecks', [])
            if not checks or not config['bridgeUrls']:
                raise Unknown()
            for url in config['bridgeUrls']:
                self.browser(url, bridge=True)
            for check in checks:
                check_json(check)
            results['bridge-portal'] = 0
        except TargetFailure:
            results['bridge-portal'] = 1
        except Exception:
            results['bridge-portal'] = None
        with self.lock:
            self.samples = {key: (value, now) for key, value in results.items() if value in (0, 1)}
            self.last_tick = time.time()

    def explorer(self, reference):
        for url in self.config['explorerUrls']:
            self.browser(url)
        urls = self.config.get('explorerApiUrls', [])
        if not urls:
            raise Unknown()
        for url in urls:
            data = http_json(url.rstrip('/') + '/api/v2/blocks?type=block')
            need(isinstance(data, dict) and isinstance(data.get('items'), list) and len(data['items']) > 0)
            latest = data['items'][0]
            need(isinstance(latest.get('height'), int) and latest['height'] >= 0)
            if latest['height'] > reference['height']:
                raise Unknown()  # The reference may have advanced during browser navigation.
            need(isinstance(latest.get('hash'), str) and re.fullmatch(r'0x[0-9a-fA-F]{64}', latest['hash']) is not None)
            try:
                canonical = rpc(reference['url'], 'eth_getBlockByNumber', [hex(latest['height']), False])
            except TargetFailure as exc:
                raise Unknown() from exc
            need(isinstance(canonical, dict) and canonical.get('hash', '').lower() == latest.get('hash', '').lower())
            timestamp = quantity(canonical.get('timestamp'))
            need(reference['timestamp'] - timestamp <= self.config['maxIndexLagSeconds'])

    def node_sync(self, reference):
        url = self.config.get('nodeRpcUrl')
        checks = self.config.get('nodeDependencyChecks', [])
        if not url or not checks:
            raise Unknown()
        node = block(url, self.config['chainId'])
        # An independent canary node must follow the canonical public chain and
        # reach the configured public bootstrap/DA dependencies from this site.
        if node['height'] > reference['height']:
            raise Unknown()
        try:
            canonical = rpc(reference['url'], 'eth_getBlockByNumber', [hex(node['height']), False])
        except TargetFailure as exc:
            raise Unknown() from exc
        need(isinstance(canonical, dict) and canonical.get('hash', '').lower() == node['hash'])
        need(reference['timestamp'] - node['timestamp'] <= self.config['maxNodeLagSeconds'])
        for check in checks:
            check_json(check)

    def metrics(self):
        with self.lock:
            lines = [f'scroll_status_probe_last_tick_seconds {self.last_tick}']
            for key, (value, timestamp) in self.samples.items():
                labels = ','.join(f'{k}={json.dumps(str(v))}' for k, v in {'environment': self.config['environment'], 'chain_id': self.config['chainId'], 'component_key': key, 'location': self.location}.items())
                lines.extend([f'scroll_status_probe_affected{{{labels}}} {value}', f'scroll_status_probe_timestamp_seconds{{{labels}}} {timestamp}'])
            return '\n'.join(lines) + '\n'


def main():
    with open('/config/probe.json') as file:
        config = json.load(file)
    probe = Probe(config, os.environ['PROBE_LOCATION'])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            code = 200 if self.path == '/metrics' or (self.path == '/healthz' and time.time() - probe.last_tick < 180) else 503
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(probe.metrics().encode() if self.path == '/metrics' else b'observer\n')
    def worker():
        while True:
            started = time.monotonic()
            try:
                probe.cycle()
            except Exception:
                pass  # Last timestamp ages out; never fabricate a failed target.
            time.sleep(max(0.1, 30 - (time.monotonic() - started)))
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', 9111), Handler).serve_forever()


if __name__ == '__main__':
    main()
