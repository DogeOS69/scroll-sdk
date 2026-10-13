"""Operator boundaries: untrusted deployment-kit import, start re-verification and capability-specific readiness."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('runtime', Path(__file__).parents[1] / 'scripts/runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


FIXTURE = Path(__file__).parent / 'fixtures/deployment-kit-1'
# sha256 of the fixture manifest, as printed by `scrollsdk setup export-deployment-kit`.
FIXTURE_DIGEST = 'f2faedcb513a339a29355c1e39fffa20fad28097f328bebfd234661b696a3fec'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'operator'
        self.root.mkdir()
        self.bundle = Path(tmp.name) / 'received'
        shutil.copytree(FIXTURE, self.bundle)
        self.identity = {'schema': 'dogeos/attestation-signer-descriptor/v1', 'network': 'testnet', 'publicKey': 'test-public-key', 'transportPubkey': 'test-transport-key'}
        (self.root / 'identity.json').write_text(json.dumps(self.identity))
        for name in ['attestation-signer.env', 'transport.key', 'attestation-signer.toml', 'operator.env']:
            (self.root / name).write_text('private operator-owned fixture')
        self.original = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.digest = FIXTURE_DIGEST

    def manifest(self, extra=()):
        """Re-sign a modified kit the way the CLI does; returns the new authenticated digest."""
        names = sorted(p.name for p in self.bundle.iterdir() if p.name != 'deployment-kit-manifest.json')
        files = [{'file': n, 'sha256': 'sha256:' + hashlib.sha256((self.bundle / n).read_bytes()).hexdigest(), 'sizeBytes': (self.bundle / n).stat().st_size} for n in names]
        raw = (json.dumps({'files': files + list(extra), 'schema': 'dogeos/deployment-kit-manifest/v1'}, indent=2) + '\n').encode()
        (self.bundle / 'deployment-kit-manifest.json').write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def install(self):
        runtime.install(self.root, self.bundle, self.digest)

    def assert_operator_files_unchanged(self):
        for name, original in self.original.items():
            self.assertTrue((self.root / name).read_bytes() == original, name)

    def assert_rejected(self, message):
        with self.assertRaisesRegex(ValueError, message):
            self.install()
        self.assertFalse((self.root / 'active-bundle').exists())
        self.assert_operator_files_unchanged()

    def test_fixture_is_the_cli_kit_and_its_manifest_is_the_identity(self):
        self.assertEqual(self.manifest(), FIXTURE_DIGEST)

    def test_import_and_start_verification_are_repeatable_and_preserve_operator_files(self):
        self.install()
        self.install()
        self.assertEqual((self.root / 'active-bundle').resolve(), self.root / 'bundles' / self.digest)
        runtime.verify_active(self.root)
        self.assert_operator_files_unchanged()

    def test_bridge_cannot_set_identity_rpc_trust_pins_or_rotation_permissions(self):
        env = self.bundle / 'deployment-kit.env'
        before = env.read_text()
        for field in ['ATTESTATION_SIGNER_BACKEND', 'ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT', 'ATTESTATION_SIGNER_ALLOWED_NEXT_BRIDGE_SCRIPT_HASHES', 'ATTESTATION_SIGNER_ADVANCE_L1_TERMINAL_ANCHOR_SOURCES_JSON', 'AWS_ACCESS_KEY_ID']:
            env.write_text(before + f'{field}=TEST_ONLY\n')
            self.digest = self.manifest()
            self.assert_rejected('non-bridge fields')

    def test_tampered_file_is_rejected_at_import_without_replacing_the_active_kit(self):
        self.install()
        active = (self.root / 'active-bundle').readlink()
        (self.bundle / 'protocol_context.json').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.install()
        self.assertEqual((self.root / 'active-bundle').readlink(), active)
        self.digest = self.manifest()
        with self.assertRaisesRegex(ValueError, 'Context does not match'):
            self.install()
        self.assertEqual((self.root / 'active-bundle').readlink(), active)

    def test_tampered_or_extra_active_kit_file_is_rejected_at_start(self):
        self.install()
        installed = self.root / 'bundles' / self.digest
        context = installed / 'protocol_context.json'
        original = context.read_bytes()
        context.write_bytes(original + b' ')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            runtime.prestart(self.root, {'services': {'attestation-signer': {}}})
        context.write_bytes(original)
        runtime.verify_active(self.root)
        (installed / 'extra.env').write_text('ATTESTATION_SIGNER_ALLOWED_NEXT_BRIDGE_SCRIPT_HASHES=0x00\n')
        with self.assertRaisesRegex(ValueError, 'unlisted'):
            runtime.verify_active(self.root)

    def test_old_bundle_format_must_be_reimported_before_start(self):
        old = self.root / 'bundles' / ('a' * 64)
        old.mkdir(parents=True)
        (old / 'signer-policy-manifest.json').write_text('{}')
        (self.root / 'active-bundle').symlink_to(Path('bundles') / ('a' * 64), target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'deployment-kit-manifest.json'):
            runtime.verify_active(self.root)

    def test_operator_env_cannot_override_kit_fields_at_start(self):
        self.install()
        kit_env = runtime.env_values((self.root / 'active-bundle' / 'deployment-kit.env').read_bytes())
        compose = {'services': {'attestation-signer': {'environment': dict(kit_env)}}}
        config = self.root / 'attestation-signer.toml'
        config.write_text((Path(__file__).parents[1] / 'attestation-signer.toml').read_text().replace('.example.invalid', '.test'))
        config.chmod(0o600)
        (self.root / 'operator.env').unlink()
        runtime.prestart(self.root, compose)
        for field, value in [('ATTESTATION_SIGNER_POLICY_MODE', 'observe'), ('ATTESTATION_SIGNER_TSO_URL', 'https://tso.attacker.test')]:
            with self.assertRaisesRegex(ValueError, field):
                runtime.prestart(self.root, {'services': {'attestation-signer': {'environment': {**kit_env, field: value}}}})

    def test_kit_contract_fields_and_core_identity_are_required(self):
        kit = json.loads((self.bundle / 'deployment-kit.json').read_text())
        for change, message in [({'kit_version': '../1'}, 'kit version'), ({'deployment': {}}, 'deployment generation')]:
            (self.bundle / 'deployment-kit.json').write_text(json.dumps({**kit, **change}))
            self.digest = self.manifest()
            self.assert_rejected(message)
        (self.bundle / 'deployment-kit.json').write_text(json.dumps(kit))
        self.digest = self.manifest()
        self.original['identity.json'] = json.dumps({**self.identity, 'schema': 'other'}).encode()
        (self.root / 'identity.json').write_bytes(self.original['identity.json'])
        self.assert_rejected('print-identity')

    def test_missing_verifier_is_rejected(self):
        (self.bundle / 'advance-l2-agg-verifying-key.bin').unlink()
        self.digest = self.manifest()
        self.assert_rejected('Incomplete deployment kit')

    def test_missing_required_file_is_rejected(self):
        (self.bundle / 'deployment-kit.env').unlink()
        self.digest = self.manifest()
        self.assert_rejected('Incomplete deployment kit')

    def test_kit_for_another_network_is_rejected(self):
        self.original['identity.json'] = json.dumps({**self.identity, 'network': 'mainnet'}).encode()
        (self.root / 'identity.json').write_bytes(self.original['identity.json'])
        self.assert_rejected('another network')

    def test_duplicate_filename_is_rejected(self):
        entry = {'file': 'deployment-kit.env', 'sha256': 'sha256:' + hashlib.sha256((self.bundle / 'deployment-kit.env').read_bytes()).hexdigest(), 'sizeBytes': (self.bundle / 'deployment-kit.env').stat().st_size}
        self.digest = self.manifest(extra=[entry])
        self.assert_rejected('Duplicate kit file')

    def test_observe_kit_is_rejected(self):
        kit = json.loads((self.bundle / 'deployment-kit.json').read_text())
        (self.bundle / 'deployment-kit.json').write_text(json.dumps({**kit, 'policy_mode': 'observe'}))
        self.digest = self.manifest()
        self.assert_rejected('enforce')

    def test_no_symlink_substitution(self):
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
