"""Execute the partner scripts with disposable transport keys."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "partner-kit/attestation-signer/scripts"
PHASE_A, PHASE_B = "phase-a.sh", "phase-b.sh"


class PartnerTransportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="partner-transport-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        shutil.copytree(SCRIPTS, self.root / "scripts")
        for name in ("signer-partner-a", "docker-compose", "signer-policy-bundle", "bin"):
            (self.root / name).mkdir()
        self.source = self.root / "signer-partner-a/transport.key"
        self.runtime = self.root / "docker-compose/transport.key"
        self.descriptor = self.root / "signer-partner-a/descriptor.json"
        self.log = self.root / "calls.log"
        self.generate_key()
        self.original = self.source.read_bytes()
        self.runtime.write_bytes(self.original)
        self.runtime.chmod(0o600)
        for name in ("attestation-signer.env", "attestation-signer.toml"):
            (self.source.parent / name).write_text("# test placeholder\n")
        for name in ("signer-policy.env", "protocol_context.json"):
            (self.root / "signer-policy-bundle" / name).write_text("{}\n")
        for name in ("docker", "scrollsdk"):
            stub = self.root / "bin" / name
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS_LOG"\n')
            stub.chmod(0o755)

    def generate_key(self):
        # No fixed signing material in fixtures or private-key output in logs.
        subprocess.run(["node", "--input-type=commonjs", "-e", """
const fs = require('node:fs');
const key = require('node:crypto').createECDH('secp256k1');
key.generateKeys();
fs.writeFileSync(process.argv[1], key.getPrivateKey('hex').padStart(64, '0') + '\\n', {mode: 0o600});
fs.writeFileSync(process.argv[2], JSON.stringify({transportPubkey: key.getPublicKey('hex', 'compressed')}));
""", str(self.source), str(self.descriptor)], check=True, capture_output=True)

    def run_phase(self, phase=PHASE_B, preflight_flags=None):
        env = dict(os.environ)
        env.pop("PREFLIGHT_FLAGS", None)
        if preflight_flags is not None:
            env["PREFLIGHT_FLAGS"] = preflight_flags
        return subprocess.run(["bash", str(self.root / "scripts" / phase)], cwd=self.root.parent, capture_output=True,
                              env={**env, "SIGNER_ID": "partner-a", "DOGE_NETWORK": "testnet",
                                   "CALLS_LOG": str(self.log),
                                   "PATH": f"{self.root / 'bin'}{os.pathsep}{os.environ['PATH']}"})

    def assert_stopped(self, phase=PHASE_B):
        self.assertNotEqual(self.run_phase(phase).returncode, 0)
        self.assertTrue(self.runtime.read_bytes() == self.original, "Runtime key changed")
        self.assertFalse(self.log.exists(), "A later Docker or CLI step ran")
        self.assertFalse((self.root / "docker-compose/policy").exists())

    def test_missing_source_preserves_runtime_and_never_generates(self):
        self.source.unlink()
        self.assert_stopped()
        self.assert_stopped(PHASE_A)
        self.assertFalse(self.source.exists())

    def test_missing_descriptor_stops_install(self):
        self.descriptor.unlink()
        self.assert_stopped()

    def test_mismatched_key_stops_both_phases(self):
        registered = self.descriptor.read_bytes()
        self.generate_key()
        self.descriptor.write_bytes(registered)
        self.assert_stopped()
        self.assert_stopped(PHASE_A)

    def test_malformed_descriptor_stops_install(self):
        self.descriptor.write_text("{")
        self.assert_stopped()

    def test_missing_transport_pubkey_stops_install(self):
        self.descriptor.write_text(json.dumps({"id": "partner-a"}))
        self.assert_stopped()

    def test_corrupt_key_stops_install(self):
        self.source.write_bytes(self.original + b"garbage\n")
        self.assert_stopped()

    def test_invalid_scalar_stops_install(self):
        self.source.write_text("00" * 32 + "\n")
        self.assert_stopped()

    def test_matching_key_installs_and_reruns_without_rotation(self):
        self.runtime.unlink()
        for _ in range(2):
            self.assertEqual(self.run_phase().returncode, 0)
            self.assertTrue(self.runtime.read_bytes() == self.original, "Runtime key changed")
            self.assertEqual(self.runtime.stat().st_mode & 0o777, 0o600)
        self.assertIn("up -d", self.log.read_text())
        self.assertIn("signer preflight", self.log.read_text())

    def test_production_preflight_is_the_default(self):
        self.assertEqual(self.run_phase().returncode, 0)
        self.assertIn("--require-production-ready", self.log.read_text())

    def test_observe_preflight_requires_an_explicit_empty_override(self):
        self.assertEqual(self.run_phase(preflight_flags="").returncode, 0)
        self.assertIn("signer preflight", self.log.read_text())
        self.assertNotIn("--require-production-ready", self.log.read_text())

    def test_bundle_verification_checks_manifest_files_and_descriptor(self):
        bundle = self.root / "signer-policy-bundle"
        descriptor = {**json.loads(self.descriptor.read_text()), "id": "partner-a",
                      "network": "testnet", "publicKey": "PUBLIC_KEY_PLACEHOLDER"}
        self.descriptor.write_text(json.dumps(descriptor))
        policy = bundle / "signer-policy.json"
        policy.write_text(json.dumps({"contract": "attestation_evidence_v2",
                                     "network": "testnet", "signers": [descriptor]}))
        manifest = bundle / "signer-policy-manifest.json"
        manifest.write_text(json.dumps({"files": [{"file": policy.name,
                            "sha256": "sha256:" + hashlib.sha256(policy.read_bytes()).hexdigest()}]}))
        expected = hashlib.sha256(manifest.read_bytes()).hexdigest()

        def verify(digest=expected):
            return subprocess.run(["bash", str(self.root / "scripts/verify-bundle.sh")],
                                  cwd=self.root.parent, capture_output=True,
                                  env={**os.environ, "SIGNER_ID": "partner-a",
                                       "EXPECTED_MANIFEST_SHA256": digest}).returncode

        self.assertEqual(verify(), 0)
        self.assertNotEqual(verify("00" * 32), 0)
        self.assertNotEqual(verify("invalid"), 0)
        descriptor["transportPubkey"] = "DIFFERENT_PUBLIC_KEY_PLACEHOLDER"
        self.descriptor.write_text(json.dumps(descriptor))
        self.assertNotEqual(verify(), 0)
        policy.write_text("{}")
        self.assertNotEqual(verify(), 0)


if __name__ == "__main__":
    unittest.main()
