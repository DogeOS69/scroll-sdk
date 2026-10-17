"""Standalone operator helpers. Run inside the pinned Python container."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
from urllib.parse import urlparse
import urllib.request

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


MANIFEST = 'deployment-kit-manifest.json'
KIT_FILES = {'deployment-kit.json', 'deployment-kit.env', 'protocol_context.json', 'advance-l2-agg-verifying-key.bin'}
SAFE_NAME = r'[A-Za-z0-9][A-Za-z0-9_.-]*'
COMMITMENT = r'0x[0-9a-f]{128}'


def sha256_ref(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def verify_kit(folder, expected, identity_file):
    """Verify a deployment kit directory against its authenticated manifest digest."""
    manifest_raw = regular(folder / MANIFEST)
    require(hashlib.sha256(manifest_raw).hexdigest() == expected, 'Manifest differs from authenticated digest')
    manifest = json.loads(manifest_raw)
    require(manifest['schema'] == 'dogeos/deployment-kit-manifest/v1', 'Unsupported kit manifest schema')
    names = set()
    for entry in manifest['files']:
        name = entry['file']
        require(isinstance(name, str) and re.fullmatch(SAFE_NAME, name) and name != MANIFEST, 'Unsafe kit filename')
        require(name not in names, 'Duplicate kit file')
        names.add(name)
        raw = regular(folder / name)
        require(sha256_ref(raw) == entry['sha256'], 'Kit file digest mismatch')
        require(len(raw) == entry['sizeBytes'], 'Kit file size mismatch')
    require(names == KIT_FILES, 'Deployment kit must list exactly the required files')
    kit = json.loads(regular(folder / 'deployment-kit.json'))
    require(kit['schema'] == 'dogeos/deployment-kit/v1', 'Unsupported deployment kit schema')
    require(kit['policy_mode'] == 'enforce', 'Expected enforce mode')
    require(isinstance(kit['kit_version'], str) and re.fullmatch(r'k-[0-9a-f]{12}', kit['kit_version']), 'Invalid kit version')
    identity = json.loads(regular(identity_file))
    require(identity['schema'] == 'dogeos/attestation-signer-descriptor/v1', 'Use core --print-identity JSON')
    require(identity['network'] == kit['network'], 'Kit is for another network than this signer')
    require(re.fullmatch(r'0x[0-9a-f]{64}', kit['protocol_instance_id']), 'Invalid protocol instance id')
    context, verifier = kit['protocol_context'], kit['advance_l2_verifier']
    require(context['file'] == 'protocol_context.json' and verifier['agg_verifying_key_file'] == 'advance-l2-agg-verifying-key.bin', 'Unexpected kit material filename')
    require(sha256_ref(regular(folder / 'protocol_context.json')) == context['sha256'], 'Context does not match kit')
    require(sha256_ref(regular(folder / 'advance-l2-agg-verifying-key.bin')) == verifier['agg_verifying_key_sha256'], 'Verifier does not match kit')
    require(re.fullmatch(COMMITMENT, verifier['batch_program_commitment_hex']) and re.fullmatch(COMMITMENT, verifier['l2_range_aggregation_program_commitment_hex']), 'Missing verifier commitments')
    values = env_values(regular(folder / 'deployment-kit.env'))
    require(set(values) == BRIDGE_FIELDS, 'Bridge env contains missing or non-bridge fields; it cannot set keys, RPC trust, binary pins or rotation permissions')
    # Core validates endpoints/commitments at startup. Reject Compose interpolation here.
    require(all('$' not in v and not v.startswith(('"', "'")) for v in values.values()), 'Bridge env must contain literal values')
    require(values['ATTESTATION_SIGNER_POLICY_MODE'] == 'enforce', 'Expected enforce mode')
    require(values['ATTESTATION_SIGNER_NETWORK'] == kit['network'], 'Bridge env network mismatch')
    require(values['ATTESTATION_SIGNER_PROTOCOL_CONTEXT_JSON'] == '/etc/dogeos/protocol_context.json', 'Invalid context path')
    require(values['ATTESTATION_SIGNER_ADVANCE_L2_AGG_VERIFYING_KEY_PATH'] == '/etc/dogeos/advance-l2-agg-verifying-key.bin', 'Invalid verifier path')
    require(values['ATTESTATION_SIGNER_TSO_URL'] == kit['tso_url'], 'TSO URL does not match kit')
    require([values['ATTESTATION_SIGNER_ARTIFACT_ALLOWED_ORIGINS']] == kit['artifact_origins'], 'Artifact origin does not match kit')
    for field, key in [('ATTESTATION_SIGNER_ADVANCE_L2_BATCH_PROGRAM_COMMITMENT_HEX', 'batch_program_commitment_hex'), ('ATTESTATION_SIGNER_L2_RANGE_AGGREGATION_PROGRAM_COMMITMENT_HEX', 'l2_range_aggregation_program_commitment_hex')]:
        require(values[field] == verifier[key], 'Verifier commitment does not match kit')
    return names | {MANIFEST}


def install(root, folder, expected):
    require(re.fullmatch(r'[0-9a-f]{64}', expected), 'Use the authenticated manifest SHA-256')
    # Snapshot once; verify and install exactly those bytes, not a subsequently changed input.
    bundles = root / 'bundles'
    require(not bundles.is_symlink(), 'Bundles directory must not be a symlink')
    bundles.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import-', dir=bundles) as temp:
        snapshot = Path(temp)
        manifest = regular(folder / MANIFEST)
        require(hashlib.sha256(manifest).hexdigest() == expected, 'Manifest differs from authenticated digest')
        put_private(snapshot / MANIFEST, manifest)
        for entry in json.loads(manifest)['files']:
            name = entry['file']
            require(isinstance(name, str) and re.fullmatch(SAFE_NAME, name) and name != MANIFEST, 'Unsafe kit filename')
            require(not (snapshot / name).exists(), 'Duplicate kit file')
            put_private(snapshot / name, regular(folder / name))
        verify_kit(snapshot, expected, root / 'identity.json')
        final = bundles / expected
        require(not final.is_symlink(), 'Kit record must not be a symlink')
        if final.exists():
            verify_active_files(final, expected, root / 'identity.json')
        else:
            snapshot.rename(final)
            snapshot.mkdir()  # TemporaryDirectory cleanup only removes this empty directory.
        active = root / 'active-bundle'
        require(not active.exists() or active.is_symlink(), 'active-bundle must be the managed link')
        temp_link = root / '.active-bundle.next'
        require(not temp_link.exists() and not temp_link.is_symlink(), 'Interrupted import link exists; inspect before retrying')
        temp_link.symlink_to(Path('bundles') / expected, target_is_directory=True)
        os.replace(temp_link, active)
    print('Deployment kit verified and installed. Private keys, operator RPC trust and rotation allowlists were not changed.')


def verify_active_files(folder, expected, identity_file):
    listed = verify_kit(folder, expected, identity_file)
    require({p.name for p in folder.iterdir()} == listed, 'Installed kit contains unlisted files')


def verify_active(root):
    """Re-verify the selected kit before start and inspect read it."""
    active = root / 'active-bundle'
    require(active.is_symlink(), 'Import the approved deployment kit first')
    target = os.readlink(active)
    expected = Path(target).name
    require(Path(target) == Path('bundles') / expected and re.fullmatch(r'[0-9a-f]{64}', expected), 'active-bundle must link to an imported kit')
    require(not (root / 'bundles').is_symlink(), 'Bundles directory must not be a symlink')
    folder = root / 'bundles' / expected
    require(folder.is_dir() and not folder.is_symlink(), 'Imported kit is missing')
    verify_active_files(folder, expected, root / 'identity.json')
    return folder


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


KIT_COMMAND = ['-c', '/etc/dogeos-partner/attestation-signer.toml']


def check_service(service, host_root):
    """The resolved service must run the kit's own command and mount active-bundle/ at /etc/dogeos."""
    require(service.get('command') == KIT_COMMAND and not service.get('entrypoint'), 'Compose command or entrypoint differs from the signer kit')
    kit_mounts = [v for v in service.get('volumes', []) if v.get('target', '').rstrip('/') == '/etc/dogeos' or v.get('target', '').startswith('/etc/dogeos/')]
    require(len(kit_mounts) == 1 and kit_mounts[0].get('type') == 'bind' and kit_mounts[0].get('target') == '/etc/dogeos'
            and kit_mounts[0].get('source') == host_root + '/active-bundle' and kit_mounts[0].get('read_only') is True,
            'Compose must mount only active-bundle, read-only, at /etc/dogeos')


