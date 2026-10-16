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

test('wrapper rejects an already tracked private output before writing secrets', t => {
  const root = temporary(t)
  assert.equal(spawnSync('git', ['init', '--quiet', root]).status, 0)
  const out = path.join(root, 'output')
  fs.mkdirSync(out)
  fs.writeFileSync(path.join(out, 'attestation-signer.env'), '# NONSECRET_TEST_PLACEHOLDER\n')
  assert.equal(spawnSync('git', ['-C', root, 'add', 'output/attestation-signer.env']).status, 0)
  const result = run(out, 'testnet', 'partner-a', true)
  assert.notEqual(result.status, 0)
  assert.ok(!fs.existsSync(path.join(out, 'transport.key')))
  assert.ok(result.stderr.includes('Private output is already tracked'))
})

test('Docker initialization inside Git permits tracked public templates and ignores private outputs', {skip: process.env.SIGNER_KEYGEN_DOCKER_TEST !== '1'}, t => {
  const root = temporary(t)
  assert.equal(spawnSync('git', ['init', '--quiet', root]).status, 0)
  const out = path.join(root, 'operator')
  fs.mkdirSync(out)
  fs.writeFileSync(path.join(out, 'docker-compose.yml'), '# PUBLIC_TEST_TEMPLATE\n')
  assert.equal(spawnSync('git', ['-C', root, 'add', 'operator/docker-compose.yml']).status, 0)
  const result = run(out, 'testnet', 'partner-a', true)
  assert.equal(result.status, 0, result.stderr)
  noSecretOutput(out, result)
  const before = snapshots(out)
  assert.equal(run(out, 'testnet', 'partner-a', true).status, 0)
  assert.deepEqual(snapshots(out), before)
  for (const name of ['attestation-signer.env', 'transport.key']) {
    assert.equal(spawnSync('git', ['-C', root, 'check-ignore', '-q', 'operator/' + name]).status, 0)
  }
  assert.notEqual(spawnSync('git', ['-C', root, 'check-ignore', '-q', 'operator/']).status, 0)
})

test('Docker-generated keys match the real beta.8 signer on every network', {skip: process.env.SIGNER_KEYGEN_DOCKER_TEST !== '1'}, t => {
  const signer = 'dogeos69/attestation-signer@sha256:0795b7d7a0fcec5a85170147753cae6c2ba7c5217b68289360cd8e249553a8e5'
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


test('explicit reviewed pins are installed once and conflicting reruns preserve both keys', t => {
  const root = temporary(t)
  const pins = ['--release-version', '0.3.0', '--git-commit', 'a'.repeat(40), '--signing-policy-version', '1']
  const invoke = args => spawnSync(process.execPath, [path.join(scripts, 'init-keys.mjs'), '--name', 'partner-a', '--network', 'testnet', '--out', root, ...args], {encoding: 'utf8'})
  assert.notEqual(invoke(pins.slice(0, 2)).status, 0)
  assert.ok(files.every(file => !fs.existsSync(path.join(root, file))))
  const first = invoke(pins)
  assert.equal(first.status, 0, first.stderr)
  noSecretOutput(root, first)
  const before = snapshots(root)
  assert.equal(invoke(pins).status, 0)
  assert.notEqual(invoke(pins.map(value => value === 'a'.repeat(40) ? 'b'.repeat(40) : value)).status, 0)
  assert.deepEqual(snapshots(root), before)
  const env = fs.readFileSync(path.join(root, files[0]), 'utf8')
  assert.ok(env.includes(`ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT=${'a'.repeat(40)}`))
})


test('explicit pins pass through Docker initialization', {skip: process.env.SIGNER_KEYGEN_DOCKER_TEST !== '1'}, t => {
  const root = temporary(t)
  const generated = spawnSync('bash', [path.join(scripts, 'init-keys.sh'), '--name', 'partner-r3', '--network', 'testnet', '--out', root,
    '--release-version', '0.3.0', '--git-commit', 'a0bc76bbdc85e1600c257768c417f2ea14981957', '--signing-policy-version', '1'], {encoding: 'utf8'})
  assert.equal(generated.status, 0, generated.stderr)
  const env = fs.readFileSync(path.join(root, files[0]), 'utf8')
  assert.ok(env.includes('ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT=a0bc76bbdc85e1600c257768c417f2ea14981957'))
})

test('KMS identity validates key metadata, reuses transport and never writes a WIF', t => {
  const root = temporary(t)
  // A disposable key stands in for GetPublicKey; no AWS call or long-lived fixture.
  const fixture = spawnSync(process.execPath, ['--input-type=module', '-e', `
    import {generateKeyPairSync} from 'node:crypto';
    const {publicKey} = generateKeyPairSync('ec', {namedCurve: 'secp256k1'});
    console.log(JSON.stringify({KeyId: 'arn:aws:kms:us-east-1:000000000000:key/test-only',
      KeySpec: 'ECC_SECG_P256K1', KeyUsage: 'SIGN_VERIFY', SigningAlgorithms: ['ECDSA_SHA_256'],
      PublicKey: publicKey.export({type: 'spki', format: 'der'}).toString('base64')}));
  `], {encoding: 'utf8'})
  assert.equal(fixture.status, 0)
  const info = path.join(root, 'kms.json')
  fs.writeFileSync(info, fixture.stdout)
  const invoke = () => spawnSync(process.execPath, [path.join(scripts, 'init-keys.mjs'), '--name', 'kms-signer', '--network', 'testnet', '--out', root, '--kms-info', info, '--kms-region', 'us-east-1'], {encoding: 'utf8'})
  assert.equal(invoke().status, 0)
  const env = fs.readFileSync(path.join(root, 'attestation-signer.env'), 'utf8')
  assert.ok(env.includes('ATTESTATION_SIGNER_BACKEND=aws_kms'))
  assert.ok(!env.includes('ATTESTATION_SIGNER_WIF='))
  const core = JSON.parse(fs.readFileSync(path.join(root, 'identity.json')))
  assert.equal(core.schema, 'dogeos/attestation-signer-descriptor/v1')
  assert.match(core.publicKey, /^0[23][0-9a-f]{64}$/)
  assert.notEqual(core.publicKey, core.transportPubkey)
  const before = snapshots(root)
  assert.equal(invoke().status, 0)
  assert.deepEqual(snapshots(root), before)
  for (const change of [{KeySpec: 'ECC_NIST_P256'}, {KeyUsage: 'ENCRYPT_DECRYPT'}, {KeyId: 'arn:aws:kms:us-west-2:000000000000:key/test-only'}]) {
    fs.writeFileSync(info, JSON.stringify({...JSON.parse(fixture.stdout), ...change}))
    assert.notEqual(invoke().status, 0)
    assert.deepEqual(snapshots(root), before)
  }
})
