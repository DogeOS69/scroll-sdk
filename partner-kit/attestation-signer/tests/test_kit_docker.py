"""Actual Docker onboarding; only AWS provider calls are stubbed (no cloud resources)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

KIT = Path(__file__).parents[1]


@unittest.skipUnless(os.environ.get('SIGNER_KIT_DOCKER_TEST') == '1', 'Set SIGNER_KIT_DOCKER_TEST=1 for isolated Docker onboarding')
class KitDockerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='standalone-signer-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'operator'
        shutil.copytree(KIT, self.root, ignore=shutil.ignore_patterns('__pycache__'))
        # The normal operator layout may contain tracked public templates.
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', 'docker-compose.yml', 'signer.sh'], check=True)
        self.env = dict(os.environ)
        self.docker = shutil.which('docker')
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.env['PATH'] = str(self.bin) + os.pathsep + self.env['PATH']
        self.env['REAL_DOCKER'] = self.docker
        self.env['TEST_RECORDS'] = str(self.base)
        subprocess.run(['node', '--input-type=module', '-e', """
import {generateKeyPairSync} from 'node:crypto';
import fs from 'node:fs';
const {publicKey} = generateKeyPairSync('ec', {namedCurve: 'secp256k1'});
fs.writeFileSync(process.argv[1], JSON.stringify({KeyId: 'arn:aws:kms:us-east-1:000000000000:key/test-only', KeySpec: 'ECC_SECG_P256K1', KeyUsage: 'SIGN_VERIFY', SigningAlgorithms: ['ECDSA_SHA_256'], PublicKey: publicKey.export({format:'der',type:'spki'}).toString('base64')}));
""", str(self.base / 'get-key.json')], check=True, capture_output=True)
        stub = self.bin / 'docker'
        stub.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
if 'inspect-rotation' in sys.argv:
    # The core subcommand ships with the signer release; record how the wrapper calls it.
    pathlib.Path(os.environ['TEST_RECORDS'], 'inspect-args').write_text(json.dumps(sys.argv[1:]))
    sys.exit(0)
if any(x.startswith('public.ecr.aws/aws-cli/aws-cli:') for x in sys.argv):
    root = pathlib.Path(os.environ['TEST_RECORDS'])
    if 'sts' in sys.argv:
        if os.environ.get('FAIL_AUTH'): sys.exit(1)
        print('000000000000')
        sys.exit(0)
    action = sys.argv[sys.argv.index('kms') + 1]
    with (root / 'aws-calls').open('a') as f: f.write(action + '\\n')
    if action == 'create-key':
        if os.environ.get('FAIL_CREATE'): sys.exit(1)
        print(json.loads((root / 'get-key.json').read_text())['KeyId'])
    else:
        if os.environ.get('FAIL_GET'): sys.exit(1)
        print((root / 'get-key.json').read_text())
    sys.exit(0)
os.execv(os.environ['REAL_DOCKER'], [os.environ['REAL_DOCKER'], *sys.argv[1:]])
''')
        stub.chmod(0o755)

    def run_kit(self, *args, extra_env=None):
        return subprocess.run(['bash', './signer.sh', *args], cwd=self.root, env={**self.env, **(extra_env or {})}, capture_output=True, text=True, timeout=180)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_keys_match_core_and_rerun_without_changes(self):
        self.assert_ok(self.run_kit('init', '--name', 'test-signer', '--network', 'testnet'))
        files = ['attestation-signer.env', 'transport.key', 'public-identity.json', 'identity.json']
        original = {f: (self.root / f).read_bytes() for f in files}
        self.assert_ok(self.run_kit('init', '--name', 'test-signer', '--network', 'testnet'))
        for name, raw in original.items():
            self.assertTrue((self.root / name).read_bytes() == raw)
        image = next(line.split('=', 1)[1] for line in (self.root / '.env').read_text().splitlines() if line.startswith('SIGNER_IMAGE='))
        subprocess.run([self.docker, 'pull', image], check=True, capture_output=True, timeout=180)
        exported = subprocess.run([self.docker, 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--user', f'{os.getuid()}:{os.getgid()}',
                                   '--env-file', str(self.root / 'attestation-signer.env'),
                                   '--mount', f'type=bind,src={self.root / "transport.key"},dst=/etc/dogeos-partner/transport.key,readonly',
                                   '--entrypoint', '/usr/local/bin/attestation_signer', image, '--print-identity'],
                                  capture_output=True, text=True, timeout=120)
        self.assert_ok(exported)
        self.assertEqual(json.loads(exported.stdout), json.loads(original['identity.json']))
        public = self.run_kit('identity')
        self.assert_ok(public)
        self.assertNotIn((self.root / 'transport.key').read_text().strip(), public.stdout)
        self.assertFalse((self.base / 'aws-calls').exists())

    def test_kms_created_once_and_resumes_after_get_failure(self):
        args = ['init', '--name', 'test-kms', '--network', 'testnet', '--backend', 'aws-kms', '--kms-region', 'us-east-1', '--create-key']
        self.assertNotEqual(self.run_kit(*args, extra_env={'FAIL_GET': '1'}).returncode, 0)
        self.assertFalse((self.root / 'transport.key').exists())
        self.assert_ok(self.run_kit(*args))
        original = (self.root / 'transport.key').read_bytes()
        self.assert_ok(self.run_kit(*args))
        calls = (self.base / 'aws-calls').read_text().splitlines()
        self.assertEqual(calls.count('create-key'), 1)
        self.assertEqual(calls.count('get-public-key'), 3)
        self.assertTrue((self.root / 'transport.key').read_bytes() == original)
        self.assertNotIn('ATTESTATION_SIGNER_WIF=', (self.root / 'attestation-signer.env').read_text())
        (self.root / 'transport.key').unlink()
        before = (self.base / 'aws-calls').read_bytes()
        self.assertNotEqual(self.run_kit(*args).returncode, 0)
        self.assertEqual((self.base / 'aws-calls').read_bytes(), before)

    def test_uncertain_creation_is_not_repeated(self):
        args = ['init', '--name', 'test-kms', '--network', 'testnet', '--backend', 'aws-kms', '--kms-region', 'us-east-1', '--create-key']
        self.assertNotEqual(self.run_kit(*args, extra_env={'FAIL_CREATE': '1'}).returncode, 0)
        self.assertNotEqual(self.run_kit(*args).returncode, 0)
        self.assertEqual((self.base / 'aws-calls').read_text().splitlines(), ['create-key'])
        recovered = args[:-1] + ['--kms-key-id', 'arn:aws:kms:us-east-1:000000000000:key/test-only']
        self.assert_ok(self.run_kit(*recovered))

    def test_import_compose_config_and_start_with_a_cli_kit(self):
        from test_runtime import FIXTURE, FIXTURE_DIGEST
        self.assert_ok(self.run_kit('init', '--name', 'test-import', '--network', 'testnet'))
        self.addCleanup(subprocess.run, [self.docker, 'compose', 'down', '--timeout', '1'], cwd=self.root, capture_output=True, timeout=120)
        toml = self.root / 'attestation-signer.toml'
        toml.write_text(toml.read_text().replace('.example.invalid', '.test'))
        private = ['attestation-signer.env', 'transport.key', 'attestation-signer.toml', 'identity.json', 'public-identity.json', 'aws.env']
        before = {name: (self.root / name).read_bytes() for name in private}
        self.assert_ok(self.run_kit('import', str(FIXTURE), FIXTURE_DIGEST))
        compose = subprocess.run([self.docker, 'compose', 'config', '--quiet'], cwd=self.root, capture_output=True, text=True)
        self.assert_ok(compose)
        with (self.root / 'aws.env').open('a') as f:
            f.write('ATTESTATION_SIGNER_ADVANCE_L2_ETHEREUM_SOURCE_SET_JSON=PRIVATE_VALUE_SENTINEL\n')
        blocked = self.run_kit('start')
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('Remove RPC JSON env overrides', blocked.stderr)
        self.assertNotIn('PRIVATE_VALUE_SENTINEL', blocked.stdout + blocked.stderr)
        (self.root / 'aws.env').write_bytes(before['aws.env'] + b'ATTESTATION_SIGNER_TSO_URL=https://tso.attacker.test\n')
        overridden = self.run_kit('start')
        self.assertNotEqual(overridden.returncode, 0)
        self.assertIn('overrides the deployment kit field ATTESTATION_SIGNER_TSO_URL', overridden.stderr)
        (self.root / 'aws.env').write_bytes(before['aws.env'])
        installed = self.root / 'bundles' / FIXTURE_DIGEST / 'deployment-kit.env'
        original = installed.read_bytes()
        installed.chmod(0o600)
        installed.write_bytes(original.replace(b'https://tso.example.com', b'https://tso.attacker.test'))
        tampered = self.run_kit('start')
        self.assertNotEqual(tampered.returncode, 0)
        self.assertIn('digest mismatch', tampered.stderr)
        self.assertFalse(any((self.root / 'data').iterdir()))
        installed.write_bytes(original)
        self.assert_ok(self.run_kit('start'))
        running = subprocess.run([self.docker, 'compose', 'ps', '-q', 'attestation-signer'], cwd=self.root, capture_output=True, text=True)
        self.assertTrue(running.stdout.strip())
        for name, raw in before.items():
            self.assertTrue((self.root / name).read_bytes() == raw, name)

    def test_inspect_runs_the_signer_image_offline_and_read_only(self):
        from test_runtime import FIXTURE, FIXTURE_DIGEST
        self.assertNotEqual(self.run_kit('inspect', 'missing.json').returncode, 0)
        self.assert_ok(self.run_kit('init', '--name', 'test-inspect', '--network', 'testnet'))
        export = self.base / 'rotation-export.json'
        export.write_text('{}')
        self.assertNotEqual(self.run_kit('inspect', str(export)).returncode, 0)
        self.assert_ok(self.run_kit('import', str(FIXTURE), FIXTURE_DIGEST))
        self.assert_ok(self.run_kit('inspect', str(export)))
        args = json.loads((self.base / 'inspect-args').read_text())
        image = next(line.split('=', 1)[1] for line in (self.root / '.env').read_text().splitlines() if line.startswith('SIGNER_IMAGE='))
        self.assertEqual(args[-3:], [image, 'inspect-rotation', '/rotation-export.json'])
        for flag in ['--network', '--read-only', '--cap-drop']:
            self.assertIn(flag, args)
        self.assertEqual(args[args.index('--network') + 1], 'none')
        mounts = [args[i + 1] for i, arg in enumerate(args) if arg == '--mount']
        self.assertIn(f'type=bind,src={export},dst=/rotation-export.json,readonly', mounts)
        self.assertTrue(all(mount.endswith(',readonly') for mount in mounts))
        # Least privilege: only the kit and the export; no TOML (it may hold RPC credentials), keys or AWS files.
        self.assertEqual(sorted(mount.split(',dst=')[1].split(',')[0] for mount in mounts), ['/etc/dogeos', '/rotation-export.json'])
        self.assertNotIn('--env-file', args)
        envs = [args[i + 1] for i, arg in enumerate(args) if arg == '--env']
        self.assertEqual(envs, ['ATTESTATION_SIGNER_NETWORK=testnet', 'ATTESTATION_SIGNER_PROTOCOL_CONTEXT_JSON=/etc/dogeos/protocol_context.json'])

    def test_missing_credentials_never_marks_creation_uncertain(self):
        args = ['init', '--name', 'test-kms', '--network', 'testnet', '--backend', 'aws-kms', '--kms-region', 'us-east-1', '--create-key']
        result = self.run_kit(*args, extra_env={'FAIL_AUTH': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No KMS creation was attempted', result.stderr)
        self.assertFalse((self.root / '.kms/create-pending').exists())
        self.assertFalse((self.base / 'aws-calls').exists())
        self.assert_ok(self.run_kit(*args))

    def test_known_legacy_missing_credentials_can_retry_after_authentication(self):
        args = ['init', '--name', 'test-kms', '--network', 'testnet', '--backend', 'aws-kms', '--kms-region', 'us-east-1', '--create-key']
        self.assertNotEqual(self.run_kit(*args, extra_env={'FAIL_AUTH': '1'}).returncode, 0)
        (self.root / '.kms/create-pending').touch()
        (self.root / '.kms/region').write_text('us-east-1\n')
        (self.root / '.kms/provider-error.log').write_text('Unable to locate credentials. You can configure credentials by running aws configure.\n')
        self.assert_ok(self.run_kit(*args))
        self.assertEqual((self.base / 'aws-calls').read_text().splitlines().count('create-key'), 1)
