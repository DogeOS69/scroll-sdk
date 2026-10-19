"""Check expanded recipes and stubbed installation ordering without a cluster."""
import os
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

    def test_reth_installs_use_the_bundled_chart_version(self):
        chart = MAKEFILE.parent.parent / 'charts/l2-reth/Chart.yaml'
        version = re.search(r'^version:\s*(\S+)', chart.read_text(), re.MULTILINE)[1]
        commands = self.expanded_commands('selected', 'chain', targets=[
            'install-l2-reth-bootnode', 'install-l2-reth-rpc', 'install-l2-reth-sequencer',
        ])
        self.assertTrue(commands)
        for command in commands:
            self.assertEqual(command[command.index('--version') + 1], version)

    def test_preinstalls_runs_before_contracts_and_waits_for_the_hook(self):
        commands = self.expanded_commands('selected', 'chain', targets=['install-chain-contracts'])
        preinstalls = next(command for command in commands if 'preinstalls' in command)
        contracts = next(command for command in commands if 'contracts' in command)
        self.assertLess(commands.index(preinstalls), commands.index(contracts))
        self.assertIn('values/preinstalls-production.yaml', preinstalls)
        self.assertEqual(preinstalls[preinstalls.index('--timeout') + 1], '20m')
        self.assertNotIn('--no-hooks', preinstalls)
        # Each recursive make is a separate recipe: failure must stop chain deployment.
        source = MAKEFILE.read_text()
        self.assertIn('\t$(MAKE) -f $(firstword $(MAKEFILE_LIST)) install-preinstalls\n'
                      '\t$(MAKE) -f $(firstword $(MAKEFILE_LIST)) install-contracts\n', source)

    def test_application_install_excludes_independent_optional_and_chain_actions(self):
        commands = self.expanded_commands('selected', 'chain', targets=['install-scroll-core', 'reconcile-proof-services', 'install-frontends'])
        releases = [c[c.index('-i') + 1] for c in commands if 'upgrade' in c]
        for excluded in ['dogecoin-testnet', 'blockbook-testnet', 'preinstalls', 'contracts', 'testnet-activity-helper', 'blockscout']:
            self.assertNotIn(excluded, releases)
        self.assertLess(releases.index('scroll-monitor'), releases.index('l1-interface'))
        self.assertLess(releases.index('tso-service'), releases.index('withdrawal-processor'))
        self.assertEqual(releases.count('eth-da-submitter'), 1)
        self.assertFalse(any('run' in c for c in commands))
        source = MAKEFILE.read_text()
        self.assertNotIn('fund-accounts', source)
        self.assertNotIn('dogecoin-wallet-import', source)
        self.assertNotRegex(source, r'(?m)^(install|delete)-(dogecoin|blockbook):')

    def test_metrics_exporter_is_independently_installable(self):
        commands = self.expanded_commands('selected', 'chain', targets=['install-metrics-exporter'])
        self.assertEqual(len(commands), 1)
        self.assertIn('metrics-exporter', commands[0])
        self.assertIn('values/metrics-exporter-production.yaml', commands[0])

    def test_preinstalls_chart_can_be_validated_locally(self):
        commands = self.expanded_commands('selected', 'chain', {
            'PREINSTALLS_CHART': './charts/preinstalls-deployer',
            'PREINSTALLS_CHART_VERSION': '0.1.2-dogeos',
            'PREINSTALLS_TIMEOUT': '30m',
        }, targets=['install-preinstalls'])
        self.assertEqual(commands, [[
            'helm', '--kube-context', 'selected', 'upgrade', '-i', 'preinstalls',
            './charts/preinstalls-deployer', '-n', 'chain', '--version=0.1.2-dogeos',
            '--timeout', '30m', '--values', 'values/preinstalls-production.yaml',
        ]])

    def test_dstack_install_accepts_chart_and_values_overrides(self):
        commands = self.expanded_commands('selected', 'chain', {
            'DSTACK_CONTROLLER_CHART': './charts/dstack-controller',
            'DSTACK_CONTROLLER_CHART_VERSION': '0.1.2',
            'DSTACK_CONTROLLER_VALUES': 'custom values/dstack.yaml',
        }, targets=['install-dstack-controller'])
        self.assertEqual(commands, [[
            'helm', '--kube-context', 'selected', 'upgrade', '-i', 'dstack-controller',
            './charts/dstack-controller', '-n', 'chain', '--create-namespace',
            '--version', '0.1.2', '--values', 'custom values/dstack.yaml',
        ]])

    def test_capacity_preflight_runs_before_helm_and_failure_stops_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            log = root / 'calls'
            for name in ['scrollsdk', 'helm']:
                tool = root / name
                tool.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + ' $*" >> "$CALL_LOG"\n'
                                + ('exit "$PREFLIGHT_EXIT"\n' if name == 'scrollsdk' else 'exit 0\n'))
                tool.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                       CALL_LOG=str(log), PREFLIGHT_EXIT='1')
            command = ['make', '--no-print-directory', '-f', str(MAKEFILE),
                       'install-capacity-manager', 'KUBE_CONTEXT=selected', 'NAMESPACE=chain']
            failed = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(len(log.read_text().splitlines()), 1)
            self.assertIn('--dir . --kube-context selected --namespace chain', log.read_text())
            log.unlink()
            env['PREFLIGHT_EXIT'] = '0'
            succeeded = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(succeeded.returncode, 0, succeeded.stderr)
            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[0].startswith('scrollsdk setup capacity-manager credentials'))
            self.assertTrue(calls[1].startswith('helm --kube-context selected'))

    def test_signer_activation_guard_stops_before_helm_and_uses_the_same_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            log = root / 'calls'
            for name in ['scrollsdk', 'helm']:
                tool = root / name
                tool.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + ' $*" >> "$CALL_LOG"\n'
                                + ('exit "$ACTIVATION_EXIT"\n' if name == 'scrollsdk' else 'exit 0\n'))
                tool.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                       CALL_LOG=str(log), ACTIVATION_EXIT='2')
            command = ['make', '--no-print-directory', '-f', str(MAKEFILE),
                       'install-cubesigner-signer', 'KUBE_CONTEXT=selected', 'NAMESPACE=chain']
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(log.read_text().splitlines()), 1)
            self.assertIn('verify-activation --dir . --kube-context selected', log.read_text())
            self.assertIn('--namespace chain', log.read_text())
            log.unlink()
            env['ACTIVATION_EXIT'] = '0'
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[0].startswith('scrollsdk setup cubesigner-policy verify-activation'))
            self.assertTrue(calls[1].startswith('helm --kube-context selected'))
            for call in calls:
                self.assertIn('values/cubesigner-signer-production.yaml', call)
                self.assertIn('0.1.9', call)

    def test_monitor_applies_generated_dstack_overlay_after_base_values(self):
        overlay = 'values/scroll-monitor-dstack.yaml'
        for targets in [['install-scroll-monitor'], ['install-scroll-core']]:
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
