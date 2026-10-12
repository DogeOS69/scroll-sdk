"""Operator boundaries: untrusted bundle import and capability-specific readiness."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('runtime', Path(__file__).parents[1] / 'scripts/runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'operator'
        self.root.mkdir()
        self.bundle = Path(tmp.name) / 'received'
        self.bundle.mkdir()
        self.identity = {'schema': 'dogeos/attestation-signer-descriptor/v1', 'network': 'testnet', 'publicKey': 'test-public-key', 'transportPubkey': 'test-transport-key'}
        (self.root / 'identity.json').write_text(json.dumps(self.identity))
        for name in ['attestation-signer.env', 'transport.key', 'attestation-signer.toml', 'operator.env']:
            (self.root / name).write_text('private operator-owned fixture')
        self.original = {p.name: p.read_bytes() for p in self.root.iterdir()}
        context, vk = b'{"fixture":true}', b'disposable-verifier-fixture'
        policy = {'contract': 'attestation_evidence_v2', 'network': 'testnet', 'mode': 'active', 'generation': 'real', 'enforcement': 'enforce', 'signers': [self.identity], 'tsoUrl': 'https://tso.example.invalid', 'protocolContext': {'sha256': 'sha256:' + hashlib.sha256(context).hexdigest()}, 'advanceL2Verifier': {'aggVerifyingKeySha256': 'sha256:' + hashlib.sha256(vk).hexdigest(), 'batchProgramCommitmentHex': '0x' + 'a' * 128, 'l2RangeAggregationProgramCommitmentHex': '0x' + 'b' * 128}}
        values = {
            'ATTESTATION_SIGNER_POLICY_MODE': 'enforce', 'ATTESTATION_SIGNER_NETWORK': 'testnet',
            'ATTESTATION_SIGNER_PROTOCOL_CONTEXT_JSON': '/etc/dogeos/protocol_context.json',
            'ATTESTATION_SIGNER_ARTIFACT_ALLOWED_ORIGINS': 'https://proof.example.invalid',
            'ATTESTATION_SIGNER_ADVANCE_L2_AGG_VERIFYING_KEY_PATH': '/etc/dogeos/advance-l2-agg-verifying-key.bin',
            'ATTESTATION_SIGNER_ADVANCE_L2_BATCH_PROGRAM_COMMITMENT_HEX': '0x' + 'a' * 128,
            'ATTESTATION_SIGNER_L2_RANGE_AGGREGATION_PROGRAM_COMMITMENT_HEX': '0x' + 'b' * 128,
            'ATTESTATION_SIGNER_TSO_URL': policy['tsoUrl'],
        }
        (self.bundle / 'signer-policy.env').write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
        (self.bundle / 'signer-policy.json').write_text(json.dumps(policy))
        (self.bundle / 'protocol_context.json').write_bytes(context)
        (self.bundle / 'advance-l2-agg-verifying-key.bin').write_bytes(vk)
        self.digest = self.manifest()

    def manifest(self):
        files = [{'file': p.name, 'sizeBytes': p.stat().st_size, 'sha256': 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()} for p in self.bundle.iterdir() if p.name != 'signer-policy-manifest.json']
        raw = json.dumps({'schema': 'dogeos/attestation-signer-policy-manifest/v1', 'files': files}).encode()
        (self.bundle / 'signer-policy-manifest.json').write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def install(self):
        runtime.install(self.root, self.bundle, self.digest)

    def test_install_is_repeatable_and_preserves_operator_files(self):
        self.install()
        self.install()
        self.assertEqual((self.root / 'active-bundle').resolve(), self.root / 'bundles' / self.digest)
        for name, original in self.original.items():
            self.assertTrue((self.root / name).read_bytes() == original)

    def test_bridge_cannot_set_identity_rpc_trust_pins_or_rotation_permissions(self):
        env = self.bundle / 'signer-policy.env'
        before = env.read_text()
        for field in ['ATTESTATION_SIGNER_BACKEND', 'ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT', 'ATTESTATION_SIGNER_ALLOWED_NEXT_BRIDGE_SCRIPT_HASHES', 'ATTESTATION_SIGNER_ADVANCE_L1_TERMINAL_ANCHOR_SOURCES_JSON', 'AWS_ACCESS_KEY_ID']:
            env.write_text(before + f'{field}=TEST_ONLY\n')
            self.digest = self.manifest()
            with self.assertRaisesRegex(ValueError, 'non-bridge fields'):
                self.install()
            self.assertFalse((self.root / 'active-bundle').exists())
            for name, original in self.original.items():
                self.assertTrue((self.root / name).read_bytes() == original)

    def test_tampering_does_not_replace_active_bundle(self):
        self.install()
        active = (self.root / 'active-bundle').readlink()
        (self.bundle / 'protocol_context.json').write_text('tampered')
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual((self.root / 'active-bundle').readlink(), active)
        self.digest = self.manifest()
        with self.assertRaisesRegex(ValueError, 'Context does not match'):
            self.install()
        self.assertEqual((self.root / 'active-bundle').readlink(), active)

    def test_no_symlink_or_identity_substitution(self):
        target = self.bundle / 'protocol_context.json'
        target.unlink()
        target.symlink_to(self.root / 'operator.env')
        with self.assertRaises(ValueError):
            self.install()

    def test_unapproved_future_rotations_do_not_block_normal_readiness(self):
        report = {'contract': 'attestation_evidence_v2', 'network': 'testnet', 'public_key': self.identity['publicKey'], 'policy_mode': 'enforce', 'production_v2_ready': False, 'v2_capabilities': [{'capability': name, 'production_serving': serving} for name, serving in [('advance_l1', True), ('advance_l2', True), ('rotate_key', False), ('rotate_sequencer_signer', False)]]}
        self.assertTrue(runtime.check_report(self.identity, report)['advanceL2'])
        for field, value in [('public_key', 'wrong'), ('network', 'mainnet'), ('policy_mode', 'observe')]:
            with self.assertRaises(ValueError):
                runtime.check_report(self.identity, {**report, field: value})
        report['v2_capabilities'][1]['production_serving'] = False
        with self.assertRaisesRegex(ValueError, 'advance_l2'):
            runtime.check_report(self.identity, report)

    def test_rpc_json_overrides_are_rejected_even_if_empty_without_echoing_values(self):
        for field in runtime.SOURCE_ENV_OVERRIDES:
            for value in ['', 'PRIVATE_VALUE_SENTINEL']:
                with self.assertRaises(ValueError) as ctx:
                    runtime.reject_rpc_overrides({field: value})
                self.assertIn(field, str(ctx.exception))
                self.assertNotIn('PRIVATE_VALUE_SENTINEL', str(ctx.exception))
        runtime.reject_rpc_overrides({'ATTESTATION_SIGNER_POLICY_MODE': 'enforce'})

    def test_rpc_file_is_private_complete_and_not_shadowed_by_legacy_env(self):
        config = self.root / 'attestation-signer.toml'
        template = (Path(__file__).parents[1] / 'attestation-signer.toml').read_text()
        config.write_text(template)
        config.chmod(0o600)
        (self.root / 'operator.env').unlink()
        with self.assertRaisesRegex(ValueError, 'placeholders'):
            runtime.validate_rpc_config(self.root)
        config.write_text(template.replace('.example.invalid', '.test'))
        runtime.validate_rpc_config(self.root)
        config.chmod(0o644)
        with self.assertRaisesRegex(ValueError, '0600'):
            runtime.validate_rpc_config(self.root)
        config.chmod(0o600)
        (self.root / 'operator.env').write_text('LEGACY=PRIVATE_VALUE_SENTINEL')
        with self.assertRaisesRegex(ValueError, 'legacy operator.env'):
            runtime.validate_rpc_config(self.root)
