// Disposable keys only. Assertions deliberately never dump private buffers.
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
import {createHash} from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {test} from 'node:test'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const scripts = path.join(repo, 'partner-kit/attestation-signer/scripts')
const files = ['attestation-signer.env', 'transport.key', 'public-identity.json']
const digest = value => createHash('sha256').update(value).digest('hex')
function temporary(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'signer-keygen-test-'))
  t.after(() => fs.rmSync(root, {force: true, recursive: true}))
  return root
}
function run(root, network = 'testnet', name = 'partner-a', docker = false) {
  return spawnSync(docker ? 'bash' : process.execPath, [path.join(scripts, docker ? 'init-keys.sh' : 'init-keys.mjs'),
    '--name', name, '--network', network, '--out', root], {encoding: 'utf8'})
}
function snapshots(root) { return files.map(file => digest(fs.readFileSync(path.join(root, file)))) }
function noSecretOutput(root, result) {
  const env = fs.readFileSync(path.join(root, files[0]), 'utf8')
  const wif = env.match(/^ATTESTATION_SIGNER_WIF=(.+)$/m)[1]
  const secret = fs.readFileSync(path.join(root, files[1]), 'utf8').trim()
  assert.ok(!`${result.stdout}${result.stderr}`.includes(wif), 'WIF leaked to output')
  assert.ok(!`${result.stdout}${result.stderr}`.includes(secret), 'Transport secret leaked to output')
}

for (const network of ['mainnet', 'testnet', 'regtest']) {
  test(`creates private files and preserves the ${network} identity on rerun`, t => {
    const root = temporary(t)
    const first = run(root, network)
    assert.equal(first.status, 0, first.stderr)
    noSecretOutput(root, first)
    const identity = JSON.parse(fs.readFileSync(path.join(root, files[2])))
    assert.equal(identity.network, network)
    assert.equal(identity.name, 'partner-a')
    for (const key of ['attestationPubkey', 'transportPubkey']) {
      assert.match(identity[key], /^0[23][0-9a-f]{64}$/)
      assert.ok(first.stdout.includes(identity[key]))
    }
    assert.notEqual(identity.attestationPubkey, identity.transportPubkey)
    for (const file of files) assert.equal(fs.statSync(path.join(root, file)).mode & 0o777, 0o600)
    const original = snapshots(root)
    const second = run(root, network)
    assert.equal(second.status, 0, second.stderr)
    noSecretOutput(root, second)
    assert.deepEqual(snapshots(root), original)
    for (const [selectedNetwork, name] of [[network, 'different-name'], [network === 'mainnet' ? 'testnet' : 'mainnet', 'partner-a']]) {
      assert.notEqual(run(root, selectedNetwork, name).status, 0)
      assert.deepEqual(snapshots(root), original)
    }
  })
}

test('missing key or public record never causes regeneration', t => {
  for (const missing of files) {
    const root = temporary(t)
    assert.equal(run(root).status, 0)
    const remaining = files.filter(file => file !== missing)
    const original = remaining.map(file => digest(fs.readFileSync(path.join(root, file))))
    fs.unlinkSync(path.join(root, missing))
    assert.notEqual(run(root).status, 0)
    assert.ok(!fs.existsSync(path.join(root, missing)))
    assert.deepEqual(remaining.map(file => digest(fs.readFileSync(path.join(root, file)))), original)
  }
})

test('corruption, wrong public keys and broad secret permissions fail without rewriting', t => {
  const root = temporary(t)
  assert.equal(run(root).status, 0)
  for (const file of files) {
    const filename = path.join(root, file)
    const original = fs.readFileSync(filename)
    fs.writeFileSync(filename, 'NONFUNCTIONAL_CORRUPTION_PLACEHOLDER')
    const before = snapshots(root)
    assert.notEqual(run(root).status, 0)
    assert.deepEqual(snapshots(root), before)
    fs.writeFileSync(filename, original)
  }
  const publicFile = path.join(root, files[2])
  const originalPublic = fs.readFileSync(publicFile)
  const identity = JSON.parse(fs.readFileSync(publicFile))
  identity.transportPubkey = identity.attestationPubkey
  fs.writeFileSync(publicFile, JSON.stringify(identity))
  const before = snapshots(root)
  const result = run(root)
  assert.notEqual(result.status, 0)
  noSecretOutput(root, result)
  assert.deepEqual(snapshots(root), before)
  fs.writeFileSync(publicFile, originalPublic)
  const valid = snapshots(root)
  fs.chmodSync(path.join(root, files[0]), 0o644)
  assert.notEqual(run(root).status, 0)
  assert.deepEqual(snapshots(root), valid)
})

