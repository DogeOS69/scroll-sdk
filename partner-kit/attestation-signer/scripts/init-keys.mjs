// Run through init-keys.sh. No npm packages; secp256k1 is implemented by the
// container's OpenSSL-backed node:crypto, not by this script.
import {createECDH, createHash, timingSafeEqual} from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import {parseArgs} from 'node:util'

const alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
const versions = {mainnet: 0x9e, testnet: 0xf1, regtest: 0xef}
const files = ['attestation-signer.env', 'transport.key', 'public-identity.json']
const sha256 = value => createHash('sha256').update(value).digest()
const checksum = value => sha256(sha256(value)).subarray(0, 4)
const requireValid = condition => { if (!condition) throw new Error('Invalid identity material') }

function encodeWif(secret, network) {
  const payload = Buffer.concat([Buffer.from([versions[network]]), secret, Buffer.from([1])])
  let number = BigInt(`0x${Buffer.concat([payload, checksum(payload)]).toString('hex')}`)
  let result = ''
  while (number > 0n) {
    result = alphabet[Number(number % 58n)] + result
    number /= 58n
  }
  return result // These network prefixes are nonzero; no leading-zero padding.
}

function decodeWif(wif, network) {
  requireValid(typeof wif === 'string' && wif.length === 52)
  let number = 0n
  for (const char of wif) {
    const digit = alphabet.indexOf(char)
    requireValid(digit >= 0)
    number = number * 58n + BigInt(digit)
  }
  let hex = number.toString(16)
  if (hex.length % 2) hex = `0${hex}`
  const bytes = Buffer.from(hex, 'hex')
  requireValid(bytes.length === 38 && bytes[0] === versions[network] && bytes[33] === 1)
  requireValid(timingSafeEqual(bytes.subarray(34), checksum(bytes.subarray(0, 34))))
  return bytes.subarray(1, 33)
}

function publicKey(secret) {
  const key = createECDH('secp256k1')
  key.setPrivateKey(secret)
  return key.getPublicKey('hex', 'compressed')
}

function newKey() {
  const key = createECDH('secp256k1')
  key.generateKeys()
  return Buffer.from(key.getPrivateKey('hex').padStart(64, '0'), 'hex')
}

function readRegularFile(filename, secret = false) {
  const fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW)
  try {
    const stat = fs.fstatSync(fd)
    requireValid(stat.isFile() && stat.size < 65536)
    if (secret) requireValid((stat.mode & 0o777) === 0o600 && stat.nlink === 1)
    return fs.readFileSync(fd, 'utf8')
  } finally { fs.closeSync(fd) }
}

function readIdentity(out, name, network, pins) {
  const env = new Map()
  for (const line of readRegularFile(path.join(out, files[0]), true).split('\n')) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue
    const match = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/)
    requireValid(match && !env.has(match[1]))
    env.set(match[1], match[2])
  }
  if (pins) for (const [field, value] of Object.entries(pins)) requireValid(env.get(field) === value)
  requireValid(env.get('ATTESTATION_SIGNER_BACKEND') === 'local')
  requireValid(env.get('ATTESTATION_SIGNER_NETWORK') === network)
  requireValid(env.get('ATTESTATION_SIGNER_TSO_DELIVERY') === 'pull')
  requireValid(env.get('ATTESTATION_SIGNER_TSO_TRANSPORT_KEY_FILE') === '/etc/dogeos-partner/transport.key')
  const transport = readRegularFile(path.join(out, files[1]), true)
  requireValid(/^[0-9a-f]{64}\n$/.test(transport))
  const attestationPubkey = publicKey(decodeWif(env.get('ATTESTATION_SIGNER_WIF'), network))
  const transportPubkey = publicKey(Buffer.from(transport.trim(), 'hex'))
  requireValid(attestationPubkey !== transportPubkey)
  const identity = JSON.parse(readRegularFile(path.join(out, files[2])))
  requireValid(identity.name === name && identity.network === network
    && identity.attestationPubkey === attestationPubkey && identity.transportPubkey === transportPubkey)
  // Return only the defined public fields, never arbitrary file contents.
  return {name, network, attestationPubkey, transportPubkey}
}

function writePrivate(filename, contents) {
  const fd = fs.openSync(filename, 'wx', 0o600)
  try { fs.writeFileSync(fd, contents); fs.fsyncSync(fd) } finally { fs.closeSync(fd) }
}

