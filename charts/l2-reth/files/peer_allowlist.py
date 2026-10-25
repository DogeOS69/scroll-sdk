#!/usr/bin/env python3
"""Reconcile a mounted public-key allowlist through Reth's local JSON-RPC IPC."""

import argparse
import json
import logging
import os
from pathlib import Path
import re
import signal
import socket
import threading
import time


LOG = logging.getLogger("peer-allowlist")
MAX_RESPONSE = 8 * 1024 * 1024


def peer_id(value):
    """Accept uncompressed node IDs, never addresses, private keys or URLs."""
    if not isinstance(value, str):
        raise ValueError("peer IDs must be strings")
    value = value.removeprefix("enode://").removeprefix("0x")
    if not re.fullmatch(r"[0-9a-fA-F]{128}", value):
        raise ValueError("expected a 128-hex-digit P2P public key without an address")
    # An enode ID is the x || y encoding of a secp256k1 public key.
    x, y = int(value[:64], 16), int(value[64:], 16)
    p = 2**256 - 2**32 - 977
    if x >= p or y >= p or (y * y - x * x * x - 7) % p:
        raise ValueError("P2P public key is not on secp256k1")
    return value.lower()


def peer_set(value):
    if not isinstance(value, list):
        raise ValueError("allowlist must be a JSON array of public keys")
    return {peer_id(item) for item in value}


def atomic_json(path, value):
    """Persist intent before RPC writes so a sidecar restart can retry removals."""
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class IPC:
    def __init__(self, path, timeout=5):
        self.path = path
        self.timeout = timeout
        self.sequence = 0

    def call(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        deadline = time.monotonic() + self.timeout
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(self.path)
            connection.sendall(json.dumps(request).encode() + b"\n")
            response = bytearray()
            while len(response) < MAX_RESPONSE:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("IPC response deadline exceeded")
                connection.settimeout(remaining)
                chunk = connection.recv(min(65536, MAX_RESPONSE - len(response)))
                if not chunk:
                    raise ConnectionError("IPC closed before a complete response")
                response.extend(chunk)
                try:
                    result = json.loads(response)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(result, dict) or result.get("id") != request_id:
                    raise ValueError("invalid IPC response ID")
                if "error" in result:
                    # Do not echo server-provided text into logs.
                    raise RuntimeError(f"{method} returned an RPC error")
                if "result" not in result:
                    raise ValueError("IPC response has no result")
                return result["result"]
        raise ValueError("IPC response exceeds size limit")


class Reconciler:
    def __init__(self, rpc, allowlist, state_dir, static_peers=()):
        self.rpc = rpc
        self.allowlist = Path(allowlist)
        # Startup-configured peers (e.g. sequencers) are owned by Reth's flags,
        # not by the runtime policy. Never revoke them or disconnect them.
        self.static_peers = peer_set(list(static_peers))
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.journal = self.state_dir / "journal.json"
        self.ready = self.state_dir / "ready.json"
        self.managed = set()
        self.desired = None
        if self.journal.exists():
            state = json.loads(self.journal.read_text())
            self.managed = peer_set(state["managed"])
            self.desired = peer_set(state["desired"])

    def write_journal(self):
        atomic_json(self.journal, {"managed": sorted(self.managed), "desired": sorted(self.desired)})

    def connected(self):
        peers = self.rpc.call("admin_peers", [])
        if not isinstance(peers, list):
            raise ValueError("admin_peers did not return a list")
        # admin_peers.id is a hash in this Reth version, not the enode public key.
        return {peer_id(peer["enode"].split("@", 1)[0]) for peer in peers}

    def mutate(self, method, node_id):
        if self.rpc.call(method, ["enode://" + node_id]) is not True:
            raise RuntimeError(f"{method} did not acknowledge the request")

    def reconcile(self):
        try:
            return self._reconcile()
        except Exception:
            self.ready.unlink(missing_ok=True)
            raise

    def _reconcile(self):
        invalid_config = False
        try:
            desired = peer_set(json.loads(self.allowlist.read_text()))
        except (OSError, ValueError):
            if self.desired is None:
                raise ValueError("no valid allowlist is available") from None
            # Preserve the last valid policy, including after an execution-client restart.
            desired = self.desired
            invalid_config = True

        self.desired = desired
        allowed = desired | self.static_peers
        self.managed |= desired | self.connected()
        self.write_journal()
        # Keep tombstones for the Pod's lifetime. RPC success is asynchronous;
        # repeating removals also handles interrupted calls and late connections.
        for node_id in sorted(self.managed - allowed):
            self.mutate("admin_removeTrustedPeer", node_id)
            self.mutate("admin_removePeer", node_id)
        # Replay every cycle: no ConfigMap edit or observed outage is needed to
        # recover after Reth restarts between polls, or after only this sidecar restarts.
        for node_id in sorted(desired - self.static_peers):
            self.mutate("admin_addTrustedPeer", node_id)
        if self.connected() - allowed:
            raise RuntimeError("waiting for unauthorized sessions to disconnect")
        if invalid_config:
            raise ValueError("allowlist unreadable or invalid; retaining last valid policy")
        atomic_json(self.ready, {"time": time.time(), "peers": len(allowed)})
        return len(allowed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipc", default="/run/reth-allowlist/reth.ipc")
    parser.add_argument("--allowlist", default="/etc/reth-allowlist/peers.json")
    parser.add_argument("--state-dir", default="/var/lib/reth-peer-allowlist")
    parser.add_argument("--static-peers", help="JSON file of IDs from Reth's startup trusted peers")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--rpc-timeout", type=float, default=5)
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--max-age", type=float, default=60)
    args = parser.parse_args()
    if args.healthcheck:
        try:
            ready = json.loads((Path(args.state_dir) / "ready.json").read_text())
            return 0 if 0 <= time.time() - ready["time"] < args.max_age else 1
        except (OSError, ValueError, KeyError, TypeError):
            return 1
    if args.interval <= 0 or args.rpc_timeout <= 0:
        parser.error("interval and rpc-timeout must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    static_peers = peer_set(json.loads(Path(args.static_peers).read_text())) if args.static_peers else set()
    controller = Reconciler(IPC(args.ipc, args.rpc_timeout), args.allowlist, args.state_dir, static_peers)
    status = None
    while not stop.is_set():
        try:
            count = controller.reconcile()
            current = ("ok", count)
            if status != current:
                LOG.info("Allowlist reconciled: %d public keys", count)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            current = ("error", type(error).__name__, str(error))
            if status != current:
                LOG.warning("Allowlist reconciliation failed: %s", error)
        status = current
        stop.wait(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
