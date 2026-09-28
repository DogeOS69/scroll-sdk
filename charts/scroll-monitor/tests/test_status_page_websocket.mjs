import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {observe, rpc} from '../scripts/status-page-websocket.mjs';
// Reuse the CLI's installed test dependency; never store captured service metrics.
const require = createRequire(process.env.STATUS_WS_TEST_PACKAGE || new URL('../package.json', import.meta.url));
const {WebSocketServer} = require('ws');
async function server(handler) {
  const ws = new WebSocketServer({port: 0, host: '127.0.0.1'});
  await new Promise(resolve => ws.once('listening', resolve));
  ws.on('connection', client => client.on('message', raw => handler(client, JSON.parse(raw))));
  return {url: `ws://127.0.0.1:${ws.address().port}`, close: () => new Promise(resolve => { for (const c of ws.clients) c.terminate(); ws.close(resolve); })};
}
test('checks chain identity and a real RPC exchange, not only the upgrade handshake', async () => {
  const s = await server((c, q) => c.send(JSON.stringify({jsonrpc: '2.0', id: q.id, result: q.method === 'eth_chainId' ? '0x123' : '0x42'})));
  try {
    assert.equal((await observe({address:s.url, chain_id:'291'})).success,1);
    assert.equal((await observe({address:s.url, chain_id:'292'})).success,0);
  } finally { await s.close(); }
});
test('rejects errors, wrong ids, malformed quantities and silent servers', async () => {
  for (const payload of [{jsonrpc:'2.0',id:1,error:{code:-1}}, {jsonrpc:'2.0',id:2,result:'0x1'}, {jsonrpc:'2.0',id:1,result:'latest'}, null]) {
    const s=await server(c => { if (payload) c.send(JSON.stringify(payload)); });
    try { await assert.rejects(rpc(s.url,'eth_chainId',100)); } finally { await s.close(); }
  }
});

test('starts when its entrypoint is a projected ConfigMap symlink', async () => {
  const {mkdtempSync, symlinkSync, writeFileSync, rmSync} = await import('node:fs');
  const {tmpdir} = await import('node:os');
  const {fileURLToPath} = await import('node:url');
  const {spawn} = await import('node:child_process');
  const dir = mkdtempSync(`${tmpdir()}/status-ws-start-`);
  symlinkSync(fileURLToPath(new URL('../scripts/status-page-websocket.mjs', import.meta.url)), `${dir}/probe.mjs`);
  writeFileSync(`${dir}/config.json`, JSON.stringify({websocketTargets:[]}));
  const child = spawn(process.execPath, [`${dir}/probe.mjs`, `${dir}/config.json`], {stdio:'ignore'});
  try {
    let ready = false;
    for (let i=0;i<30;i++) {
      await new Promise(resolve=>setTimeout(resolve,50));
      try { if ((await fetch('http://127.0.0.1:9113/healthz')).ok) { ready=true; break; } } catch {}
    }
    assert.equal(ready,true);
  } finally { child.kill(); await new Promise(resolve=>child.once('exit',resolve)); rmSync(dir,{recursive:true,force:true}); }
});
