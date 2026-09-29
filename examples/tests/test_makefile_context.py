"""Check expanded recipes without invoking Helm, kubectl, or any cluster."""
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest


MAKEFILE = pathlib.Path(__file__).resolve().parents[1] / 'Makefile.example'


class MakefileContextTests(unittest.TestCase):
    def expanded_commands(self, context, namespace, override=None):
        source = MAKEFILE.read_text().replace('KUBE_CONTEXT ?=\n', f'KUBE_CONTEXT ?= {context}\n')
        source = source.replace('NAMESPACE ?= default\n', f'NAMESPACE ?= {namespace}\n')
        targets = re.findall(r'^([a-z][a-z0-9-]*):', source, re.MULTILINE)
        with tempfile.TemporaryDirectory(prefix='make-context-test-') as directory:
            makefile = pathlib.Path(directory) / 'Makefile'
            makefile.write_text(source)
            args = ['make', '--no-print-directory', '-n', '-f', str(makefile)]
            if override:
                args += [f'{key}={value}' for key, value in override.items()]
            result = subprocess.run(args + targets, cwd=directory, text=True,
                                    capture_output=True, check=True)
        # Join continued recipe lines before parsing; nested make output is included.
        expanded = re.sub(r'\\\n\s*', ' ', result.stdout)
        return [shlex.split(line) for line in expanded.splitlines()
                if line.startswith(('helm ', 'kubectl '))]

    def assert_context(self, commands, context, namespace):
        self.assertGreater(len(commands), 50)
        for command in commands:
            if command[:2] == ['helm', 'repo']:
                continue  # Repository metadata operations do not target a cluster.
            with self.subTest(command=command[:5]):
                flag = '--kube-context' if command[0] == 'helm' else '--context'
                self.assertEqual(command.count(flag), 1)
                self.assertEqual(command[command.index(flag) + 1], context)
                self.assertEqual(command[command.index('-n') + 1], namespace)

    def test_header_context_and_namespace_reach_all_cluster_commands(self):
        self.assert_context(self.expanded_commands('header-cluster', 'header-ns'),
                            'header-cluster', 'header-ns')

    def test_command_line_overrides_reach_recursive_targets(self):
        overrides = {'KUBE_CONTEXT': 'arn:aws:eks:us-east-1:123456789012:cluster/selected',
                     'NAMESPACE': 'selected-ns'}
        self.assert_context(self.expanded_commands('header-cluster', 'header-ns', overrides),
                            overrides['KUBE_CONTEXT'], overrides['NAMESPACE'])

    def test_empty_context_is_an_empty_argument_not_the_next_option(self):
        self.assert_context(self.expanded_commands('', 'default'), '', 'default')


if __name__ == '__main__':
    unittest.main()
