"""Allowlist reconciliation, IPC transport and independently rendered Helm releases."""

import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

import yaml

from test_l2_reth import helm_template


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "peer_allowlist", ROOT / "charts/l2-reth/files/peer_allowlist.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def public_key(seed):
    # Generate test curve points, without storing any private key material.
    p = 2**256 - 2**32 - 977
    x = seed
    while True:
        y_squared = (x**3 + 7) % p
        y = pow(y_squared, (p + 1) // 4, p)
        if y * y % p == y_squared:
            return f"{x:064x}{y:064x}"
        x += 1


A, B, C = (public_key(seed) for seed in (100, 200, 300))


class FakeReth:
    """Simulate the Reth RPC interface for controller unit tests."""

    def __init__(self):
        self.trusted = set()
        self.sessions = set()
        self.calls = []
        self.fail_after_add = False

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "admin_peers":
            return [{"id": "hashed-id-is-not-a-public-key", "enode": f"enode://{key}@127.0.0.1:30303"}
                    for key in sorted(self.sessions)]
        key = params[0].removeprefix("enode://")
        if method == "admin_addTrustedPeer":
            self.trusted.add(key)
            if self.fail_after_add:
                self.fail_after_add = False
                raise ConnectionError("connection lost after mutation")
        elif method == "admin_removeTrustedPeer":
            self.trusted.discard(key)
        elif method == "admin_removePeer":
            if key not in self.trusted:
                self.sessions.discard(key)
        else:
            raise AssertionError(method)
        return True


class ReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.policy = self.root / "peers.json"
        self.state = self.root / "state"
        self.rpc = FakeReth()
        self.write([])
        self.sync = controller.Reconciler(self.rpc, self.policy, self.state)

    def write(self, peers):
        # Atomic replacement models a projected ConfigMap's changing symlink.
        controller.atomic_json(self.policy, peers)

    def test_add_revoke_and_disconnect_without_restarting(self):
        self.write([A, B])
        self.sync.reconcile()
        self.assertEqual(self.rpc.trusted, {A, B})
        self.rpc.sessions = {A, B}
        self.write([B, C])
        self.sync.reconcile()
        self.assertEqual(self.rpc.trusted, {B, C})
        self.assertEqual(self.rpc.sessions, {B})
        removes = [method for method, args in self.rpc.calls if args == [f"enode://{A}"]]
        self.assertEqual(removes[-2:], ["admin_removeTrustedPeer", "admin_removePeer"])

    def test_reth_restart_between_polls_replays_unchanged_policy(self):
        self.write([A])
        self.sync.reconcile()
        self.rpc.trusted.clear()
        self.sync.reconcile()
        self.assertEqual(self.rpc.trusted, {A})

    def test_sidecar_restart_removes_disconnected_peer_from_old_policy(self):
        self.write([A, B])
        self.sync.reconcile()
        self.write([B])
        restarted = controller.Reconciler(self.rpc, self.policy, self.state)
        restarted.reconcile()
        self.assertEqual(self.rpc.trusted, {B})

    def test_ambiguous_rpc_failure_does_not_lose_revocation_intent(self):
        self.write([A])
        self.rpc.fail_after_add = True
        with self.assertRaises(ConnectionError):
            self.sync.reconcile()
        self.assertFalse(self.sync.ready.exists())
        self.write([])
        restarted = controller.Reconciler(self.rpc, self.policy, self.state)
        restarted.reconcile()
        self.assertEqual(self.rpc.trusted, set())

    def test_static_sequencer_survives_empty_policy_and_dynamic_revocation(self):
        self.rpc.trusted.add(A)
        self.rpc.sessions.add(A)
        self.sync = controller.Reconciler(self.rpc, self.policy, self.state, [A])
        self.sync.reconcile()
        self.write([A, B])  # A can also appear in the runtime list.
        self.sync.reconcile()
        self.rpc.sessions.add(B)
        self.write([])
        self.sync.reconcile()
        restarted = controller.Reconciler(self.rpc, self.policy, self.state, [A])
        restarted.reconcile()
        self.assertEqual(self.rpc.trusted, {A})
        self.assertEqual(self.rpc.sessions, {A})
        self.assertFalse(any(args == [f"enode://{A}"] for _, args in self.rpc.calls))

    def test_empty_policy_revokes_all_and_removals_are_retried(self):
        self.write([A])
        self.sync.reconcile()
        self.write([])
        self.sync.reconcile()
        self.rpc.trusted.add(A)  # Simulate a late mutation after the previous pass.
        self.sync.reconcile()
        self.assertEqual(self.rpc.trusted, set())

    def test_unknown_connected_peers_are_revoked_using_enode_not_hashed_id(self):
        self.rpc.sessions.add(C)
        self.rpc.trusted.add(C)
        self.sync.reconcile()
        self.assertFalse(self.rpc.sessions)
        self.assertFalse(self.rpc.trusted)

    def test_invalid_policy_preserves_last_good_policy_even_after_restarts(self):
        self.write([A])
        self.sync.reconcile()
        for invalid in (["not-a-public-key"], {"peers": []}, ["00" * 64]):
            with self.subTest(invalid=invalid):
                self.write(invalid)
                self.rpc.trusted.clear()
                restarted = controller.Reconciler(self.rpc, self.policy, self.state)
                with self.assertRaisesRegex(ValueError, "retaining last valid"):
                    restarted.reconcile()
                self.assertEqual(self.rpc.trusted, {A})
                self.assertFalse(restarted.ready.exists())

    def test_missing_policy_at_start_does_not_change_reth(self):
        self.policy.unlink()
        with self.assertRaisesRegex(ValueError, "no valid allowlist"):
            self.sync.reconcile()
        self.assertEqual(self.rpc.calls, [])

    def test_key_validation_and_deduplication(self):
        self.assertEqual(controller.peer_set([A, A.upper(), "0x" + A, "enode://" + A]), {A})
        for invalid in (None, "11" * 32, "04" + A, "enode://" + A + "@127.0.0.1:30303", "ff" * 64):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                controller.peer_id(invalid)


class IPCTests(unittest.TestCase):
    def exchange(self, response, close_early=False):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "reth.ipc")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(path)
                server.listen(1)

                def serve():
                    with server.accept()[0] as connection:
                        stream = connection.makefile("rb")
                        request = json.loads(stream.readline())
                        stream.close()
                        payload = json.dumps({"jsonrpc": "2.0", "id": request["id"], **response}).encode()
                        # Responses need not arrive in one recv or end in a newline.
                        connection.sendall(payload[:10])
                        if not close_early:
                            connection.sendall(payload[10:])

                worker = threading.Thread(target=serve)
                worker.start()
                try:
                    return controller.IPC(path).call("admin_peers", [])
                finally:
                    worker.join(timeout=5)

    def test_fragmented_response_without_newline(self):
        self.assertEqual(self.exchange({"result": []}), [])

    def test_rpc_errors_and_truncated_responses_are_not_success(self):
        with self.assertRaises(RuntimeError):
            self.exchange({"error": {"code": -32601, "message": "not available"}})
        with self.assertRaises(ConnectionError):
            self.exchange({"result": True}, close_early=True)