test('valid-length secrets with invalid WIF checksum or zero scalar fail privately', t => {
  const root = temporary(t)
  assert.equal(run(root).status, 0)
  const envFile = path.join(root, files[0])
  const original = fs.readFileSync(envFile, 'utf8')
  const changed = original.replace(/^(ATTESTATION_SIGNER_WIF=)(.+)$/m, (_, prefix, wif) =>
    `${prefix}${wif.slice(0, -1)}${wif.endsWith('1') ? '2' : '1'}`)
  fs.writeFileSync(envFile, changed)
  const result = run(root)
  assert.notEqual(result.status, 0)
  noSecretOutput(root, result)
  fs.writeFileSync(envFile, original)
  fs.writeFileSync(path.join(root, files[1]), `${'0'.repeat(64)}\n`)
  assert.notEqual(run(root).status, 0)
})

test('symlinks and concurrent initializers are refused', t => {
  const root = temporary(t)
  fs.mkdirSync(path.join(root, '.key-init.lock'))
  assert.notEqual(run(root).status, 0)
  assert.ok(files.every(file => !fs.existsSync(path.join(root, file))))
  fs.rmdirSync(path.join(root, '.key-init.lock'))
  assert.equal(run(root).status, 0)
  const original = snapshots(root)
  fs.renameSync(path.join(root, files[1]), path.join(root, 'saved-key'))
  fs.symlinkSync('saved-key', path.join(root, files[1]))
  assert.notEqual(run(root).status, 0)
  assert.deepEqual(snapshots(root), original)
})

test('wrapper rejects Git checkouts before writing any secret', t => {
  const root = temporary(t)
  assert.equal(spawnSync('git', ['init', '--quiet', root]).status, 0)
  const out = path.join(root, 'output')
  const result = run(out, 'testnet', 'partner-a', true)
  assert.notEqual(result.status, 0)
  assert.ok(files.every(file => !fs.existsSync(path.join(out, file))))
})

test('Docker wrapper permits ignored operator directories but rejects tracked output', {skip: process.env.SIGNER_KEYGEN_DOCKER_TEST !== '1'}, t => {
  const root = temporary(t)
  assert.equal(spawnSync('git', ['init', '--quiet', root]).status, 0)
  fs.appendFileSync(path.join(root, '.git/info/exclude'), '\n/private/\n')
  const out = path.join(root, 'private')
  const result = run(out, 'testnet', 'partner-a', true)
  assert.equal(result.status, 0, result.stderr)
  noSecretOutput(out, result)
  const before = snapshots(out)
  // Track only a nonsecret placeholder to verify that ignore rules cannot
  // authorize writing into an already tracked output directory.
  fs.writeFileSync(path.join(out, 'tracked.txt'), 'PUBLIC_TEST_PLACEHOLDER\n')
  fs.appendFileSync(path.join(root, '.git/info/exclude'), '!/private/\n/private/*\n!/private/tracked.txt\n')
  assert.equal(spawnSync('git', ['-C', root, 'add', 'private/tracked.txt']).status, 0)
  fs.appendFileSync(path.join(root, '.git/info/exclude'), '/private/\n')
  assert.notEqual(run(out, 'testnet', 'partner-a', true).status, 0)
  assert.deepEqual(snapshots(out), before)
})

test('Docker-generated keys match the real beta.6 signer on every network', {skip: process.env.SIGNER_KEYGEN_DOCKER_TEST !== '1'}, t => {
  const signer = 'dogeos69/attestation-signer@sha256:f5f02291e0a4c9a3c688fba431b52ba9c26c9418073c92671f03dad7d81f79fc'
  for (const network of ['mainnet', 'testnet', 'regtest']) {
    const root = temporary(t)
    const generated = run(root, network, 'partner-a', true)
    assert.equal(generated.status, 0, generated.stderr)
    noSecretOutput(root, generated)
    const identity = JSON.parse(fs.readFileSync(path.join(root, files[2])))
    fs.writeFileSync(path.join(root, 'attestation-signer.toml'), '# Identity export needs no runtime policy.\n')
    const result = spawnSync('docker', ['run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
      '--security-opt', 'no-new-privileges', '--user', `${process.getuid()}:${process.getgid()}`,
      '--env-file', path.join(root, files[0]), '--mount', `type=bind,src=${root},dst=/etc/dogeos-partner,readonly`,
      signer, '-c', '/etc/dogeos-partner/attestation-signer.toml', '--print-identity'], {encoding: 'utf8'})
    noSecretOutput(root, result)
    // Runtime errors may include credentials; do not include raw stderr in assertions.
    assert.equal(result.status, 0, `Native signer identity export failed for ${network}`)
    const exported = JSON.parse(result.stdout)
    assert.equal(exported.network, network)
    assert.equal(exported.publicKey, identity.attestationPubkey)
    assert.equal(exported.transportPubkey, identity.transportPubkey)
    const before = snapshots(root)
    assert.equal(run(root, network, 'partner-a', true).status, 0)
    assert.deepEqual(snapshots(root), before)
  }
})
