"""Read-only verification; no CLI descriptor wrapper or host Python required."""
import hashlib
import json
from pathlib import Path
import re
import sys


def verify_bundle(folder, identity_file, expected):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def regular(file):
        require(file.is_file() and not file.is_symlink(), 'Bundle files must be regular files')
        return file.read_bytes()

    manifest_bytes = regular(folder / 'signer-policy-manifest.json')
    require(hashlib.sha256(manifest_bytes).hexdigest() == expected, 'Manifest differs from authenticated digest')
    manifest = json.loads(manifest_bytes)
    require(manifest['schema'] == 'dogeos/attestation-signer-policy-manifest/v1', 'Unsupported manifest schema')
    names = set()
    for entry in manifest['files']:
        name = entry['file']
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name), 'Unsafe bundle filename')
        require(name not in names, 'Duplicate bundle file')
        names.add(name)
        raw = regular(folder / name)
        require('sha256:' + hashlib.sha256(raw).hexdigest() == entry['sha256'], 'Bundle file digest mismatch')
        require(len(raw) == entry['sizeBytes'], 'Bundle file size mismatch')
    require({'signer-policy.json', 'signer-policy.env', 'protocol_context.json'} <= names, 'Incomplete signer bundle')
    identity = json.loads(regular(identity_file))
    require(identity['schema'] == 'dogeos/attestation-signer-descriptor/v1', 'Use core --print-identity JSON')
    policy = json.loads(regular(folder / 'signer-policy.json'))
    require(policy['contract'] == 'attestation_evidence_v2', 'Unsupported policy contract')
    require(identity['network'] == policy['network'], 'Signer and bridge networks differ')
    require(any(s['publicKey'] == identity['publicKey'] and s['transportPubkey'] == identity['transportPubkey'] for s in policy['signers']), 'Public key pair is not registered in this bundle')
    require(policy['mode'] == 'active' and policy['generation'] == 'real' and policy['enforcement'] == 'enforce', 'This rotation guide requires active/real/enforce')
    require('advance-l2-agg-verifying-key.bin' in names, 'Missing production verifying key')
    return {'verified': True, 'network': policy['network'], 'files': sorted(names),
            'note': 'Review RPC trust sources and release pins independently. This verifies integrity and membership, not runtime readiness.'}


if __name__ == '__main__':
    try:
        print(json.dumps(verify_bundle(Path('/bundle'), Path('/identity.json'), sys.argv[1]), indent=2))
    except (ValueError, KeyError, TypeError, OSError, IndexError):
        print('Bundle verification failed: check authenticated digest, complete files, core identity and active/real/enforce policy. Private file contents are not logged.', file=sys.stderr)
        sys.exit(1)
