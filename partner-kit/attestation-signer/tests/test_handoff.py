"""Integrity and core-identity checks using disposable public fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('verify_handoff', Path(__file__).parents[1] / 'scripts/verify-handoff.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.identity = {'schema': 'dogeos/attestation-signer-descriptor/v1', 'network': 'testnet', 'publicKey': 'public-a', 'transportPubkey': 'transport-a'}
        self.identity_file = self.root / 'identity.json'
        self.identity_file.write_text(json.dumps(self.identity))
        policy = {'contract': 'attestation_evidence_v2', 'network': 'testnet', 'mode': 'active', 'generation': 'real', 'enforcement': 'enforce', 'signers': [self.identity]}
        (self.bundle / 'signer-policy.json').write_text(json.dumps(policy))
        for name in ['signer-policy.env', 'protocol_context.json', 'advance-l2-agg-verifying-key.bin']:
            (self.bundle / name).write_text('disposable fixture')
        self.refresh_manifest()

    def refresh_manifest(self):
        files = [{'file': p.name, 'sizeBytes': p.stat().st_size, 'sha256': 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()} for p in self.bundle.iterdir() if p.name != 'signer-policy-manifest.json']
        self.manifest = self.bundle / 'signer-policy-manifest.json'
        self.manifest.write_text(json.dumps({'schema': 'dogeos/attestation-signer-policy-manifest/v1', 'files': files}))
        self.sha = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def verify(self):
        return module.verify_bundle(self.bundle, self.identity_file, self.sha)

    def test_core_pair_without_cli_descriptor(self):
        self.assertTrue(self.verify()['verified'])

    def test_wrong_digest_and_tampering(self):
        self.sha = '0' * 64
        with self.assertRaisesRegex(ValueError, 'authenticated digest'):
            self.verify()
        self.refresh_manifest()
        (self.bundle / 'signer-policy.env').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.verify()

    def test_pair_and_network_must_match(self):
        for field in ['publicKey', 'transportPubkey', 'network']:
            self.identity_file.write_text(json.dumps({**self.identity, field: 'wrong'}))
            with self.assertRaises(ValueError):
                self.verify()

    def test_no_symlink_or_path_escape(self):
        p = self.bundle / 'signer-policy.env'
        p.unlink()
        p.symlink_to(self.identity_file)
        with self.assertRaisesRegex(ValueError, 'regular'):
            self.verify()
        m = json.loads(self.manifest.read_text())
        m['files'][0]['file'] = '../identity.json'
        self.manifest.write_text(json.dumps(m))
        self.sha = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            self.verify()
