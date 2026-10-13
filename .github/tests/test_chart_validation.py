"""Keep chart-sync validation aligned with the standalone signer handoff."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from validate_charts import validate_attestation_signer_partner_kit


class PartnerKitValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.kit = self.directory / "partner-kit/attestation-signer"
        shutil.copytree(ROOT / "partner-kit/attestation-signer", self.kit)
        previous = Path.cwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)

    def validate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return validate_attestation_signer_partner_kit()

    def test_current_standalone_kit_passes_without_legacy_compose(self):
        shutil.rmtree(self.kit / "docker-compose")
        self.assertTrue(self.validate())

    def test_legacy_kit_cannot_hide_missing_standalone_entrypoint(self):
        (self.kit / "signer.sh").unlink()
        self.assertFalse(self.validate())

    def test_old_cli_instructions_cannot_replace_standalone_instructions(self):
        (self.kit / "README.md").write_text(
            "scrollsdk signer init\nscrollsdk signer preflight\n"
            "docker compose --project-directory docker-compose\n"
            "signer-policy-bundle/PARTNER-COMMANDS.md\n"
        )
        self.assertFalse(self.validate())

    def test_bridge_policy_cannot_override_operator_environment(self):
        path = self.kit / "docker-compose.yml"
        compose = yaml.safe_load(path.read_text())
        compose["services"]["attestation-signer"]["env_file"].reverse()
        path.write_text(yaml.safe_dump(compose))
        self.assertFalse(self.validate())

    def test_writable_bundle_mount_is_rejected(self):
        path = self.kit / "docker-compose.yml"
        path.write_text(path.read_text().replace(
            "./active-bundle:/etc/dogeos:ro", "./active-bundle:/etc/dogeos:rw"
        ))
        self.assertFalse(self.validate())


if __name__ == "__main__":
    unittest.main()