function initialize(out, name, network, pins) {
  const stat = fs.lstatSync(out)
  requireValid(stat.isDirectory() && !stat.isSymbolicLink())
  const lock = path.join(out, '.key-init.lock')
  fs.mkdirSync(lock, {mode: 0o700})
  try {
    const entries = fs.readdirSync(out)
    const existing = files.filter(file => entries.includes(file))
    if (existing.length) {
      requireValid(existing.length === files.length)
      return readIdentity(out, name, network, pins)
    }
    // Never initialize over an older deployment or interrupted write. A fresh
    // directory (or the kit's public Compose templates) is the only valid target.
    requireValid(!entries.some(file => file.endsWith('.key') || file.endsWith('.new')
      || ['identity.json', 'descriptor.json', 'signer-data'].includes(file)))
    const attestation = newKey()
    let transport = newKey()
    while (transport.equals(attestation)) transport = newKey()
    const identity = {name, network, attestationPubkey: publicKey(attestation), transportPubkey: publicKey(transport)}
    const env = [
      '# PRIVATE: local attestation key. Keep with transport.key; never upload either.',
      'ATTESTATION_SIGNER_BACKEND=local',
      `ATTESTATION_SIGNER_NETWORK=${network}`,
      `ATTESTATION_SIGNER_WIF=${encodeWif(attestation, network)}`,
      'ATTESTATION_SIGNER_TSO_DELIVERY=pull',
      'ATTESTATION_SIGNER_TSO_TRANSPORT_KEY_FILE=/etc/dogeos-partner/transport.key',
      '# Approved signer binary. Review these pins together with the runtime image.',
      ...Object.entries(pins ?? {
        ATTESTATION_SIGNER_ALLOWED_RELEASE_VERSION: '0.3.0',
        ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT: '56007d3c413ad07f33d0e08b272004089c911f78',
        ATTESTATION_SIGNER_ALLOWED_SIGNING_POLICY_VERSION: '1',
      }).map(([field, value]) => `${field}=${value}`),
      '',
    ].join('\n')
    // Exclusive, fsynced writes. A partial write blocks retries instead of
    // silently generating a replacement for an identity that may be registered.
    writePrivate(path.join(out, files[0]), env)
    writePrivate(path.join(out, files[1]), `${transport.toString('hex')}\n`)
    writePrivate(path.join(out, files[2]), `${JSON.stringify(identity, null, 2)}\n`)
    return readIdentity(out, name, network, pins)
  } finally { fs.rmdirSync(lock) }
}

try {
  const {values} = parseArgs({options: {name: {type: 'string'}, network: {type: 'string'}, out: {type: 'string'}, 'release-version': {type: 'string'}, 'git-commit': {type: 'string'}, 'signing-policy-version': {type: 'string'}}})
  requireValid(typeof values.name === 'string' && /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(values.name) && values.name.length <= 63)
  requireValid(Object.hasOwn(versions, values.network) && typeof values.out === 'string')
  const suppliedPins = ['release-version', 'git-commit', 'signing-policy-version'].filter(key => values[key] !== undefined)
  requireValid(suppliedPins.length === 0 || suppliedPins.length === 3)
  let pins
  if (suppliedPins.length) {
    requireValid(/^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/.test(values['release-version']))
    requireValid(/^[0-9a-f]{40}$/.test(values['git-commit']))
    requireValid(/^[1-9][0-9]*$/.test(values['signing-policy-version']) && Number.isSafeInteger(Number(values['signing-policy-version'])))
    pins = {ATTESTATION_SIGNER_ALLOWED_RELEASE_VERSION: values['release-version'], ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT: values['git-commit'], ATTESTATION_SIGNER_ALLOWED_SIGNING_POLICY_VERSION: values['signing-policy-version']}
  }
  const identity = initialize(path.resolve(values.out), values.name, values.network, pins)
  console.log('Public identity — copy the name and paired public keys into Governance:')
  console.log(JSON.stringify(identity, null, 2))
  console.log('Private files: attestation-signer.env and transport.key. Existing identities are reused without rewriting.')
} catch {
  // Never echo crypto/JSON/parser exceptions: they may include private input.
  console.error('Key initialization failed. Check arguments, directory permissions and all three identity files. Existing files must be complete, match the requested name/network and any explicit binary pins, and have private-key permissions 0600. Restore incomplete or mismatched files; keys are never overwritten. If .key-init.lock remains after an interrupted process, confirm no initializer is running before removing that empty lock directory.')
  process.exitCode = 1
}
