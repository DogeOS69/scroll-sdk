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
if any(x.startswith('public.ecr.aws/aws-cli/aws-cli:') for x in sys.argv):
    root = pathlib.Path(os.environ['TEST_RECORDS'])
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
        exported = subprocess.run(['bash', 'scripts/identity.sh', image, '.'], cwd=self.root, env=self.env, capture_output=True, text=True, timeout=120)
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

    def test_import_and_resolved_compose_reject_rpc_env_overrides_without_starting(self):
        from test_runtime import RuntimeTests
        self.assert_ok(self.run_kit('init', '--name', 'test-import', '--network', 'testnet'))
        fixture = RuntimeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        policy_file = fixture.bundle / 'signer-policy.json'
        policy = json.loads(policy_file.read_text())
        policy['signers'] = [json.loads((self.root / 'identity.json').read_text())]
        policy_file.write_text(json.dumps(policy))
        digest = fixture.manifest()
        self.assert_ok(self.run_kit('import', str(fixture.bundle), digest))
        compose = subprocess.run([self.docker, 'compose', 'config', '--quiet'], cwd=self.root, capture_output=True, text=True)
        self.assert_ok(compose)
        initial = self.run_kit('start')
        self.assertNotEqual(initial.returncode, 0)
        self.assertIn('placeholders', initial.stderr)
        toml = self.root / 'attestation-signer.toml'
        toml.write_text(toml.read_text().replace('.example.invalid', '.test'))
        with (self.root / 'aws.env').open('a') as f:
            f.write('ATTESTATION_SIGNER_ADVANCE_L2_ETHEREUM_SOURCE_SET_JSON=PRIVATE_VALUE_SENTINEL\n')
        blocked = self.run_kit('start')
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('Remove RPC JSON env overrides', blocked.stderr)
        self.assertNotIn('PRIVATE_VALUE_SENTINEL', blocked.stdout + blocked.stderr)
        self.assertFalse(any((self.root / 'data').iterdir()))