def prestart(root, compose, host_root):
    kit_env = env_values(regular(verify_active(root) / 'deployment-kit.env'))
    service = compose['services']['attestation-signer']
    check_service(service, host_root)
    environment = service.get('environment', {})
    # Operator env files load after the kit; they must not replace any bridge field.
    for field in sorted(BRIDGE_FIELDS):
        require(environment.get(field) == kit_env[field], 'Operator configuration overrides the deployment kit field ' + field)
    reject_rpc_overrides(environment)
    validate_rpc_config(root)
    print('Active deployment kit and RPC file configuration checked. Independent ownership of the sources still requires operator review.')


def check_report(identity, report):
    require(report.get('contract') == 'attestation_evidence_v2', 'Unexpected policy contract')
    require(report.get('public_key', '').removeprefix('0x').lower() == identity['publicKey'], 'Running attestation identity mismatch')
    # The pinned runtime serializes Dogecoin mainnet using bitcoin::Network.
    expected_network = 'bitcoin' if identity['network'] == 'mainnet' else identity['network']
    require(report.get('network') in (identity['network'], expected_network), 'Running network mismatch')
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
        install(root, Path('/kit'), sys.argv[2])
    elif action == 'prestart':
        prestart(root, json.load(sys.stdin), sys.argv[2])
    elif action == 'verify':
        verify_active(root)
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
        print('Operation failed. Check arguments, file integrity, ownership, kit fields or local signer capabilities. No private values are logged.', file=sys.stderr)
        sys.exit(1)
