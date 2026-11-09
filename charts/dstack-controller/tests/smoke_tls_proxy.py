"""Opt-in local runtime smoke test for tls.enabled. No provider credentials or GPU.

Runs the chart's controller command and TLS sidecar, with the rendered files, in one
network namespace as in the Pod. A disposable CA stands in for cert-manager. Checks
that peers reach dstack only through HTTPS with the private CA, that the controller
probe passes, that a renewed certificate is served without a restart, and that the
proxy stops on SIGTERM and on the image's SIGQUIT stop signal. This is not a Kubernetes deployment test.
"""
import base64
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import uuid

import yaml

CHART = Path(__file__).resolve().parents[1]
SERVER_NAME = "smoke-dstack-controller.default.svc"


def run(*args, check=True):
    return subprocess.run(list(args), check=check, text=True, capture_output=True)


def docker(*args, check=True):
    return run("docker", *args, check=check)


def issue_certificate(directory, ca_key, ca_cert, name):
    key, request, extensions = directory / f"{name}.key", directory / f"{name}.csr", directory / f"{name}.ext"
    extensions.write_text(f"subjectAltName=DNS:{SERVER_NAME}\nextendedKeyUsage=serverAuth\n")
    run("openssl", "req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
        "-keyout", str(key), "-out", str(request), "-subj", "/CN=smoke")
    run("openssl", "x509", "-req", "-in", str(request), "-CA", str(ca_cert), "-CAkey", str(ca_key),
        "-set_serial", str(int.from_bytes(os.urandom(8), "big")), "-days", "1",
        "-extfile", str(extensions), "-out", str(directory / f"{name}.crt"))
    return directory / f"{name}.crt", key


def install(source, target):
    """Replace a mounted file atomically, as a Secret volume update does."""
    staged = target.with_name("." + target.name)
    staged.write_bytes(source.read_bytes())
    staged.chmod(0o444)
    os.replace(staged, target)


