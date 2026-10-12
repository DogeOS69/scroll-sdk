"""Standalone operator helpers. Run inside the pinned Python container."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
from urllib.parse import urlparse
import urllib.request

spec = importlib.util.spec_from_file_location('handoff', Path(__file__).with_name('verify-handoff.py'))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class OperatorError(ValueError):
    """Only static messages and public field names may enter this exception."""


def require(ok, message):
    if not ok:
        raise OperatorError(message)


def regular(path):
    require(path.is_file() and not path.is_symlink(), f'Expected regular file: {path.name}')
    return path.read_bytes()


def env_values(raw):
    result = {}
    for line in raw.decode().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]*)=([^\r\n]*)', line)
        require(match is not None and match[1] not in result, 'Invalid or duplicate env assignment')
        result[match[1]] = match[2]
    return result


def put_private(path, data):
    with path.open('xb') as f:
        os.chmod(path, 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def prepare(root, name):
    require(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', name) and len(name) <= 63, 'Use a DNS-label signer name')
    for filename in ['.env', 'aws.env']:
        p = root / filename
        if p.exists() or p.is_symlink():
            regular(p)
            os.chmod(p, 0o600)
        else:
            data = regular(root / (filename + '.example')).replace(b'REPLACE_WITH_SIGNER_NAME', name.encode())
            put_private(p, data)
    settings = env_values(regular(root / '.env'))
    require(settings.get('COMPOSE_PROJECT_NAME') == name, 'Existing Compose project name differs; do not reuse another signer directory')
    require(re.fullmatch(r'[^\s$]+@sha256:[a-f0-9]{64}', settings.get('SIGNER_IMAGE', '')), 'SIGNER_IMAGE must be an approved immutable digest')
    require(re.fullmatch(r'[0-9a-f]{40}', settings.get('SIGNER_GIT_COMMIT', '')), 'Provide the approved full commit')
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?', settings.get('SIGNER_RELEASE_VERSION', '')), 'Invalid release version')
    require(re.fullmatch(r'[1-9][0-9]*', settings.get('SIGNER_POLICY_VERSION', '')), 'Invalid policy version')
    for directory in ['aws', '.kms']:
        p = root / directory
        require(not p.is_symlink(), 'Private directories must not be symlinks')
        p.mkdir(mode=0o700, exist_ok=True)
    regular(root / 'attestation-signer.toml')
    os.chmod(root / 'attestation-signer.toml', 0o600)
    print('Workspace ready; attestation-signer.toml and aws.env stay private.')


BRIDGE_FIELDS = {
    'ATTESTATION_SIGNER_POLICY_MODE', 'ATTESTATION_SIGNER_NETWORK',
    'ATTESTATION_SIGNER_PROTOCOL_CONTEXT_JSON', 'ATTESTATION_SIGNER_ARTIFACT_ALLOWED_ORIGINS',
    'ATTESTATION_SIGNER_ADVANCE_L2_AGG_VERIFYING_KEY_PATH',
    'ATTESTATION_SIGNER_ADVANCE_L2_BATCH_PROGRAM_COMMITMENT_HEX',
    'ATTESTATION_SIGNER_L2_RANGE_AGGREGATION_PROGRAM_COMMITMENT_HEX', 'ATTESTATION_SIGNER_TSO_URL',
}


def install(root, folder, expected):
    require(re.fullmatch(r'[0-9a-f]{64}', expected), 'Use the authenticated manifest SHA-256')
    # Snapshot once; verify and install exactly those bytes, not a subsequently changed input.
    bundles = root / 'bundles'
    require(not bundles.is_symlink(), 'Bundles directory must not be a symlink')
    bundles.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import-', dir=bundles) as temp:
        snapshot = Path(temp)
        manifest = regular(folder / 'signer-policy-manifest.json')
        require(hashlib.sha256(manifest).hexdigest() == expected, 'Manifest differs from authenticated digest')
        put_private(snapshot / 'signer-policy-manifest.json', manifest)
        for entry in json.loads(manifest)['files']:
            name = entry['file']
            require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name), 'Unsafe bundle filename')
            put_private(snapshot / name, regular(folder / name))
        handoff.verify_bundle(snapshot, root / 'identity.json', expected)
        policy = json.loads(regular(snapshot / 'signer-policy.json'))
        values = env_values(regular(snapshot / 'signer-policy.env'))
        require(set(values) == BRIDGE_FIELDS, 'Bridge env contains missing or non-bridge fields; it cannot set keys, RPC trust, binary pins or rotation permissions')
        require(values['ATTESTATION_SIGNER_POLICY_MODE'] == 'enforce', 'Expected enforce mode')
        require(values['ATTESTATION_SIGNER_NETWORK'] == policy['network'], 'Bridge env network mismatch')
        require(values['ATTESTATION_SIGNER_PROTOCOL_CONTEXT_JSON'] == '/etc/dogeos/protocol_context.json', 'Invalid context path')
        require(values['ATTESTATION_SIGNER_ADVANCE_L2_AGG_VERIFYING_KEY_PATH'] == '/etc/dogeos/advance-l2-agg-verifying-key.bin', 'Invalid verifier path')
        # Core validates endpoints/commitments at startup. Reject Compose interpolation here.
        require(all('$' not in v and not v.startswith(('"', "'")) for v in values.values()), 'Bridge env must contain literal values')
        context = regular(snapshot / 'protocol_context.json')
        require('sha256:' + hashlib.sha256(context).hexdigest() == policy['protocolContext']['sha256'], 'Context does not match policy')
        vk = regular(snapshot / 'advance-l2-agg-verifying-key.bin')
        require('sha256:' + hashlib.sha256(vk).hexdigest() == policy['advanceL2Verifier']['aggVerifyingKeySha256'], 'Verifier does not match policy')
        require(values['ATTESTATION_SIGNER_TSO_URL'] == policy['tsoUrl'], 'TSO URL does not match policy')
        for field, key in [('ATTESTATION_SIGNER_ADVANCE_L2_BATCH_PROGRAM_COMMITMENT_HEX', 'batchProgramCommitmentHex'), ('ATTESTATION_SIGNER_L2_RANGE_AGGREGATION_PROGRAM_COMMITMENT_HEX', 'l2RangeAggregationProgramCommitmentHex')]:
            require(values[field] == policy['advanceL2Verifier'][key], 'Verifier commitment does not match policy')
        final = bundles / expected
        require(not final.is_symlink(), 'Bundle record must not be a symlink')
        if final.exists():
            handoff.verify_bundle(final, root / 'identity.json', expected)
        else:
            snapshot.rename(final)
            snapshot.mkdir()  # TemporaryDirectory cleanup only removes this empty directory.
        active = root / 'active-bundle'
        require(not active.exists() or active.is_symlink(), 'active-bundle must be the managed link')
        temp_link = root / '.active-bundle.next'
        require(not temp_link.exists() and not temp_link.is_symlink(), 'Interrupted import link exists; inspect before retrying')
        temp_link.symlink_to(Path('bundles') / expected, target_is_directory=True)
        os.replace(temp_link, active)
    print('Bundle verified and installed. Private keys, operator RPC trust and rotation allowlists were not changed.')



SOURCE_ENV_OVERRIDES = {
    'ATTESTATION_SIGNER_ADVANCE_L1_TERMINAL_ANCHOR_SOURCE_SET_JSON',
    'ATTESTATION_SIGNER_ADVANCE_L2_ETHEREUM_SOURCE_SET_JSON',
    'ATTESTATION_SIGNER_ADVANCE_L2_L2_SOURCE_SET_JSON',
}


def reject_rpc_overrides(env):
    found = SOURCE_ENV_OVERRIDES.intersection(env)
    require(not found, 'Remove RPC JSON env overrides: ' + ', '.join(sorted(found)))


def validate_rpc_config(root):
    filename = root / 'attestation-signer.toml'
    raw = regular(filename)
    require(filename.stat().st_mode & 0o777 == 0o600, 'Private attestation-signer.toml must have mode 0600')
    policy = tomllib.loads(raw.decode())
    for section, field in [('advance_l1_policy', 'terminal_anchor_sources'), ('advance_l2_policy', 'ethereum_sources'), ('advance_l2_policy', 'l2_sources')]:
        group = policy.get(section, {}).get(field, {})
        threshold = group.get('required_agreement')
        require(group.get('posture') == 'quorum' and type(threshold) is int and threshold >= 2, 'Configure quorum >= 2 for ' + field)
        sources = group.get('sources', [])
        domains = [source.get('trust_domain_id') for source in sources]
        require(len(sources) >= threshold and all(isinstance(d, str) and d.strip() for d in domains) and len(set(domains)) == len(domains), 'Provide enough distinct trust domains for ' + field)
        for source in sources:
            url = urlparse(source.get('rpc_url', ''))
            require(url.scheme in ('http', 'https') and url.hostname and not url.hostname.endswith(('.invalid', '.example')) and not url.username and not url.password and not url.query and not url.fragment, 'Replace placeholders with supported RPC URLs for ' + field)
            require(all('REPLACE_WITH_' not in str(v) for v in source.values()), 'Fill or remove credential placeholders for ' + field)
    # A previous env-based deployment must explicitly migrate its private source
    # configuration. Do not silently ignore a leftover operator.env file.
    legacy = root / 'operator.env'
    if legacy.exists() or legacy.is_symlink():
        require(not env_values(regular(legacy)), 'Move legacy operator.env settings into TOML; this kit does not load operator.env')


def prestart(root, compose):
    service = compose['services']['attestation-signer']
    environment = service.get('environment', {})
    reject_rpc_overrides(environment)
    validate_rpc_config(root)
    print('RPC file configuration checked. Independent ownership of the sources still requires operator review.')


def check_report(identity, report):
    require(report.get('contract') == 'attestation_evidence_v2', 'Unexpected policy contract')
    require(report.get('public_key', '').removeprefix('0x').lower() == identity['publicKey'], 'Running attestation identity mismatch')
    require(report.get('network') == identity['network'], 'Running network mismatch')
    require(report.get('policy_mode') == 'enforce', 'Signer is not enforcing policy')
    for capability in ['advance_l1', 'advance_l2']:
        rows = [row for row in report.get('v2_capabilities', []) if row.get('capability') == capability]
        require(len(rows) == 1 and rows[0].get('production_serving') is True, f'{capability} is not serving; inspect local /policy')
    return {'identityMatches': True, 'advanceL1': True, 'advanceL2': True,
            'tsoAuthenticatedPolling': 'bridge_operator_confirmation_required',
            'note': 'Future rotation allowlists are not required. This is local readiness, not proof of TSO connection or real signing.'}


def main():
    action = sys.argv[1]
    root = Path('/workspace')
    if action == 'prepare':
        prepare(root, sys.argv[2])
    elif action == 'import':
        install(root, Path('/bundle'), sys.argv[2])
    elif action == 'prestart':
        prestart(root, json.load(sys.stdin))
    elif action == 'check':
        identity = json.loads(regular(root / 'identity.json'))
        with urllib.request.urlopen('http://127.0.0.1:4040/policy', timeout=5) as response:
            report = json.load(response)
        print(json.dumps(check_report(identity, report), indent=2))
    else:
        raise ValueError('Unknown action')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        if isinstance(error, OperatorError):
            print(str(error), file=sys.stderr)
        # No provider responses, URLs, keys or arbitrary file contents in diagnostics.
        print('Operation failed. Check arguments, file integrity, ownership, bundle fields or local signer capabilities. No private values are logged.', file=sys.stderr)
        sys.exit(1)
