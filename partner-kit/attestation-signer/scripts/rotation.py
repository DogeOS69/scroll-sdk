#!/usr/bin/env python3
"""Independent, offline verification and local approval of RotateKey proposals."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib
import urllib.request


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=no_duplicates)


def hex_bytes(value, length=None, prefix=False):
    require(isinstance(value, str), 'Expected a hexadecimal string')
    if prefix:
        require(value.startswith('0x'), 'Hash requires 0x prefix')
        value = value[2:]
    require(bool(re.fullmatch('[0-9a-f]+', value)) and len(value) % 2 == 0,
            'Expected lowercase hexadecimal bytes')
    result = bytes.fromhex(value)
    require(length is None or len(result) == length, 'Wrong hexadecimal byte length')
    return result


def public_key(value):
    raw = hex_bytes(value, 33)
    require(raw[0] in (2, 3), 'Expected compressed secp256k1 public key')
    prime = 2**256 - 2**32 - 977
    x = int.from_bytes(raw[1:], 'big')
    y_squared = (x**3 + 7) % prime
    require(x < prime and pow(pow(y_squared, (prime + 1) // 4, prime), 2, prime) == y_squared,
            'Public key is not on secp256k1')
    return value


def parse_script(script_hex):
    raw = hex_bytes(script_hex)
    require(len(raw) <= 520, 'Redeem script exceeds consensus size limit')
    chunks = []
    offset = 0
    while offset < len(raw):
        opcode = raw[offset]
        offset += 1
        if 1 <= opcode <= 75:
            require(offset + opcode <= len(raw), 'Truncated script push')
            chunks.append(raw[offset:offset + opcode])
            offset += opcode
        else:
            require(opcode not in (76, 77, 78), 'Only canonical direct pushes are supported')
            chunks.append(opcode)
    position = 0

    def take():
        nonlocal position
        require(position < len(chunks), 'Truncated bridge script')
        item = chunks[position]
        position += 1
        return item

    def op(expected):
        require(take() == expected, 'Unexpected bridge script opcode')

    def number():
        value = take()
        if value == 0:
            return 0
        if isinstance(value, int):
            require(81 <= value <= 96, 'Invalid script number opcode')
            return value - 80
        require(0 < len(value) <= 5 and not value[-1] & 128, 'Invalid positive script number')
        require(value[-1] != 0 or (len(value) > 1 and value[-2] & 128), 'Nonminimal script number')
        result = int.from_bytes(value, 'little')
        require(result > 16, 'Nonminimal small integer push')
        return result

    def pub():
        item = take()
        require(isinstance(item, bytes), 'Missing public key push')
        return public_key(item.hex())

    def multisig():
        threshold = number()
        keys = []
        while position < len(chunks) and isinstance(chunks[position], bytes) and len(chunks[position]) == 33:
            keys.append(pub())
        count = number()
        require(1 <= threshold <= count <= 16 and count == len(keys), 'Invalid multisig quorum')
        require(len(set(keys)) == len(keys), 'Duplicate multisig public keys')
        op(0xaf)  # CHECKMULTISIGVERIFY
        return {'threshold': threshold, 'pubkeys': keys}

    namespace = take()
    require(isinstance(namespace, bytes) and len(namespace) == 20, 'Invalid bridge namespace')
    op(0x75)
    op(0x63)
    attestation = multisig()
    tee = pub()
    op(0xad)
    op(0x67)
    timelock = number()
    require(0 < timelock < 500_000_000, 'Recovery timelock must use block heights')
    op(0xb1)
    op(0x75)
    recovery = multisig()
    op(0x68)
    op(0x51)
    require(position == len(chunks), 'Trailing bridge script instructions')
    require(tee not in attestation['pubkeys'] + recovery['pubkeys'], 'TEE key overlaps multisig')
    return {'namespace': namespace.hex(), 'attestation': attestation, 'tee': tee,
            'timelock': timelock, 'recovery': recovery}


def hash160(script):
    return '0x' + hashlib.new('ripemd160', hashlib.sha256(hex_bytes(script)).digest()).hexdigest()


def address(key_hash, network):
    raw = bytes([22 if network == 'mainnet' else 196]) + hex_bytes(key_hash, 20, True)
    checksum = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[:4]
    data = raw + checksum
    value = int.from_bytes(data, 'big')
    encoded = ''
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    while value:
        value, remainder = divmod(value, 58)
        encoded = alphabet[remainder] + encoded
    return '1' * (len(data) - len(data.lstrip(b'\0'))) + encoded


def verify(envelope, expected, current_hash):
    proposal = envelope['proposal']
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None, 'Invalid expected proposal digest')
    require(envelope['sha256'] == expected == digest(proposal), 'Proposal digest mismatch')
    require(proposal['schema'] == 'dogeos/attestation-rotation/v1', 'Unsupported proposal schema')
    require(proposal['network'] in ('mainnet', 'testnet', 'regtest'), 'Unknown network')
    hex_bytes(proposal['deployment']['protocolContextSha256'], 32)
    old, new = proposal['current'], proposal['target']
    for item in (old, new):
        require(hash160(item['redeemScriptHex']) == item['keyHash'], 'Script hash mismatch')
    hex_bytes(current_hash, 20, True)
    require(old['keyHash'] == current_hash, 'Current bridge hash does not match independently supplied value')
    before, after = parse_script(old['redeemScriptHex']), parse_script(new['redeemScriptHex'])
    require(before['namespace'] == after['namespace'] == proposal['deployment']['namespace'], 'Namespace changed or mismatched')
    require(before['tee'] == after['tee'], 'TEE public key changed')
    require(before['recovery'] == after['recovery'], 'Recovery public keys, order or threshold changed')
    require(not set(before['attestation']['pubkeys']) & set(after['attestation']['pubkeys']),
            'New attestation set must be fully disjoint from old set')
    require(new['threshold'] == after['attestation']['threshold'], 'Target threshold mismatch')
    members = new['signers']
    names = [member['name'] for member in members]
    require(all(re.fullmatch('[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?', name) for name in names)
            and len(set(names)) == len(names), 'Invalid or duplicate member names')
    keys = [public_key(member['attestationPubkey']) for member in members]
    transports = [public_key(member['transportPubkey']) for member in members]
    require(len(set(keys)) == len(keys) and set(keys) == set(after['attestation']['pubkeys']), 'Target member keys mismatch')
    require(len(set(transports)) == len(transports), 'Duplicate transport public keys')
    require(address(new['keyHash'], proposal['network']) == new['address'], 'Target bridge address mismatch')
    timing = proposal['timelock']
    require(timing['oldHeight'] == before['timelock'] and timing['newHeight'] == after['timelock'], 'Timelock summary mismatch')
    require(timing['policy'] in ('preserve', 'refresh'), 'Unknown timelock policy')
    if timing['policy'] == 'preserve':
        require(before['timelock'] == after['timelock'], 'Preserve policy changes timelock')
    require(type(timing['anchorHeight']) is int and timing['anchorHeight'] >= 0
            and after['timelock'] >= timing['anchorHeight'] + 259200, 'Insufficient recovery delay at proposal anchor')
    require(type(proposal['graceWfTxs']) is int and 1 <= proposal['graceWfTxs'] <= 2**32 - 1, 'Invalid overlap duration')
    require(type(proposal['observedWfTxNumber']) is int and 0 <= proposal['observedWfTxNumber'] <= 2**53 - 1, 'Invalid observed WF number')
    return proposal, before, after


def patch_policy(text, target):
    """Preserve all unrelated TOML text and verify the semantic delta with tomllib."""
    original = tomllib.loads(text)
    expected = copy.deepcopy(original)
    rotation = expected.setdefault('rotation_policy', {})
    existing = rotation.setdefault('allowed_next_bridge_script_hashes', [])
    require(isinstance(existing, list) and all(isinstance(item, str) for item in existing), 'Invalid bridge allowlist')
    if target in existing:
        return text
    existing.append(target)
    assignment = 'allowed_next_bridge_script_hashes = ' + json.dumps(existing) + '\n'
    section = re.search(r'(?m)^\s*\[rotation_policy\]\s*(?:#[^\n]*)?$', text)
    if section:
        end_match = re.search(r'(?m)^\s*\[', text[section.end():])
        end = section.end() + end_match.start() if end_match else len(text)
        body = text[section.end():end]
        field = re.search(r'(?m)^[ \t]*allowed_next_bridge_script_hashes[ \t]*=', body)
        if field:
            # Find the end of the existing array by parsing prefixes. This handles
            # multiline arrays and comments without rewriting other settings.
            start = field.start()
            finish = None
            for boundary in [match.end() for match in re.finditer('\n', body[field.end():])]:
                candidate_end = field.end() + boundary
                try:
                    candidate = tomllib.loads(body[start:candidate_end])
                except tomllib.TOMLDecodeError:
                    continue
                if set(candidate) == {'allowed_next_bridge_script_hashes'}:
                    finish = candidate_end
                    break
            if finish is None:
                candidate = tomllib.loads(body[start:])
                require(set(candidate) == {'allowed_next_bridge_script_hashes'}, 'Unsupported allowlist formatting')
                finish = len(body)
            body = body[:start] + assignment + body[finish:]
        else:
            body = '\n' + assignment + body
        updated = text[:section.end()] + body + text[end:]
    else:
        require('rotation_policy' not in original, 'Use a plain [rotation_policy] table before approving')
        updated = text.rstrip() + '\n\n[rotation_policy]\n' + assignment
    require(tomllib.loads(updated) == expected, 'Refusing an ambiguous TOML edit')
    return updated


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def policy_status(port, signer, network, require_rotation, require_normal=False):
    # Docker joins only the explicitly selected signer's network namespace.
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/policy', timeout=3) as response:
        report = json.load(response)
    require(report.get('public_key', '').removeprefix('0x').lower() == signer, 'Running signer public key mismatch')
    require(report.get('network') == network, 'Running signer network mismatch')
    require(report.get('policy_mode') == 'enforce', 'Signer is not in enforce mode')
    if require_normal:
        for capability in ('advance_l1', 'advance_l2'):
            require(any(row.get('capability') == capability and row.get('production_serving') is True
                        for row in report.get('v2_capabilities', [])), 'Required AdvanceL1/AdvanceL2 capability is not serving')
    if require_rotation:
        require(any(row.get('capability') == 'rotate_key' and row.get('production_serving') is True
                    for row in report.get('v2_capabilities', [])), 'RotateKey capability is not serving')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inspect', 'approve', 'check', 'receipt', 'container-check', 'ready'])
    parser.add_argument('--proposal', required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--current-key-hash', required=True)
    parser.add_argument('--config')
    parser.add_argument('--host-config')
    parser.add_argument('--signer-public-key')
    parser.add_argument('--port', type=int, default=4040)
    parser.add_argument('--transport-public-key')
    parser.add_argument('--acknowledge-tso-connected', action='store_true')
    args = parser.parse_args()
    proposal, before, after = verify(read_json(args.proposal), args.expected_sha256, args.current_key_hash)
    if args.action == 'inspect':
        print(json.dumps({'proposalSha256': args.expected_sha256, 'name': proposal['name'],
                          'network': proposal['network'], 'protocolContextSha256': proposal['deployment']['protocolContextSha256'],
                          'currentKeyHash': proposal['current']['keyHash'], 'targetKeyHash': proposal['target']['keyHash'],
                          'targetAddress': proposal['target']['address'], 'oldScript': before, 'newScript': after,
                          'targetSigners': proposal['target']['signers'], 'graceWfTxs': proposal['graceWfTxs']}, indent=2))
        print('Offline inspection only. Confirm deployment identity and current bridge hash independently; live-chain admission is checked again by WP.')
        return
    if args.action == 'ready' or (args.action == 'container-check' and args.transport_public_key):
        require(any(member['attestationPubkey'] == args.signer_public_key
                    and member['transportPubkey'] == args.transport_public_key
                    for member in proposal['target']['signers']), 'New signer public key pair does not match proposal')
        require(args.acknowledge_tso_connected, 'Explicit acknowledgement of observed authenticated TSO connectivity is required')
    else:
        require(args.signer_public_key in before['attestation']['pubkeys'], 'Approving identity is not in the current attestation set')
    if args.action == 'container-check':
        metadata = json.load(sys.stdin)
        require(not metadata['override'], 'Container environment overrides file allowlist')
        command = metadata['command'] or []
        require(not any(arg.startswith('--allowed-next-bridge-script-hashes') for arg in command), 'Container command overrides file allowlist')
        paths = [command[i + 1] for i, arg in enumerate(command[:-1]) if arg in ('-c', '--config')]
        paths += [arg.split('=', 1)[1] for arg in command if arg.startswith('--config=')]
        require(len(paths) == 1, 'Container must explicitly select its TOML configuration')
        matches = [mount for mount in metadata['mounts'] if mount.get('Type') == 'bind'
                   and mount.get('Source') == args.host_config and mount.get('Destination') == paths[0]]
        require(len(matches) == 1, 'Config must be the selected container single-file bind mount')
        return
    if args.action in ('check', 'receipt', 'ready'):
        last_error = None
        for attempt in range(15 if args.action == 'receipt' else 1):
            try:
                policy_status(args.port, args.signer_public_key, proposal['network'], args.action == 'receipt', args.action == 'ready')
                last_error = None
                break
            except (ValueError, OSError) as error:
                last_error = error
                if args.action == 'receipt':
                    time.sleep(2)
        require(last_error is None, 'Signer policy check failed; no approval receipt produced')
    if args.action == 'approve':
        path = Path(args.config)
        require(not path.is_symlink() and path.is_file(), 'Config must be a regular, non-symlink file')
        with path.open('r+') as handle:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            original = handle.read()
            updated = patch_policy(original, proposal['target']['keyHash'])
            if updated != original:
                suffix = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                write_private(str(path) + '.before-rotation-' + suffix, original)
                # Preserve the inode for existing Docker single-file bind mounts.
                handle.seek(0)
                handle.write(updated)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
        print('Exact target added; backup retained; keys, database and other policies unchanged.')
    if args.action == 'ready':
        result = {'schema': 'dogeos/rotation-readiness/v1', 'proposalSha256': args.expected_sha256,
                  'signerAttestationPubkey': args.signer_public_key, 'transportPubkey': args.transport_public_key,
                  'advanceL1': True, 'advanceL2': True, 'tsoConnected': True,
                  'checkedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        receipt = Path(args.config).parent / ('rotation-readiness-' + args.expected_sha256 + '.json')
        if receipt.exists():
            previous = read_json(receipt)
            require(all(previous.get(key) == value for key, value in result.items() if key != 'checkedAt'), 'Existing readiness receipt conflicts')
        else:
            write_private(receipt, json.dumps(result, indent=2) + '\n')
        print('Readiness receipt written: identity and normal capabilities verified locally; TSO connectivity explicitly attested by operator.')
        print('This is not evidence of a completed signature; validate real WF signing after activation.')
    if args.action == 'receipt':
        config = Path(args.config)
        require(proposal['target']['keyHash'] in tomllib.loads(config.read_text()).get('rotation_policy', {}).get('allowed_next_bridge_script_hashes', []), 'Approved target no longer present in local config')
        result = {'schema': 'dogeos/rotation-approval/v1', 'proposalSha256': args.expected_sha256,
                  'signerAttestationPubkey': args.signer_public_key, 'targetKeyHash': proposal['target']['keyHash'],
                  'approvedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        receipt = config.parent / ('rotation-approval-' + args.expected_sha256 + '.json')
        if receipt.exists():
            previous = read_json(receipt)
            require(all(previous.get(key) == value for key, value in result.items() if key != 'approvedAt'), 'Existing receipt conflicts')
        else:
            write_private(receipt, json.dumps(result, indent=2) + '\n')
        print('Approval receipt written. Deliver it over your authenticated Governance/operator channel.')
        print('Runtime check verifies identity, enforce mode and RotateKey capability; /policy does not expose the loaded target allowlist.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        # Never render parser exceptions: malformed TOML can contain secrets.
        detail = str(error) if type(error) is ValueError else 'Review proposal, local configuration and operation prerequisites; private file contents are not logged.'
        print('Rotation operation failed; no successful approval is implied. ' + detail, file=sys.stderr)
        sys.exit(1)
