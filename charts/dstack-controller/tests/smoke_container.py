"""Opt-in local runtime smoke test. No network, provider credentials or GPU.

Uses the chart's image, environment and mount layout, then recreates the
container with the same volume and checks persisted authenticated identity.
This is not a Kubernetes deployment test.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import uuid

import yaml

CHART = Path(__file__).resolve().parents[1]


def docker(*args, check=True):
    return subprocess.run(["docker", *args], check=check, text=True, capture_output=True)


def main():
    manifests = yaml.safe_load_all(subprocess.check_output(
        ["helm", "template", "smoke", str(CHART)], text=True))
    deployment = next(d for d in manifests if d and d["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    name = "dstack-chart-smoke-" + uuid.uuid4().hex[:12]
    volume = name + "-state"
    # No automatic pull: explicitly pull the pinned chart image before this test.
    docker("image", "inspect", container["image"])
    with tempfile.TemporaryDirectory(prefix="dstack-chart-smoke-") as directory:
        config = Path(directory) / "config.yml"
        config.write_text(yaml.safe_dump({
            "projects": [{"name": "main", "backends": []}],
            "encryption": {"keys": [{"type": "aes", "name": "smoketest",
                                      "secret": base64.b64encode(os.urandom(32)).decode()}]},
        }))
        # The temporary parent is mode 0700. A bind-mounted host-owned file must
        # be readable by container root after dropping DAC_OVERRIDE; Kubernetes
        # projected Secret files instead belong to root and use mode 0400.
        config.chmod(0o444)
        env = Path(directory) / "controller.env"
        env.write_text("\n".join(
            f'{e["name"]}={e["value"]}' for e in container["env"] if "value" in e
        ) + "\nDSTACK_SERVER_ADMIN_TOKEN=" + secrets.token_hex(32) + "\n")
        env.chmod(0o600)
        probe = '''
import hashlib, json, os, urllib.request
assert urllib.request.urlopen("http://127.0.0.1:3000/", timeout=3).status == 200
request = urllib.request.Request("http://127.0.0.1:3000/api/users/get_my_user",
    data=b"{}", headers={"Content-Type": "application/json",
    "Authorization": "Bearer " + os.environ["DSTACK_SERVER_ADMIN_TOKEN"]})
user = json.load(urllib.request.urlopen(request, timeout=3))
assert user["username"] == "admin"
assert os.path.isfile("/root/.dstack/server/data/sqlite.db")
# Print only a digest of the identity, never the token or private key.
print(hashlib.sha256(json.dumps({k: user[k] for k in
    ("id", "username", "ssh_public_key")}, sort_keys=True).encode()).hexdigest())
'''
        try:
            docker("volume", "create", volume)
            identities = []
            for attempt in range(2):
                docker("run", "-d", "--name", name, "--network", "none",
                       "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                       "--env-file", str(env),
                       "--mount", f"type=volume,src={volume},dst=/root/.dstack/server",
                       "--mount", f"type=bind,src={config},dst=/root/.dstack/server/config.yml,readonly",
                       container["image"])
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    result = docker("exec", name, "python3", "-c", probe, check=False)
                    if result.returncode == 0:
                        identities.append(result.stdout.strip())
                        break
                    if docker("inspect", "--format", "{{.State.Running}}", name).stdout.strip() != "true":
                        raise RuntimeError("Controller exited during isolated startup")
                    time.sleep(2)
                else:
                    raise RuntimeError("Controller did not pass authenticated readiness within 120s")
                docker("stop", "--time", "30", name)
                docker("rm", name)
            assert identities[0] == identities[1], "Identity changed after container recreation"
        except Exception as error:
            logs = docker("logs", "--tail", "40", name, check=False)
            message = logs.stdout + logs.stderr
            for line in env.read_text().splitlines():
                if line.startswith("DSTACK_SERVER_ADMIN_TOKEN="):
                    message = message.replace(line.split("=", 1)[1], "<redacted>")
            key = yaml.safe_load(config.read_text())["encryption"]["keys"][0]["secret"]
            raise RuntimeError(f"{error}\n{message.replace(key, '<redacted>')}") from error
        finally:
            docker("rm", "-f", name, check=False)
            docker("volume", "rm", volume)
    print("PASS: network-isolated startup, authentication, SQLite persistence and restart; resources removed")


if __name__ == "__main__":
    main()