def main():
    manifests = [d for d in yaml.safe_load_all(subprocess.check_output(
        ["helm", "template", "smoke", str(CHART), "--namespace", "default",
         "--set", "tls.enabled=true", "--set", "tls.proxy.reloadCheckSeconds=10"], text=True)) if d]
    pod = next(d for d in manifests if d["kind"] == "Deployment")["spec"]["template"]["spec"]
    controller = next(c for c in pod["containers"] if c["name"] == "controller")
    proxy = next(c for c in pod["containers"] if c["name"] == "tls-proxy")
    proxy_files = next(d for d in manifests if d["kind"] == "ConfigMap")["data"]
    name = "dstack-tls-smoke-" + uuid.uuid4().hex[:12]
    network, volume, peer_image = name + "-net", name + "-state", controller["image"]
    # No automatic pull: explicitly pull both pinned chart images before this test.
    docker("image", "inspect", controller["image"])
    docker("image", "inspect", proxy["image"])
    with tempfile.TemporaryDirectory(prefix="dstack-tls-smoke-") as directory:
        root = Path(directory)
        root.chmod(0o755)
        work, tls, proxy_config = root / "work", root / "tls", root / "proxy"
        for path in (work, tls, proxy_config):
            path.mkdir(mode=0o755)
        work.chmod(0o700)
        ca_key, ca_cert = work / "ca.key", work / "ca.crt"
        run("openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
            "-keyout", str(ca_key), "-out", str(ca_cert), "-days", "1", "-subj", "/CN=smoke-ca",
            "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        first_cert, first_key = issue_certificate(work, ca_key, ca_cert, "first")
        install(first_cert, tls / "tls.crt")
        install(first_key, tls / "tls.key")
        install(ca_cert, tls / "ca.crt")
        for file, content in proxy_files.items():
            (proxy_config / file).write_text(content)
            (proxy_config / file).chmod(0o444)
        config = root / "config.yml"
        config.write_text(yaml.safe_dump({
            "projects": [{"name": "main", "backends": []}],
            "encryption": {"keys": [{"type": "aes", "name": "smoketest",
                                      "secret": base64.b64encode(os.urandom(32)).decode()}]},
        }))
        config.chmod(0o444)
        token = secrets.token_hex(32)
        env = work / "controller.env"
        env.write_text("\n".join(f'{e["name"]}={e["value"]}' for e in controller["env"] if "value" in e)
                       + f"\nDSTACK_SERVER_ADMIN_TOKEN={token}\n")

        def peer(*command):
            return docker("run", "--rm", "--network", network, "--mount",
                          f"type=bind,src={tls / 'ca.crt'},dst=/ca.crt,readonly",
                          "--entrypoint", command[0], peer_image, *command[1:], check=False)

        try:
            docker("network", "create", network)
            docker("volume", "create", volume)
            docker("run", "-d", "--name", name, "--network", network,
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--env-file", str(env),
                   "--mount", f"type=volume,src={volume},dst=/root/.dstack/server",
                   "--mount", f"type=bind,src={config},dst=/root/.dstack/server/config.yml,readonly",
                   "--entrypoint", controller["command"][0], controller["image"], *controller["command"][1:])
            context = proxy["securityContext"]
            docker("run", "-d", "--name", name + "-proxy", "--network", f"container:{name}",
                   "--user", f'{context["runAsUser"]}:{context["runAsGroup"]}', "--read-only",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--tmpfs", f'/tmp:uid={context["runAsUser"]},gid={context["runAsGroup"]}',
                   "--mount", f"type=bind,src={proxy_config},dst=/etc/dstack-tls-proxy,readonly",
                   "--mount", f"type=bind,src={tls},dst=/etc/dstack-tls,readonly",
                   "--entrypoint", proxy["command"][0], proxy["image"], *proxy["command"][1:])
            probe = controller["readinessProbe"]["exec"]["command"]
            deadline = time.monotonic() + 120
            while docker("exec", name, *probe, check=False).returncode:
                if time.monotonic() > deadline:
                    raise RuntimeError("Controller probe did not pass within 120s")
                time.sleep(2)

            address = docker("inspect", "--format",
                             "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name).stdout.strip()
            port = proxy["ports"][0]["containerPort"]
            url = f"https://{SERVER_NAME}:{port}/"
            resolve = f"{SERVER_NAME}:{port}:{address}"
            trusted = peer("curl", "--fail", "--silent", "--output", "/dev/null", "--cacert", "/ca.crt",
                           "--resolve", resolve, url)
            assert trusted.returncode == 0, f"HTTPS with the private CA failed: {trusted.stderr}"
            public_roots = peer("curl", "--silent", "--output", "/dev/null", "--resolve", resolve, url)
            assert public_roots.returncode == 60, "Public roots must not trust the private CA"
            plaintext = peer("curl", "--silent", "--max-time", "5", f"http://{address}:3000/")
            assert plaintext.returncode == 7, "dstack must not listen on the Pod network"

            def served_certificate():
                return peer("python3", "-c", "import ssl,sys; print(ssl.get_server_certificate((sys.argv[1], "
                            f"{port})).strip())", address).stdout.strip()

            assert served_certificate() == first_cert.read_text().strip()
            started = docker("inspect", "--format", "{{.State.StartedAt}}", name + "-proxy").stdout
            second_cert, second_key = issue_certificate(work, ca_key, ca_cert, "second")
            install(second_key, tls / "tls.key")
            install(second_cert, tls / "tls.crt")
            deadline = time.monotonic() + 60
            while served_certificate() != second_cert.read_text().strip():
                if time.monotonic() > deadline:
                    raise RuntimeError("Renewed certificate was not served within 60s")
                time.sleep(2)
            assert docker("inspect", "--format", "{{.State.StartedAt}}", name + "-proxy").stdout == started

            # docker stop sends the image's SIGQUIT; the kubelet can send SIGTERM instead.
            for signal in ("SIGQUIT", "SIGTERM"):
                if signal == "SIGTERM":
                    docker("start", name + "-proxy")
                time.sleep(2)
                began = time.monotonic()
                docker("kill", "--signal", signal, name + "-proxy")
                docker("wait", name + "-proxy")
                exit_code = docker("inspect", "--format", "{{.State.ExitCode}}", name + "-proxy").stdout.strip()
                assert exit_code == "0" and time.monotonic() - began < 15, f"Proxy did not stop cleanly on {signal}"
        except Exception as error:
            logs = ""
            for container in (name, name + "-proxy"):
                result = docker("logs", "--tail", "40", container, check=False)
                logs += f"\n[{container}]\n{result.stdout}{result.stderr}"
            raise RuntimeError(f"{error}{logs.replace(token, '<redacted>')}") from error
        finally:
            docker("rm", "-f", name + "-proxy", name, check=False)
            docker("network", "rm", network, check=False)
            docker("volume", "rm", volume, check=False)
    print("PASS: HTTPS only through the private CA, loopback-only dstack, certificate reload and clean stop")


if __name__ == "__main__":
    main()
