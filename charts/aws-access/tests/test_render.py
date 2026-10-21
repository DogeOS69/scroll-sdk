import pathlib
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
CHART = ROOT / 'charts/aws-access'


class AwsAccessTest(unittest.TestCase):
    def render(self, accounts):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as values:
            yaml.safe_dump({'serviceAccounts': accounts}, values)
            values.flush()
            return subprocess.run(['helm', 'template', 'aws-access', str(CHART),
                                   '--namespace', 'fixture', '-f', values.name],
                                  capture_output=True, text=True)

    def test_separate_reader_identities_and_no_secret_values(self):
        accounts = [{'name': 'aws-reader-' + service,
                     'roleArn': 'arn:aws:iam::000000000000:role/fixture-' + service}
                    for service in ['proof-coordinator', 'withdrawal-processor']]
        result = self.render(accounts)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = list(yaml.safe_load_all(result.stdout))
        self.assertEqual(len(docs), 2)
        for doc, account in zip(docs, accounts):
            self.assertEqual(doc['kind'], 'ServiceAccount')
            self.assertEqual(doc['metadata']['namespace'], 'fixture')
            self.assertEqual(doc['metadata']['name'], account['name'])
            self.assertEqual(doc['metadata']['annotations']['eks.amazonaws.com/role-arn'], account['roleArn'])
            self.assertFalse(doc['automountServiceAccountToken'])

    def test_duplicate_identity_is_rejected(self):
        account = {'name': 'aws-reader-fixture', 'roleArn': 'arn:aws:iam::000000000000:role/fixture'}
        self.assertNotEqual(self.render([account, account]).returncode, 0)

    def test_empty_values_create_no_resources(self):
        self.assertFalse(self.render([]).stdout.strip())

    def test_install_prerequisite_is_optional_and_pins_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'Makefile').write_text((ROOT / 'examples/Makefile.example').read_text())
            command = ['make', '-n', 'install-fee-oracle', 'KUBE_CONTEXT=fixture-context', 'NAMESPACE=fixture']
            before = subprocess.check_output(command, cwd=root, text=True)
            self.assertNotIn('upgrade -i aws-access', before)
            (root / 'values').mkdir()
            (root / 'values/aws-access-production.yaml').write_text('serviceAccounts: []\n')
            after = subprocess.check_output(command, cwd=root, text=True)
            self.assertLess(after.index('upgrade -i aws-access'), after.index('upgrade -i fee-oracle'))
            self.assertIn('kubectl --context "fixture-context" get crd', after)
            self.assertIn('--kube-context "fixture-context" upgrade -i aws-access', after)


if __name__ == '__main__':
    unittest.main()
