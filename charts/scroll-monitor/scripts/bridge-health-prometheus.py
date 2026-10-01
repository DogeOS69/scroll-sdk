#!/usr/bin/env python3
"""Read-only Prometheus adapter for DogeOS signing snapshot v1.

This supplies signing evidence, never a deposit/withdrawal health verdict.
No credentials for core, signers or Status Page are accepted or used.
"""
import argparse
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler

PREFIX = "tso_core_signing_"
ROLES = ("correctness", "attestation")
STATES = ("satisfied", "pending", "unreachable")
BASE = ("snapshot_schema_version", "observer_start_timestamp_seconds", "snapshot_valid",
        "snapshot_timestamp_seconds", "active_transactions", "unclassified_transactions")
NAMES = ("up",) + tuple(PREFIX + name for name in BASE +
                         ("quorum_transactions", "waiting_transactions", "oldest_wait_seconds"))


class InvalidObservation(ValueError):
    pass


def finite(value):
    if isinstance(value, bool):
        raise InvalidObservation("invalid_number")
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise InvalidObservation("invalid_number") from error
    if not math.isfinite(value) or value < 0:
        raise InvalidObservation("invalid_number")
    return value


def count(value):
    value = finite(value)
    if value != int(value) or value > 2 ** 53 - 1:
        raise InvalidObservation("invalid_count")
    return int(value)


def config(raw):
    allowed = {"prometheusUrl", "environment", "chainId", "namespace", "job", "expectedTargets",
               "intervalSeconds", "freshnessSeconds", "timeoutSeconds"}
    if not isinstance(raw, dict) or raw.keys() - allowed:
        raise ValueError("unsupported adapter configuration")
    result = {"intervalSeconds": 30, "freshnessSeconds": 120, "timeoutSeconds": 5, **raw}
    for key in ("prometheusUrl", "environment", "chainId", "namespace", "job"):
        if not isinstance(result.get(key), str) or not result[key]:
            raise ValueError(f"{key} is required")
    url = urlsplit(result["prometheusUrl"])
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("prometheusUrl must be an HTTP(S) base URL without credentials/query/fragment")
    if result["environment"] not in ("devnet", "testnet", "mainnet") or not result["chainId"].isdigit():
        raise ValueError("explicit environment and numeric chainId are required")
    for key, minimum, maximum in (("expectedTargets", 1, 32), ("intervalSeconds", 5, 300),
                                  ("freshnessSeconds", 10, 3600), ("timeoutSeconds", 1, 30)):
        if type(result.get(key)) is not int or not minimum <= result[key] <= maximum:
            raise ValueError(f"invalid {key}")
    if result["timeoutSeconds"] >= result["intervalSeconds"] or result["freshnessSeconds"] < 2 * result["intervalSeconds"]:
        raise ValueError("require timeout < interval and freshness >= 2 * interval")
    return result


def query(cfg):
    # Exact namespace/job selectors avoid crossing chains or silently merging HA
    # targets. JSON string encoding is also valid PromQL string escaping.
    return '{__name__=~' + json.dumps("|".join(NAMES)) + ',namespace=' + json.dumps(cfg["namespace"]) + ',job=' + json.dumps(cfg["job"]) + '}'


