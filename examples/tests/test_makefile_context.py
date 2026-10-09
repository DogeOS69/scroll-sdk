"""Check expanded recipes without invoking Helm, kubectl, or any cluster."""
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest


MAKEFILE = pathlib.Path(__file__).resolve().parents[1] / 'Makefile.example'


class MakefileContextTests(unittest.TestCase):
    def expanded_commands(self, context, namespace, override=None, targets=None, files=()):
        source = MAKEFILE.read_text().replace('KUBE_CONTEXT ?=\n', f'KUBE_CONTEXT ?= {context}\n')
        source = source.replace('NAMESPACE ?= default\n', f'NAMESPACE ?= {namespace}\n')
        if targets is None:
            targets = re.findall(r'^([a-z][a-z0-9-]*):', source, re.MULTILINE)
        with tempfile.TemporaryDirectory(prefix='make-context-test-') as directory:
            for filename in files:
                fixture = pathlib.Path(directory) / filename
                fixture.parent.mkdir(parents=True, exist_ok=True)
                fixture.write_text('{}\n')
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

    def assert_context(self, commands, context, namespace, dstack_namespace='dstack-system'):
        self.assertGreater(len(commands), 50)
        for command in commands:
            if command[:2] == ['helm', 'repo']:
                continue  # Repository metadata operations do not target a cluster.
            with self.subTest(command=command[:5]):
                flag = '--kube-context' if command[0] == 'helm' else '--context'
                self.assertEqual(command.count(flag), 1)
                self.assertEqual(command[command.index(flag) + 1], context)
                expected_namespace = dstack_namespace if 'dstack-controller' in command else namespace
                self.assertEqual(command[command.index('-n') + 1], expected_namespace)

    def test_header_context_and_namespace_reach_all_cluster_commands(self):
        self.assert_context(self.expanded_commands('header-cluster', 'header-ns'),
                            'header-cluster', 'header-ns')

    def test_command_line_overrides_reach_recursive_targets(self):
        overrides = {'KUBE_CONTEXT': 'arn:aws:eks:us-east-1:123456789012:cluster/selected',
                     'NAMESPACE': 'selected-ns', 'DSTACK_NAMESPACE': 'selected-gpu-ns'}
        self.assert_context(self.expanded_commands('header-cluster', 'header-ns', overrides),
                            overrides['KUBE_CONTEXT'], overrides['NAMESPACE'], overrides['DSTACK_NAMESPACE'])

    def test_empty_context_is_an_empty_argument_not_the_next_option(self):
        self.assert_context(self.expanded_commands('', 'default'), '', 'default')

    def test_dstack_install_accepts_chart_and_values_overrides(self):
        commands = self.expanded_commands('selected', 'chain', {
            'DSTACK_NAMESPACE': 'gpu-system',
            'DSTACK_CONTROLLER_CHART': './charts/dstack-controller',
            'DSTACK_CONTROLLER_CHART_VERSION': '0.1.2',
            'DSTACK_CONTROLLER_VALUES': 'custom values/dstack.yaml',
        }, targets=['install-dstack-controller'])
        self.assertEqual(commands, [[
            'helm', '--kube-context', 'selected', 'upgrade', '-i', 'dstack-controller',
            './charts/dstack-controller', '-n', 'gpu-system', '--create-namespace',
            '--version', '0.1.2', '--values', 'custom values/dstack.yaml',
        ]])

    def test_monitor_applies_generated_dstack_overlay_after_base_values(self):
        overlay = 'values/scroll-monitor-dstack.yaml'
        for targets in [['install-scroll-monitor'], ['install-all']]:
            for present in [False, True]:
                with self.subTest(targets=targets, present=present):
                    commands = self.expanded_commands('selected', 'chain', targets=targets,
                                                      files=[overlay] if present else [])
                    monitor = next(command for command in commands if 'scroll-monitor' in command)
                    values = [monitor[i + 1] for i, arg in enumerate(monitor) if arg == '--values']
                    self.assertEqual(values, ['values/scroll-monitor-production.yaml']
                                     + ([overlay] if present else []))
                    self.assertFalse(any('dstack-controller' in command for command in commands))

    def test_monitor_accepts_an_explicit_overlay_or_disables_auto_loading(self):
        for overlay in ['custom values/dstack.yaml', '']:
            commands = self.expanded_commands('selected', 'chain', {
                'SCROLL_MONITOR_DSTACK_VALUES': overlay,
            }, targets=['install-scroll-monitor'], files=['values/scroll-monitor-dstack.yaml'])
            monitor = commands[0]
            values = [monitor[i + 1] for i, arg in enumerate(monitor) if arg == '--values']
            self.assertEqual(values, ['values/scroll-monitor-production.yaml']
                             + ([overlay] if overlay else []))

    def test_fresh_genesis_does_not_require_unshipped_upgrade_files(self):
        commands = self.expanded_commands('', 'default')
        self.assertFalse(any('normalize-reth-genesis' in arg
                             for command in commands for arg in command))

    def test_reviewed_upgrade_can_explicitly_supply_both_normalizer_files(self):
        commands = self.expanded_commands('', 'default', {
            'L2_RETH_GENESIS_NORMALIZER_VALUES': 'upgrade/normalizer.yaml',
            'L2_RETH_GENESIS_NORMALIZER_SCRIPT': 'upgrade/normalize.sh',
        })
        reth = [command for command in commands
                if any(arg.startswith('l2-reth-') for arg in command)
                and 'upgrade' in command]
        self.assertTrue(reth)
        for command in reth:
            self.assertIn('upgrade/normalizer.yaml', command)
            self.assertIn('configMaps.reth-genesis-normalizer.data.normalize-reth-genesis=upgrade/normalize.sh', command)


if __name__ == '__main__':
    unittest.main()
