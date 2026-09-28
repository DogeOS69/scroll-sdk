// Supplemental JSON-RPC checks in the existing Alloy Pod. No write RPC calls.
import {readFileSync, realpathSync} from 'node:fs';
import {createServer} from 'node:http';
import {pathToFileURL} from 'node:url';

export function rpc(url, method, timeout = 5000) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    let done = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      socket.close();
      if (error) reject(new Error('rpc_check_failed')); else resolve(value);
    };
    const timer = setTimeout(() => finish(true), timeout);
    socket.addEventListener('open', () => socket.send(JSON.stringify({jsonrpc: '2.0', id: 1, method, params: []})));
    socket.addEventListener('error', () => finish(true));
    socket.addEventListener('close', () => { if (!done) finish(true); });
    socket.addEventListener('message', ({data}) => {
      try {
        if (typeof data !== 'string' || Buffer.byteLength(data) > 65536) throw new Error();
        const value = JSON.parse(data);
        if (value.jsonrpc !== '2.0' || value.id !== 1 || 'error' in value ||
            typeof value.result !== 'string' || !/^0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)$/.test(value.result)) throw new Error();
        finish(false, BigInt(value.result));
      } catch { finish(true); }
    });
  });
}

export async function observe(target, query = rpc) {
  const start = performance.now();
  let success = 0;
  try {
    if (await query(target.address, 'eth_chainId') !== BigInt(target.chain_id)) throw new Error();
    await query(target.address, 'eth_blockNumber');
    success = 1;
  } catch { /* Failed public RPC/TLS/JSON checks are affected, not fabricated data. */ }
  return {success, duration: (performance.now() - start) / 1000};
}

export function metrics(target, result, observed) {
  const labels = ['environment', 'chain_id', 'component_key', 'check_id', 'status_probe_config']
    .map(key => `${key}=${JSON.stringify(String(target[key]))}`).join(',');
  return [['scroll_status_ws_success', result.success], ['scroll_status_ws_duration_seconds', result.duration],
    ['scroll_status_ws_timestamp_seconds', observed]].map(([key, value]) => `${key}{${labels}} ${value}\n`).join('');
}

export function main(configPath) {
  let body = '', tick = 0;
  const config = JSON.parse(readFileSync(configPath, 'utf8'));
  if (!Array.isArray(config.websocketTargets) || config.websocketTargets.length > 16) throw new Error('Invalid WebSocket target count');
  const loop = async () => {
    const observed = Date.now() / 1000;
    body = (await Promise.all(config.websocketTargets.map(async target => metrics(target, await observe(target), observed)))).join('');
    tick = performance.now();
    setTimeout(loop, 30000).unref();
  };
  createServer((req, res) => {
    if (req.url === '/metrics') { res.writeHead(200, {'Content-Type': 'text/plain; version=0.0.4'}); res.end(body); }
    else { res.writeHead(req.url === '/healthz' && tick > 0 && performance.now() - tick < 120000 ? 200 : 503); res.end(); }
  }).listen(9113, '0.0.0.0');
  void loop();
}
// Kubernetes projected ConfigMaps resolve through timestamped symlinks.
if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) main(process.argv[2]);