class ChartTests(unittest.TestCase):
    def values(self, **settings):
        return {"role": "bootnode", "reth": {"peerAllowlist": {"enabled": True, **settings}}}

    def render(self, values):
        result = helm_template(values=values)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    def test_bootnode_has_shared_ipc_and_sidecar_only_policy_and_state(self):
        docs = self.render(self.values())
        pod = next(d for d in docs if d["kind"] == "StatefulSet")["spec"]["template"]["spec"]
        main, sidecar = pod["containers"]
        self.assertIn("--trusted-only", main["args"])
        self.assertIn("--no-persist-peers", main["args"])
        self.assertIn("--disable-discovery", main["args"])
        self.assertNotIn("--max-outbound-peers", main["args"])
        self.assertEqual(main["args"][main["args"].index("--ipcpath") + 1], "/run/reth-allowlist/reth.ipc")
        mounts = {v["name"]: v for v in sidecar["volumeMounts"]}
        self.assertNotIn("subPath", mounts["peer-allowlist-policy"])
        self.assertTrue(mounts["peer-allowlist-policy"]["readOnly"])
        self.assertNotIn("data", mounts)
        self.assertEqual(mounts["peer-allowlist-state"]["mountPath"], "/var/lib/reth-peer-allowlist")
        # /var/run is a symlink to /run in the Python Alpine runtime.
        self.assertNotEqual(mounts["peer-allowlist-state"]["mountPath"].replace("/var/run/", "/run/"),
                            mounts["peer-allowlist-ipc"]["mountPath"])
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertEqual(volumes["peer-allowlist-policy"]["configMap"]["name"], "reth-peer-allowlist")
        self.assertIn("emptyDir", volumes["peer-allowlist-state"])
        cms = {d["metadata"]["name"]: d for d in docs if d["kind"] == "ConfigMap"}
        code_name = volumes["peer-allowlist-code"]["configMap"]["name"]
        self.assertIn("peer_allowlist.py", cms[code_name]["data"])
        self.assertNotIn("reth-peer-allowlist", cms)
        self.assertTrue(sidecar["readinessProbe"])

    def test_feature_is_opt_in(self):
        docs = self.render({})
        pod = next(d for d in docs if d["kind"] == "StatefulSet")["spec"]["template"]["spec"]
        self.assertEqual(len(pod["containers"]), 1)
        self.assertNotIn("--no-persist-peers", pod["containers"][0]["args"])

    def test_uid_matches_execution_client(self):
        for override, uid in [({"securityContext": {"runAsUser": 1234}}, 1234),
                              ({"podSecurityContext": {"runAsUser": 5678}}, 5678)]:
            docs = self.render({**self.values(), **override})
            pod = next(d for d in docs if d["kind"] == "StatefulSet")["spec"]["template"]["spec"]
            self.assertEqual(pod["containers"][1]["securityContext"]["runAsUser"], uid)

    def test_sequencer_peers_and_outbound_limit_are_preserved(self):
        peers = f"enode://{A}@sequencer-0:30303,enode://{B}@sequencer-1:30303"
        values = self.values()
        values["reth"].update({"trustedPeers": peers, "rpc": {"maxOutboundPeers": "25"}})
        docs = self.render(values)
        pod = next(d for d in docs if d["kind"] == "StatefulSet")["spec"]["template"]["spec"]
        args = pod["containers"][0]["args"]
        self.assertEqual(args[args.index("--trusted-peers") + 1], peers)
        self.assertEqual(args[args.index("--max-outbound-peers") + 1], "25")
        policy = next(d for d in docs if d["kind"] == "ConfigMap"
                      and "static-peer-ids.json" in d.get("data", {}))
        self.assertEqual(json.loads(policy["data"]["static-peer-ids.json"]), [f"enode://{A}", f"enode://{B}"])

    def test_conflicting_configuration_is_rejected(self):
        cases = [
            ({"trustedPeers": "enode://" + A}, "address-bearing enode URLs"),
            ({"http": {"api": "eth,admin"}}, "remove admin"),
            ({"ws": {"api": "eth,admin"}}, "remove admin"),
            ({"peerAllowlist": {"enabled": True, "intervalSeconds": 0}}, "positive integer"),
        ]
        for extra, message in cases:
            values = self.values()
            values["reth"].update(extra)
            with self.subTest(extra=extra):
                result = helm_template(values=values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
        for flag in ["--trusted-only=false", "--peers-file", "--config", "--ipcdisable",
                     "--discovery.v5", "--max-outbound-peers=20"]:
            values = self.values()
            values["reth"]["extraArgs"] = [flag]
            with self.subTest(flag=flag):
                self.assertNotEqual(helm_template(values=values).returncode, 0)

    def test_production_overlay_preserves_external_p2p_and_references_same_policy(self):
        example = ROOT / "examples/values/l2-reth-bootnode-production.yaml"
        overlay = ROOT / "examples/values/l2-reth-bootnode-allowlist.yaml"
        external = ROOT / "charts/l2-reth/ci/existing-nlb-values.yaml"
        result = helm_template(example, external, overlay)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
        self.assertTrue(any(d["kind"] == "TargetGroupBinding" for d in docs))
        for release in ["bootnode-0", "bootnode-1"]:
            command = ["helm", "template", release, str(ROOT / "charts/l2-reth"),
                       "--namespace", "nodes", "-f", str(example), "-f", str(external), "-f", str(overlay)]
            rendered = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            resources = [doc for doc in yaml.safe_load_all(rendered.stdout) if doc]
            pod = next(d for d in resources if d["kind"] == "StatefulSet")["spec"]["template"]
            volume = next(v for v in pod["spec"]["volumes"] if v["name"] == "peer-allowlist-policy")
            self.assertEqual(volume["configMap"]["name"], "reth-peer-allowlist")
            # Helm must not look up the live policy to incorporate it in a checksum.
            self.assertNotIn("lookup", (ROOT / "charts/l2-reth/templates/_peer-allowlist.tpl").read_text())

    def test_rejects_non_bootnode_role(self):
        values = self.values()
        values["role"] = "rpc"
        result = helm_template(values=values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires role bootnode", result.stderr)

    def test_shared_chart_changes_only_configmap_for_empty_add_remove(self):
        for peers in [[], [A], [A, B], [B], []]:
            with tempfile.TemporaryDirectory() as directory:
                values = Path(directory) / "values.yaml"
                values.write_text(yaml.safe_dump({"peers": peers}))
                result = subprocess.run(["helm", "template", "shared-peers", str(ROOT / "charts/reth-peer-allowlist"),
                                         "--namespace", "nodes", "-f", str(values)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                docs = list(yaml.safe_load_all(result.stdout))
                self.assertEqual(len(docs), 1)
                self.assertEqual(docs[0]["kind"], "ConfigMap")
                self.assertEqual(docs[0]["metadata"]["namespace"], "nodes")
                self.assertEqual(json.loads(docs[0]["data"]["peers.json"]), peers)


if __name__ == "__main__":
    unittest.main()
