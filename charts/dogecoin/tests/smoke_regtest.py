"""Opt-in test using a local Dogecoin image, no Kubernetes, host ports or volumes.

Runs the chart's real start/probe/stop commands against an isolated regtest chain.
A locally available image is required; the test never pulls an image.
"""
import json
import os
import pathlib
import subprocess
import tempfile
import time
import uuid

from test_templates import deployment, render


def main():
    image = os.environ.get('DOGECOIN_TEST_IMAGE', 'dogeos69/dogecoin:1.14.9')
    name = 'dogecoin-chart-smoke-' + uuid.uuid4().hex[:12]

    def docker(*args, check=True, timeout=30):
        return subprocess.run(['docker', *args], capture_output=True, text=True,
                              check=check, timeout=timeout)

    docker('image', 'inspect', image)
    docs = render('-f', str(pathlib.Path(__file__).resolve().parents[1] / 'values-regtest.yaml'),
                  '--set', 'dogecoinConf.rpcallowip[0]=127.0.0.1',
                  '--set', 'dogecoinConf.connect=0', '--set', 'dogecoinConf.dnsseed=0')
    pod = deployment(docs)['spec']['template']['spec']
    container = pod['containers'][0]
    config = next(doc for doc in docs if doc['kind'] == 'ConfigMap')['data']['dogecoin.conf']
    created = False
    try:
        # Use the actual chart entrypoint against a fresh, isolated datadir.
        script = 'mkdir -p /dogecoin-data\n' + container['command'][-1]
        docker('create', '--name', name, '--network', 'none', '--entrypoint', '/bin/sh',
               image, '-c', script)
        created = True
        with tempfile.TemporaryDirectory(prefix='dogecoin-smoke-config-') as directory:
            root = pathlib.Path(directory)
            (root / 'dogecoin.conf').write_text(config)
            secrets = root / 'dogecoin-secrets'
            secrets.mkdir()
            (secrets / 'password').write_text('local-smoke-fixture-password')
            docker('cp', str(root / 'dogecoin.conf'), name + ':/etc/dogecoin.conf')
            docker('cp', str(secrets), name + ':/etc/dogecoin-secrets')
        for cycle in range(2):
            started = time.monotonic()
            docker('start', name)
            deadline = started + 60
            while True:
                result = docker('exec', name, *container['startupProbe']['exec']['command'],
                                check=False, timeout=10)
                if result.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError('Regtest did not pass the chart startup probe within 60s')
                time.sleep(1)
            ready = docker('exec', name, *container['readinessProbe']['exec']['command'])
            chain = json.loads(ready.stdout)
            assert chain['chain'] == 'regtest', chain['chain']
            assert chain['blocks'] == 0, 'Smoke test should not mine blocks or require peers'
            # Regtest may report IBD=true at genesis: readiness must still pass.
            elapsed = round(time.monotonic() - started, 2)
            print(json.dumps({'cycle': cycle + 1, 'rpc_ready_seconds': elapsed,
                              'blocks': chain['blocks'], 'initialblockdownload': chain['initialblockdownload']}), flush=True)
            docker('exec', name, *container['lifecycle']['preStop']['exec']['command'])
            assert docker('wait', name).stdout.strip() == '0', 'Dogecoin must shut down cleanly'
        print('PASS: chart probes accepted RPC without peers/blocks; two clean starts/stops on the same isolated datadir')
    finally:
        if created:
            docker('rm', '-f', name, check=False)


if __name__ == '__main__':
    main()
