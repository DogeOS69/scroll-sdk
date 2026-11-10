"""Render isolated capacity-manager and the WP peer without cluster access."""
import json
import pathlib
import subprocess
import tempfile
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def config():
    return {'prepared': True, 'image': {'digest': 'sha256:' + 'a' * 64},
            'manager': {'workerIdPrefix': 'test-provers',
                        'workerImage': 'example.invalid/worker@sha256:' + 'b' * 64,
                        'workerCommand': 'exec prover-worker --worker-id {worker_id}',
                        'policy': '[global]\nmax_workers = 2\n',
                        'dstack': {'project': 'test-project', 'fleets': ['test-fleet'],
                                   'regions': ['us-east-1'], 'instanceTypes': ['g6.4xlarge']}}}


def render(chart, values):
    with tempfile.TemporaryDirectory() as directory:
        file = pathlib.Path(directory) / 'values.yaml'
        file.write_text(yaml.safe_dump(values))
        return subprocess.run(['helm', 'template', chart, str(ROOT / 'charts' / chart), '-f', str(file)],
                              capture_output=True, text=True)


class CapacityManagerTests(unittest.TestCase):
    def test_initialization_precedes_deployment_and_uses_only_secret_references(self):
        values = config()
        values['initialization'] = {'enabled': True, 'provider': 'aws', 'fleets': [
            {'name': 'test-fleet', 'type': 'fleet', 'nodes': {'min': 0, 'target': 0, 'max': 2}}]}
        result = render('capacity-manager', values)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        job = next(d for d in docs if d['kind'] == 'Job')
        self.assertEqual(job['metadata']['annotations']['helm.sh/hook'], 'pre-install,pre-upgrade')
        pod = job['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertFalse(any(d['kind'] in ('Role', 'RoleBinding', 'ClusterRole', 'Secret') for d in docs))
        container = pod['containers'][0]
        self.assertIn('@sha256:', container['image'])
        env = {e['name']: e for e in container['env']}
        for key in ('DSTACK_TOKEN', 'WORKER_MASTER', 'WP_TOKEN'):
            self.assertIn('secretKeyRef', env[key]['valueFrom'])
            self.assertNotIn('value', env[key])
        self.assertEqual(json.loads(env['FLEET_INPUT']['value'])['fleets'][0]['nodes'], {'min': 0, 'target': 0, 'max': 2})
        self.assertLess(container['args'][0].index('preflight.py'), container['args'][0].index('initialize-fleets.py'))
        scripts = next(d for d in docs if d['kind'] == 'ConfigMap' and 'initialize-fleets.py' in d['data'])
        self.assertEqual(scripts['metadata']['annotations']['helm.sh/hook-weight'], '-10')
        self.assertIn('force=False', scripts['data']['initialize-fleets.py'])
        self.assertEqual(job['spec']['backoffLimit'], 0)
        # Chart-only legacy/manual use keeps explicit operator-owned fleets.
        docs = list(yaml.safe_load_all(render('capacity-manager', config()).stdout))
        self.assertFalse(any(d and d['kind'] == 'Job' for d in docs))

    def test_initialization_rejects_unsafe_or_incomplete_fleets(self):
        for failure in ('minimum', 'target', 'max', 'name', 'missing', 'duplicate', 'image', 'master'):
            values = config()
            fleet = {'name': 'test-fleet', 'type': 'fleet', 'nodes': {'min': 0, 'target': 0, 'max': 2}}
            init = {'enabled': True, 'provider': 'aws', 'fleets': [fleet]}
            values['initialization'] = init
            if failure == 'minimum': fleet['nodes']['min'] = 1
            if failure == 'target': fleet['nodes']['target'] = 1
            if failure == 'max': fleet['nodes']['max'] = 0
            if failure == 'name': fleet['name'] = 'unexpected'
            if failure == 'missing': init['fleets'] = []
            if failure == 'duplicate': init['fleets'].append(fleet.copy())
            if failure == 'image': init['image'] = {'digest': 'latest'}
            if failure == 'master': values['workerCredentialMaster'] = None
            self.assertNotEqual(render('capacity-manager', values).returncode, 0, failure)

    def test_initialization_checks_fallback_binary_before_fleet_creation(self):
        values = config()
        values['manager']['dstack']['fallbackFleet'] = 'vast-fallback'
        values['initialization'] = {'enabled': True, 'provider': 'aws', 'fallbackProvider': 'vastai',
            'fleets': [{'name': name, 'nodes': {'min': 0, 'target': 0, 'max': 2}}
                       for name in ['test-fleet', 'vast-fallback']]}
        result = render('capacity-manager', values)
        self.assertEqual(result.returncode, 0, result.stderr)
        job = next(d for d in yaml.safe_load_all(result.stdout) if d and d['kind'] == 'Job')
        init = job['spec']['template']['spec']['initContainers'][0]
        self.assertEqual(init['args'], ['--dstack-fallback-fleet', 'vast-fallback', '--help'])

    def test_optional_fallback_fleet_argument(self):
        for fleet in ['', 'vast-fallback']:
            values = config()
            values['manager']['dstack']['fallbackFleet'] = fleet
            result = render('capacity-manager', values)
            self.assertEqual(result.returncode, 0, result.stderr)
            deploy = next(d for d in yaml.safe_load_all(result.stdout) if d and d['kind'] == 'Deployment')
            args = deploy['spec']['template']['spec']['containers'][0]['args']
            self.assertEqual('--dstack-fallback-fleet' in args, bool(fleet))
            if fleet:
                self.assertEqual(args[args.index('--dstack-fallback-fleet') + 1], fleet)
            self.assertEqual(args[args.index('--dstack-fleet') + 1], 'test-fleet')
        for fleet in [' ', 'bad/name', ['vast-fallback']]:
            values['manager']['dstack']['fallbackFleet'] = fleet
            self.assertNotEqual(render('capacity-manager', values).returncode, 0)

    def test_private_dstack_ca_is_trusted_by_the_manager_and_initialization(self):
        ca = '-----BEGIN CERTIFICATE-----\nTUlJQmZha2U=\n-----END CERTIFICATE-----\n'
        values = config()
        values['manager']['dstack'].update(
            serverUrl='https://dstack-controller.dstack-system.svc:8443', caBundle=ca)
        values['initialization'] = {'enabled': True, 'provider': 'aws', 'fleets': [
            {'name': 'test-fleet', 'nodes': {'min': 0, 'target': 0, 'max': 2}}]}
        result = render('capacity-manager', values)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        bundle = next(d for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'capacity-manager-dstack-ca')
        self.assertEqual(bundle['data'], {'ca.crt': ca})
        self.assertNotIn('helm.sh/hook', bundle['metadata'].get('annotations', {}))
        deploy = next(d for d in docs if d['kind'] == 'Deployment')
        template = deploy['spec']['template']
        self.assertIn('checksum/dstack-ca', template['metadata']['annotations'])
        args = template['spec']['containers'][0]['args']
        self.assertEqual(args[args.index('--dstack-ca-file') + 1], '/etc/dstack-ca/ca.crt')
        mounts = {m['name']: m for m in template['spec']['containers'][0]['volumeMounts']}
        self.assertEqual(mounts['dstack-ca'], {'name': 'dstack-ca', 'mountPath': '/etc/dstack-ca', 'readOnly': True})
        volumes = {v['name']: v for v in template['spec']['volumes']}
        self.assertEqual(volumes['dstack-ca']['configMap']['name'], 'capacity-manager-dstack-ca')

        # The pre-install hook cannot mount the release ConfigMap, so its own hook ConfigMap carries the CA.
        job = next(d for d in docs if d['kind'] == 'Job')['spec']['template']['spec']
        scripts = next(d for d in docs if d['kind'] == 'ConfigMap' and 'preflight.py' in d['data'])
        self.assertEqual(scripts['data']['dstack-ca.crt'], ca)
        env = {e['name']: e.get('value') for e in job['containers'][0]['env']}
        self.assertEqual(env['REQUESTS_CA_BUNDLE'], '/etc/dstack-ca/ca.crt')
        volumes = {v['name']: v for v in job['volumes']}
        self.assertEqual(volumes['dstack-ca']['configMap']['items'], [{'key': 'dstack-ca.crt', 'path': 'ca.crt'}])
        self.assertEqual([c['args'] for c in job['initContainers']],
                         [['--dstack-ca-file', '/etc/dstack-ca/ca.crt', '--help']])

    def test_private_dstack_ca_allows_text_between_certificate_blocks(self):
        ca = '-----BEGIN CERTIFICATE-----\nTUlJQmZha2U=\n-----END CERTIFICATE-----\n'
        values = config()
        values['manager']['dstack'].update(serverUrl='https://dstack.example.invalid', caBundle=f'# old\n{ca}# new\n{ca}')
        result = render('capacity-manager', values)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_dstack_ca_is_absent_by_default_and_rejects_unsafe_input(self):
        result = render('capacity-manager', config())
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        self.assertFalse(any(d['metadata']['name'].endswith('-dstack-ca') for d in docs))
        deploy = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']
        self.assertNotIn('checksum/dstack-ca', deploy['metadata']['annotations'])
        self.assertNotIn('--dstack-ca-file', deploy['spec']['containers'][0]['args'])
        ca = '-----BEGIN CERTIFICATE-----\nTUlJQmZha2U=\n-----END CERTIFICATE-----\n'
        for url, bundle, message in [
            ('http://127.0.0.1:3000', ca, 'requires an https'),
            ('https://dstack.example.invalid', 'not a certificate', 'PEM CERTIFICATE'),
            ('https://dstack.example.invalid', ca + '-----BEGIN PRIVATE KEY-----\n', 'never a private key'),
            # Core skips other PEM blocks and would trust only part of the bundle.
            ('https://dstack.example.invalid', ca + ca.replace('CERTIFICATE', 'TRUSTED CERTIFICATE'), 'complete PEM CERTIFICATE'),
            ('https://dstack.example.invalid', ca + ca.replace('-----END CERTIFICATE-----', ''), 'complete PEM CERTIFICATE'),
            ('https://dstack.example.invalid', ca.replace('-----END CERTIFICATE-----', ca.strip()), 'complete PEM CERTIFICATE'),
            ('https://dstack.example.invalid', ca + '-----END X509 CRL-----\n', 'complete PEM CERTIFICATE'),
            # Markers must stand on their own lines around a base64 body, as Core reads them.
            ('https://dstack.example.invalid', ca + ca.replace('\n', '', 2), 'complete PEM CERTIFICATE'),
            ('https://dstack.example.invalid', ca + 'xx' + ca, 'complete PEM CERTIFICATE'),
            ('https://dstack.example.invalid', ca + '-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n', 'complete PEM CERTIFICATE'),
        ]:
            values = config()
            values['manager']['dstack'].update(serverUrl=url, caBundle=bundle)
            result = render('capacity-manager', values)
            self.assertNotEqual(result.returncode, 0, message)
            self.assertIn(message, result.stderr)

    def test_manager_is_single_writer_with_secret_references_and_no_public_listener(self):
        result = render('capacity-manager', config())
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        self.assertFalse(any(d['kind'] in ('Ingress', 'Service', 'Secret') for d in docs))
        deploy = next(d for d in docs if d['kind'] == 'Deployment')
        self.assertEqual(deploy['spec']['strategy']['type'], 'Recreate')
        self.assertEqual(deploy['spec']['replicas'], 1)
        pod = deploy['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        container = pod['containers'][0]
        self.assertIn('--dstack-max-price-usd', container['args'])
        self.assertEqual(container['args'][container['args'].index('--worker-credential-master-file') + 1],
                         '/run/secrets/worker-credential-master/master')
        self.assertFalse(any(arg.startswith('DOGEOS_PROVER_WORKER_TOKEN=') for arg in container['args']))
        self.assertNotIn('--scale-down-on-shutdown', container['args'])
        # The master comes from the coordinator Secret as a file, never as worker env.
        master = next(v for v in pod['volumes'] if v['name'] == 'worker-credential-master')
        self.assertEqual(master['secret'], {'secretName': 'proof-coordinator-secrets', 'defaultMode': 0o440,
                                            'items': [{'key': 'prover-worker-token', 'path': 'master'}]})
        self.assertIn('secretKeyRef', container['env'][0]['valueFrom'])
        pvc = next(d for d in docs if d['kind'] == 'PersistentVolumeClaim')
        self.assertEqual(pvc['metadata']['annotations']['helm.sh/resource-policy'], 'keep')

    def test_legacy_shared_token_is_explicit_and_exclusive(self):
        values = config()
        values['manager']['workerTokenSecret'] = 'cm_test_token'
        result = render('capacity-manager', values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not both', result.stderr)
        values['workerCredentialMaster'] = None
        result = render('capacity-manager', values)
        self.assertEqual(result.returncode, 0, result.stderr)
        pod = next(d for d in yaml.safe_load_all(result.stdout) if d and d['kind'] == 'Deployment')['spec']['template']['spec']
        args = pod['containers'][0]['args']
        self.assertIn('DOGEOS_PROVER_WORKER_TOKEN=${{ secrets.cm_test_token }}', args)
        self.assertNotIn('--worker-credential-master-file', args)
        self.assertFalse(any(v['name'] == 'worker-credential-master' for v in pod['volumes']))

    def test_public_worker_env_is_forwarded_without_changing_reserved_bindings(self):
        values = config()
        env = {'DOGEOS_CHUNK_VMEXE_URL': 'https://artifacts.example.invalid/chunk/app.vmexe',
               'DOGEOS_CHUNK_VMEXE_SHA256': 'b' * 64,
               'EXTRA_VALUE': 'spaces "quotes" = equals $HOME $(RUST_LOG) $${literal}',
               'EMPTY_VALUE': ''}
        values['manager']['workerEnv'] = env
        result = render('capacity-manager', values)
        self.assertEqual(result.returncode, 0, result.stderr)
        pod = next(d for d in yaml.safe_load_all(result.stdout) if d and d['kind'] == 'Deployment')['spec']['template']['spec']
        args = pod['containers'][0]['args']
        bindings = [args[i + 1] for i, arg in enumerate(args) if arg == '--dstack-worker-env']
        for key, value in env.items():
            self.assertIn(f'{key}={value}'.replace('$', '$$'), bindings)
        self.assertEqual(bindings.count('NVIDIA_DRIVER_CAPABILITIES=compute,utility'), 1)
        self.assertIn('--worker-credential-master-file', args)
        self.assertFalse(any(binding.startswith('DOGEOS_PROVER_WORKER_TOKEN=') for binding in bindings))

    def test_worker_env_rejects_invalid_names_types_and_owned_variables(self):
        for env in [[], 'string', {'1BAD': 'x'}, {'BAD-NAME': 'x'}, {'GOOD': 12}, {'GOOD': True},
                    {'GOOD': None}, *[{key: 'override'} for key in (
                        'DOGEOS_PROVER_WORKER_TOKEN', 'DOGEOS_PROVER_WORKER_READY_FILE',
                        'NVIDIA_DRIVER_CAPABILITIES', 'DOGEOS_CAPACITY_MANAGER',
                        'DOGEOS_CAPACITY_SPEC_SHA256', 'DOGEOS_WORKER_ID', 'DOGEOS_WORKER_SLOT',
                        'DOGEOS_CAPACITY_PROFILE')]]:
            with self.subTest(env=env):
                values = config()
                values['manager']['workerEnv'] = env
                result = render('capacity-manager', values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('workerEnv', result.stderr)

    def test_refuses_unprepared_mutable_or_multiple_writer_deployment(self):
        for change in [{'prepared': False}, {'replicaCount': 2}, {'image': {'digest': 'latest'}}]:
            values = config()
            values.update(change)
            result = render('capacity-manager', values)
            self.assertNotEqual(result.returncode, 0)

    def test_wp_manager_peer_can_only_reach_the_proof_work_port(self):
        values = yaml.safe_load((ROOT / 'examples/values/withdrawal-processor-production.yaml').read_text())
        peer = {'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'capacity-manager'}}}
        values['networkPolicy']['allowFrom']['capacityManager'] = [peer]
        result = render('withdrawal-processor', values)
        self.assertEqual(result.returncode, 0, result.stderr)
        policy = next(d for d in yaml.safe_load_all(result.stdout) if d and d['kind'] == 'NetworkPolicy')
        rules = policy['spec']['ingress']
        self.assertNotIn(peer, rules[0]['from'])
        self.assertIn(peer, rules[1]['from'])
        self.assertEqual(rules[1]['ports'], [{'port': 9300, 'protocol': 'TCP'}])


if __name__ == '__main__':
    unittest.main()