def normalize(payload, cfg, now):
    if not isinstance(payload, dict) or payload.get("status") != "success" or payload.get("warnings"):
        raise InvalidObservation("query_failed")
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector" or not isinstance(data.get("result"), list):
        raise InvalidObservation("invalid_vector")
    groups = {}
    for row in data["result"]:
        if not isinstance(row, dict) or not isinstance(row.get("metric"), dict):
            raise InvalidObservation("invalid_series")
        labels = row["metric"]
        name, instance = labels.get("__name__"), labels.get("instance")
        if name not in NAMES or not isinstance(instance, str) or not instance or len(instance) > 512:
            raise InvalidObservation("unexpected_series")
        if labels.get("namespace") != cfg["namespace"] or labels.get("job") != cfg["job"]:
            raise InvalidObservation("wrong_scope")
        sample = row.get("value")
        if not isinstance(sample, list) or len(sample) != 2 or not isinstance(sample[1], str):
            raise InvalidObservation("invalid_sample")
        stamp, value = finite(sample[0]), finite(sample[1])
        if not -5 <= now - stamp < cfg["freshnessSeconds"]:
            raise InvalidObservation("stale_sample")
        role, state = labels.get("role"), labels.get("state")
        if name == PREFIX + "quorum_transactions":
            if role not in ROLES or state not in STATES:
                raise InvalidObservation("invalid_labels")
        elif name in (PREFIX + "waiting_transactions", PREFIX + "oldest_wait_seconds"):
            if role not in ROLES or state is not None:
                raise InvalidObservation("invalid_labels")
        elif role is not None or state is not None:
            raise InvalidObservation("invalid_labels")
        key = (name, role, state)
        group = groups.setdefault(instance, {})
        if key in group:
            raise InvalidObservation("duplicate_series")
        group[key] = value
    if len(groups) != cfg["expectedTargets"]:
        raise InvalidObservation("target_inventory_incomplete")
    sources = []
    for instance, values in sorted(groups.items()):
        def get(name, role=None, state=None):
            try:
                return values[(name if name == "up" else PREFIX + name, role, state)]
            except KeyError as error:
                raise InvalidObservation("missing_metric") from error
        if get("up") != 1:
            raise InvalidObservation("target_unobserved")
        if get("snapshot_schema_version") != 1:
            raise InvalidObservation("unsupported_schema")
        if get("snapshot_valid") != 1:
            raise InvalidObservation("invalid_snapshot")
        observed, boot = get("snapshot_timestamp_seconds"), get("observer_start_timestamp_seconds")
        if not -5 <= now - observed < cfg["freshnessSeconds"] or boot <= 0 or boot > now + 5:
            raise InvalidObservation("stale_snapshot")
        active, unclassified = count(get("active_transactions")), count(get("unclassified_transactions"))
        if unclassified > active:
            raise InvalidObservation("inconsistent_counts")
        roles = {}
        for role in ROLES:
            states = {state: count(get("quorum_transactions", role, state)) for state in STATES}
            pending, age = count(get("waiting_transactions", role)), get("oldest_wait_seconds", role)
            if sum(states.values()) != active - unclassified or pending != states["pending"] + states["unreachable"] or (pending == 0 and age != 0):
                raise InvalidObservation("inconsistent_counts")
            roles[role] = {"transactions": states, "waiting": pending, "oldestWaitSeconds": age}
        sources.append({"instance": instance, "observerStart": boot, "observedAt": observed,
                        "activeTransactions": active, "unclassifiedTransactions": unclassified, "roles": roles})
    return {"schemaVersion": 1, "environment": cfg["environment"], "chainId": cfg["chainId"],
            "coverage": "tso_signing_only", "businessStatus": "unknown", "observationValid": True,
            "coverageComplete": all(source["unclassifiedTransactions"] == 0 for source in sources),
            "validUntil": min(source["observedAt"] + cfg["freshnessSeconds"] for source in sources), "sources": sources}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def collect(cfg, now=None, fetch=None):
    now = time.time() if now is None else now
    url = cfg["prometheusUrl"].rstrip("/") + "/api/v1/query?" + urlencode({"query": query(cfg), "time": now})
    def request(url):
        with build_opener(NoRedirect).open(url, timeout=cfg["timeoutSeconds"]) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise InvalidObservation("response_too_large")
            return json.loads(body)
    try:
        return normalize((fetch or request)(url), cfg, now)
    except (ValueError, KeyError, TypeError, OSError, HTTPException) as error:
        # Fixed error codes only. Never log request URLs or response bodies.
        reason = str(error) if isinstance(error, InvalidObservation) else "collection_failed"
        return {"schemaVersion": 1, "environment": cfg["environment"], "chainId": cfg["chainId"],
                "coverage": "tso_signing_only", "businessStatus": "unknown", "observationValid": False,
                "coverageComplete": False, "validUntil": now, "reason": reason, "sources": []}


def metric_quote(value):
    # Prometheus text supports only backslash, quote and newline escapes;
    # JSON's ASCII unicode escapes would corrupt non-ASCII instance labels.
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def metrics(snapshot, now):
    valid = snapshot.get("observationValid", False) and now < snapshot.get("validUntil", 0)
    labels = 'environment=' + metric_quote(snapshot["environment"]) + ',chain_id=' + metric_quote(snapshot["chainId"])
    lines = [f'scroll_bridge_signing_observation_valid{{{labels}}} {int(valid)}',
             f'scroll_bridge_signing_coverage_complete{{{labels}}} {int(valid and snapshot.get("coverageComplete", False))}']
    if valid:
        for source in snapshot["sources"]:
            scoped = labels + ',source_instance=' + metric_quote(source["instance"])
            lines.append(f'scroll_bridge_signing_observed_timestamp_seconds{{{scoped}}} {source["observedAt"]}')
            lines.append(f'scroll_bridge_signing_observer_start_timestamp_seconds{{{scoped}}} {source["observerStart"]}')
            lines.append(f'scroll_bridge_signing_active_transactions{{{scoped}}} {source["activeTransactions"]}')
            lines.append(f'scroll_bridge_signing_unclassified_transactions{{{scoped}}} {source["unclassifiedTransactions"]}')
            for role, values in source["roles"].items():
                for state, count in values["transactions"].items():
                    lines.append(f'scroll_bridge_signing_quorum_transactions{{{scoped},role="{role}",state="{state}"}} {count}')
                lines.append(f'scroll_bridge_signing_waiting_transactions{{{scoped},role="{role}"}} {values["waiting"]}')
                lines.append(f'scroll_bridge_signing_oldest_wait_seconds{{{scoped},role="{role}"}} {values["oldestWaitSeconds"]}')
    return "\n".join(lines) + "\n"


def serve(cfg, port):
    lock = threading.Lock()
    current = collect(cfg, fetch=lambda _: {})
    last_tick = 0
    def loop():
        nonlocal current, last_tick
        while True:
            started = time.monotonic()
            result = collect(cfg)
            with lock:
                current, last_tick = result, time.monotonic()
            time.sleep(max(0, cfg["intervalSeconds"] - (time.monotonic() - started)))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                snapshot, tick = current, last_tick
            if self.path == "/metrics":
                body, status, mime = metrics(snapshot, time.time()), 200, "text/plain; version=0.0.4"
            elif self.path == "/healthz":
                status = 200 if tick and time.monotonic() - tick < 2 * cfg["intervalSeconds"] else 503
                body, mime = "ok\n" if status == 200 else "waiting\n", "text/plain"
            else:
                body, status, mime = "not found\n", 404, "text/plain"
            body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=loop, daemon=True).start()
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=9112)
    args = parser.parse_args()
    cfg = config(json.loads(args.config.read_text()))
    if args.serve:
        serve(cfg, args.port)
    else:
        print(json.dumps(collect(cfg), sort_keys=True))


if __name__ == "__main__":
    main()
