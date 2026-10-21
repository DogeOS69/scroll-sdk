import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class SharedAwsIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'Makefile').write_text((ROOT / 'examples/Makefile.example').read_text())

    def manifest(self):
        (self.root / 'manifests').mkdir()
        (self.root / 'manifests/aws-secret-reader.yaml').write_text(
            'apiVersion: v1\nkind: ServiceAccount\nmetadata:\n  name: external-secrets\n  namespace: fixture\n')

    def make(self, *args):
        return subprocess.run(['make', '-n', *args, 'KUBE_CONTEXT=fixture-context', 'NAMESPACE=fixture'],
                              cwd=self.root, capture_output=True, text=True)

    def test_optional_prerequisite_precedes_services_without_chart(self):
        before = self.make('install-fee-oracle')
        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertNotIn('apply --server-side', before.stdout)
        self.manifest()
        for target in ['install-fee-oracle', 'install-proof-coordinator',
                       'install-withdrawal-processor', 'install-frontends', 'install-tso']:
            after = self.make(target)
            self.assertEqual(after.returncode, 0, after.stderr)
            self.assertLess(after.stdout.index('apply --server-side'), after.stdout.index('upgrade -i'))
            self.assertIn('--context "fixture-context" apply', after.stdout)
            self.assertIn('-n "fixture" -f "manifests/aws-secret-reader.yaml"', after.stdout)
            self.assertNotIn('helm/aws-access', after.stdout)
            self.assertNotIn('--force-conflicts', after.stdout)

    def test_shared_prerequisite_runs_once_for_multiple_targets(self):
        self.manifest()
        result = self.make('install-fee-oracle', 'install-proof-coordinator')
        self.assertEqual(result.stdout.count('apply --server-side'), 1)

    def test_install_failure_stops_service_installation(self):
        self.manifest()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        # No real cluster commands. Simulate a conflicting ServiceAccount field.
        (bin_dir / 'kubectl').write_text('#!/bin/sh\ncase "$*" in *apply*) exit 1;; esac\n')
        (bin_dir / 'helm').write_text('#!/bin/sh\ntouch helm-was-run\n')
        for executable in bin_dir.iterdir():
            executable.chmod(0o700)
        result = subprocess.run(['make', 'install-fee-oracle', 'KUBE_CONTEXT=fixture', 'NAMESPACE=fixture'],
                                cwd=self.root, env={**os.environ, 'PATH': str(bin_dir) + ':' + os.environ['PATH']},
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'helm-was-run').exists())


if __name__ == '__main__':
    unittest.main()
