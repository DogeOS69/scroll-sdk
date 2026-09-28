#!/usr/bin/env python3
"""Read-only, per-Pod official follower checks. Unknown rounds never emit healthy."""
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener


class Unknown(Exception):
    pass


def quantity(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise Unknown("invalid_quantity")
    return int(value, 16)


def block(value, expected=None):
    if not isinstance(value, dict):
        raise Unknown("missing_block")
    number, timestamp = quantity(value.get("number")), quantity(value.get("timestamp"))
    digest = value.get("hash")
    if not isinstance(digest, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", digest):
        raise Unknown("invalid_hash")
    if expected is not None and number != expected:
        raise Unknown("wrong_height")
    return number, timestamp, digest.lower()


def members(document, port):
    """Deduplicate dual-stack/slice overlap by immutable Pod UID; fail closed."""
    if document.get("metadata", {}).get("continue"):
        raise Unknown("truncated_discovery")
    found = {}
    for item in document["items"]:
        if item.get("addressType") not in ("IPv4", "IPv6"):
            raise Unknown("unsupported_address_type")
        if not any(p.get("port") == port and p.get("protocol", "TCP") == "TCP" for p in item.get("ports", [])):
            raise Unknown("missing_rpc_port")
        for entry in item.get("endpoints", []):
            target = entry.get("targetRef", {})
            if target.get("kind") != "Pod" or not target.get("uid") or not target.get("name"):
                raise Unknown("missing_pod_identity")
            condition = entry.get("conditions", {})
            ready = condition.get("ready") is True and condition.get("terminating") is not True
            addresses = sorted(str(ipaddress.ip_address(a)) for a in entry["addresses"])
            if not addresses:
                raise Unknown("missing_address")
            key = target["uid"]
            if key in found:
                if found[key]["ready"] != ready or found[key]["name"] != target["name"]:
                    raise Unknown("conflicting_discovery")
                found[key]["addresses"] = sorted(set(found[key]["addresses"] + addresses))
            else:
                found[key] = {"addresses": addresses, "name": target["name"], "ready": ready, "uid": key}
    return sorted(found.values(), key=lambda item: item["uid"])


class Client:
    def __init__(self, namespace):
        self.namespace = namespace
        self.token = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
        context = ssl.create_default_context(cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
        host = os.environ["KUBERNETES_SERVICE_HOST"]
        if ":" in host:
            host = f"[{host}]"
        self.api = f"https://{host}:{os.environ.get('KUBERNETES_SERVICE_PORT_HTTPS', '443')}"
        self.deadline = 0

    def request(self, url, data=None, headers=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Unknown("round_timeout")
        request = Request(url, data=json.dumps(data).encode() if data is not None else None,
                          headers={"Content-Type": "application/json", **(headers or {})})
        with self.opener.open(request, timeout=min(5, remaining)) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024 or time.monotonic() > self.deadline:
            raise Unknown("response_limit")
        return json.loads(raw)

    def discover(self, source):
        query = urlencode({"labelSelector": f"kubernetes.io/service-name={source['service']}"})
        result = self.request(f"{self.api}/apis/discovery.k8s.io/v1/namespaces/{self.namespace}/endpointslices?{query}",
                              headers={"Authorization": f"Bearer {self.token.read_text().strip()}"})
        return members(result, source["port"])

    def rpc(self, pod, source, method, params):
        address = pod["addresses"][0]
        if ":" in address:
            address = f"[{address}]"
        response = self.request(f"http://{address}:{source['port']}",
                                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if response.get("jsonrpc") != "2.0" or response.get("id") != 1 or "error" in response or "result" not in response:
            raise Unknown("rpc_error")
        return response["result"]


def observe(config, client, now=None):
    clock = time.time if now is None else lambda: now
    sources = [config["reference"], *config["followers"]]
    snapshots = [client.discover(source) for source in sources]
    # Exact completeness prevents scale-up, deleted Pods and selector mistakes
    # from silently reducing the observed population.
    if any(len(pods) != source["replicas"] for source, pods in zip(sources, snapshots)):
        raise Unknown("incomplete_population")
    all_uids = [pod["uid"] for pods in snapshots for pod in pods]
    if len(set(all_uids)) != len(all_uids):
        raise Unknown("overlapping_services")
    reference = snapshots[0]
    if len(reference) != 1 or not reference[0]["ready"]:
        raise Unknown("reference_not_ready")
    ref = reference[0]
    ref_source = sources[0]
    rpc = lambda pod, src, method, params: client.rpc(pod, src, method, params)
    if quantity(rpc(ref, ref_source, "eth_chainId", [])) != int(config["chainId"]):
        raise Unknown("reference_wrong_chain")
    head = block(rpc(ref, ref_source, "eth_getBlockByNumber", ["latest", False]))
    if not 0 <= clock() - head[1] <= config["maxBlockAgeSeconds"]:
        raise Unknown("reference_stale")
    results = []
    for source, pods in zip(sources[1:], snapshots[1:]):
        for pod in pods:
            if not pod["ready"]:
                results.append((source["role"], pod["name"], 1, "not_ready"))
                continue
            if quantity(rpc(pod, source, "eth_chainId", [])) != int(config["chainId"]):
                results.append((source["role"], pod["name"], 1, "wrong_chain"))
                continue
            follower = block(rpc(pod, source, "eth_getBlockByNumber", ["latest", False]))
            height = min(head[0], follower[0])
            canonical = head if height == head[0] else block(rpc(ref, ref_source, "eth_getBlockByNumber", [hex(height), False]), height)
            compared = follower if height == follower[0] else block(rpc(pod, source, "eth_getBlockByNumber", [hex(height), False]), height)
            if canonical[1] > head[1] or follower[1] > clock():
                raise Unknown("invalid_block_time")
            # Re-read the follower at the comparison height too: a reorg during
            # sampling must not be published as a persistent fork or recovery.
            if block(rpc(pod, source, "eth_getBlockByNumber", [hex(height), False]), height) != compared:
                raise Unknown("follower_reorg")
            mismatch = canonical[2] != compared[2]
            if not mismatch and canonical[1] != compared[1]:
                raise Unknown("invalid_block_time")
            lag = max(0, head[1] - canonical[1])
            affected = mismatch or lag > config["maxNodeLagSeconds"]
            results.append((source["role"], pod["name"], int(affected), "hash_mismatch" if mismatch else "lag" if affected else "healthy"))
    # Fence the entire round against reference reorgs and changes to membership.
    if block(rpc(ref, ref_source, "eth_getBlockByNumber", [hex(head[0]), False]), head[0]) != head:
        raise Unknown("reference_reorg")
    if [client.discover(source) for source in sources] != snapshots:
        raise Unknown("population_changed")
    if not 0 <= clock() - head[1] <= config["maxBlockAgeSeconds"]:
        raise Unknown("reference_stale")
    if not results:
        raise Unknown("no_followers")
    return results


def sequencing(config, client, now=None):
    """Reference-only observation; follower failures cannot classify the sequencer.

    A reachable, correctly identified reference with an old head is affected.
    Missing discovery/RPC evidence is unknown, not an asserted sequencer outage.
    """
    source = config["reference"]
    pods = client.discover(source)
    if len(pods) != 1 or not pods[0]["ready"]:
        raise Unknown("reference_not_ready")
    pod = pods[0]
    if quantity(client.rpc(pod, source, "eth_chainId", [])) != int(config["chainId"]):
        raise Unknown("reference_wrong_chain")
    head = block(client.rpc(pod, source, "eth_getBlockByNumber", ["latest", False]))
    if client.discover(source) != pods:
        raise Unknown("population_changed")
    age = (time.time() if now is None else now) - head[1]
    if age < 0:
        raise Unknown("future_block_time")
    return int(age > config["maxBlockAgeSeconds"])


def metrics(config, results, observed, reason="unknown", sequence=None):
    identity = {"environment": config["environment"], "chain_id": config["chainId"], "component_key": "node-sync"}
    labels = lambda fields: ",".join(f"{key}={json.dumps(str(value))}" for key, value in fields.items())
    lines = [f"scroll_status_node_sync_timestamp_seconds{{{labels(identity)}}} {observed}"]
    lines.append(f"scroll_status_node_sync_observation_valid{{{labels({**identity, 'reason': 'complete' if results is not None else reason})}}} {int(results is not None)}")
    if results is not None:
        lines.append(f"scroll_status_node_sync_affected{{{labels(identity)}}} {max(row[2] for row in results)}")
        for role, pod, affected, reason in results:
            lines.append(f"scroll_status_node_sync_member_affected{{{labels({**identity, 'role': role, 'pod_name': pod, 'reason': reason})}}} {affected}")
    seq_identity = {**identity, "component_key": "sequencing"}
    lines.append(f"scroll_status_sequencing_timestamp_seconds{{{labels(seq_identity)}}} {observed}")
    if sequence is not None:
        lines.append(f"scroll_status_sequencing_affected{{{labels(seq_identity)}}} {sequence}")
    return ("\n".join(lines) + "\n").encode()


def main():
    config = json.loads(Path("/config/node-sync.json").read_text())
    client = Client(os.environ["NODE_NAMESPACE"])
    state = {"body": metrics(config, None, 0), "tick": time.monotonic()}
    lock = threading.Lock()

    def loop():
        while True:
            start = time.monotonic()
            observed = time.time()  # Never rejuvenate an old round with its completion time.
            client.deadline = start + 60
            try:
                sequence = sequencing(config, client)
            except Exception:
                sequence = None
            try:
                results = observe(config, client)
                reason = "complete"
            except Exception as error:
                # Never log URLs, responses or tokens. Missing evidence goes to
                # the existing internal observation-missing rule.
                results = None
                reason = str(error) if isinstance(error, Unknown) else "request_or_decode_error"
            with lock:
                state.update(body=metrics(config, results, observed, reason, sequence), tick=time.monotonic())
            time.sleep(max(1, 30 - (time.monotonic() - start)))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                body, age = state["body"], time.monotonic() - state["tick"]
            if self.path == "/metrics":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(200 if self.path == "/healthz" and age < 120 else 503)
                self.end_headers()

        def log_message(self, *_args):
            pass

    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 9112), Handler).serve_forever()


if __name__ == "__main__":
    main()
