#!/usr/bin/env python3
"""Single-process health evaluation and durable status-page publication.

No management API credentials, no inbound public endpoint, no provider state reads.
Rules live beside this script. Grafana is not an input or publication gate.
"""
import copy
import datetime
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import status_page_health as health


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "scroll-sdk/status-page-delivery"})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as response:
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("response too large")
        return json.loads(raw) if payload is None else None


def observation(response, now, max_age, allow_partial=False):
    if response.get("status") != "success" or response.get("warnings"):
        return None
    data = response.get("data", {})
    samples = data.get("result", [])
    if data.get("resultType") != "vector" or len(samples) != 1:
        return None
    try:
        stamp, value = map(float, samples[0]["value"])
        if value not in ((0, 1, 2) if allow_partial else (0, 1)) or not math.isfinite(stamp) or not 0 <= now - stamp <= max_age:
            return None
        return int(value)
    except (KeyError, ValueError, TypeError):
        return None


def iso(stamp):
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class Delivery:
    def __init__(self, config, database, send=None):
        config = copy.deepcopy(config)
        self.config = {**config, "health": health.policy(config.get("health", {}))}
        self.components = config["components"]
        if (config["environment"] not in ("devnet", "testnet", "mainnet")
                or not str(config["chainId"]).isdigit() or len(self.components) > len(health.COMPONENTS)
                or self.components.keys() - set(health.COMPONENTS)):
            raise ValueError("invalid health scope")
        self.config.setdefault("intervalSeconds", 30)
        self.decisions = {}
        for component in self.components.values():
            if "expr" in component and "rule" not in component:
                component["rule"] = {"expr": component["expr"]}  # Read existing v2 journals/configs.
            component.setdefault("failureSeconds", health.seconds(component.get("rule", {}).get("for", self.config["health"]["failureFor"])))
            component.setdefault("recoverySeconds", health.seconds(self.config["health"]["recoveryFor"]))
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (key TEXT PRIMARY KEY, identity TEXT NOT NULL, active TEXT, pending TEXT)")
        self.memory = {}
        self.send = send or request_json
        self.last_tick = 0
        self.windows = config.get("maintenanceWindows", [])
        for window in self.windows:
            if (not isinstance(window.get("start"), (int, float)) or
                    not isinstance(window.get("end"), (int, float)) or
                    not math.isfinite(window["start"]) or not math.isfinite(window["end"]) or
                    window["end"] <= window["start"] or not isinstance(window.get("components"), list)):
                raise ValueError("invalid maintenance window")
        for key, component in self.components.items():
            identity = json.dumps([config["environment"], config["chainId"], component["pageId"], component["componentId"]])
            row = self.db.execute("SELECT identity FROM events WHERE key=?", (key,)).fetchone()
            if row and row[0] != identity:
                raise ValueError("delivery target changed: restore the original state and binding")
            if component.get("mode", "automatic") == "automatic":
                if not component["pageId"] or not component["componentId"]:
                    raise ValueError("automatic publication requires a bound component")
                self.db.execute("INSERT OR IGNORE INTO events VALUES (?, ?, NULL, NULL)", (key, identity))
        self.db.commit()

    def payload(self, key, now, active=None):
        component = self.components[key]
        status = "resolved" if active else "firing"
        identity = f'{self.config["environment"]}:{self.config["chainId"]}:{component["pageId"]}:{component["componentId"]}'
        fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:16]
        labels = {"alertname": f'{self.config["groupName"]} / {component["name"]}',
                  "component_key": key, "environment": self.config["environment"], "chain_id": self.config["chainId"]}
        start = active["alerts"][0]["startsAt"] if active else iso(now)
        return {"receiver": f"instatus-{key}", "status": status, "orgId": self.config["orgId"],
                "alerts": [{"status": status, "labels": labels, "annotations": {"summary": ", ".join(self.decisions.get(key, {}).get("reasons", []))}, "startsAt": start,
                            "endsAt": iso(now) if active else "0001-01-01T00:00:00Z", "fingerprint": fingerprint}],
                "groupLabels": labels, "commonLabels": labels, "commonAnnotations": {}, "externalURL": "",
                "version": "1", "groupKey": identity, "truncatedAlerts": 0,
                "title": f'{labels["alertname"]}: {"recovered" if active else "service disruption"}',
                "state": "ok" if active else "alerting", "message": "Continuous fresh health observations confirm recovery." if active else "Service disruption confirmed by health observations."}

    def tick(self, samples, now):
        with self.lock:
            for key, component in self.components.items():
                state = self.memory.setdefault(key, {})
                state["maintenance"] = any(key in w["components"] and w["start"] <= now < w["end"] for w in self.windows)
                if state["maintenance"]:
                    # Preserve durable active/pending identity; never create or
                    # resolve incidents inside the window. Restart confirmation
                    # from fresh evidence after the window, including restarts.
                    state.update(last=now, value=None, since=now)
                    continue
                value = samples.get(key)
                if value not in (0, 1):
                    value = None
                gap = now - state.get("last", now)
                if value is None or gap < 0 or gap > self.config["intervalSeconds"] * 2 or value != state.get("value"):
                    state["since"] = now
                state.update(last=now, value=value)
                if component.get("mode", "automatic") != "automatic":
                    continue
                active_raw, pending_raw = self.db.execute("SELECT active, pending FROM events WHERE key=?", (key,)).fetchone()
                active = json.loads(active_raw) if active_raw else None
                pending = json.loads(pending_raw) if pending_raw else None
                delay = component["failureSeconds"] if value == 1 else component["recoverySeconds"]
                if value is None or now - state.get("since", now) < delay:
                    continue
                # An uncertain HTTP response may already have created an incident.
                # Deliver that same stable event before any corresponding recovery.
                if pending and ((pending["status"] == "firing") != bool(value)):
                    continue
                if pending is None:
                    if value == 1 and active is None:
                        pending = self.payload(key, now)
                    elif value == 0 and active is not None:
                        pending = self.payload(key, now, active)
                    else:
                        continue
                    self.db.execute("UPDATE events SET pending=? WHERE key=?", (json.dumps(pending), key))
                    self.db.commit()  # persist intent BEFORE sending
                try:
                    self.send(os.environ[component["webhookEnv"]], pending)
                except Exception:
                    state["delivery_error"] = 1  # Never log URLs or response bodies.
                    continue
                self.db.execute("UPDATE events SET active=?, pending=NULL WHERE key=?",
                                (json.dumps(pending) if value == 1 else None, key))
                self.db.commit()
                state["delivery_error"] = 0
            self.last_tick = now

    def collect(self):
        # At most ten distinct requests for the built-ins; shared WF evidence is
        # fetched once. No core DB access, no per-rule background workers.
        plan = {key: health.queries(self.config, key) for key in self.components}
        expressions = {expr for rules in plan.values() for expr in rules.values() if expr}
        def query(expr):
            try:
                now = time.time()
                url = self.config["prometheusUrl"].rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": now, "timeout": "8s"})
                return expr, observation(request_json(url), time.time(), self.config["intervalSeconds"] * 2, allow_partial=True)
            except Exception:
                return expr, None
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = dict(workers.map(query, expressions))
        now = time.time()
        decisions = {key: health.evaluate({rule: (None if rule == "custom" and results.get(expr) == 2 else results.get(expr))
                                           for rule, expr in rules.items()})
                     for key, rules in plan.items()}
        for key, item in decisions.items():
            item["monitoringRequired"] = bool(plan[key]) or self.components[key].get("mode", "automatic") == "automatic"
        with self.lock:
            self.decisions = decisions
            self.tick({key: None if item["status"] == "unknown" else int(item["status"] != "operational")
                   for key, item in decisions.items()}, now)
        # Heartbeat proves this evaluator completed a tick. Missing observations
        # withhold it; known business failures do not pretend monitoring is dead.
        monitored = [item for key, item in decisions.items()
                     if self.components[key].get("mode", "automatic") != "manual"
                     and (plan[key] or self.components[key].get("mode", "automatic") == "automatic")]
        if self.config.get("heartbeatEnabled") and monitored and not any(s.get("delivery_error") for s in self.memory.values()) and all(item["observation"] == "complete" for item in monitored):
            try:
                self.send(os.environ["INSTATUS_MONITORING_HEARTBEAT_URL"], {"status": "firing", "alerts": [{"status": "firing", "labels": {"alertname": "monitoring-heartbeat", "environment": self.config["environment"]}}]})
            except Exception:
                pass  # Instatus independently expires its heartbeat; no false success.

    def metrics(self):
        with self.lock:
            lines = [f"scroll_status_delivery_last_tick_seconds {self.last_tick}"]
            for key, state in self.memory.items():
                labels = f'component_key="{key}"'
                lines.append(f'scroll_status_delivery_observation_known{{{labels}}} {int(state.get("value") is not None)}')
                lines.append(f'scroll_status_delivery_error{{{labels}}} {state.get("delivery_error", 0)}')
                lines.append(f'scroll_status_delivery_maintenance{{{labels}}} {int(state.get("maintenance", False))}')
                active, pending = self.db.execute("SELECT active, pending FROM events WHERE key=?", (key,)).fetchone() or (None, None)
                lines.append(f'scroll_status_delivery_pending{{{labels}}} {int(pending is not None)}')
                lines.append(f'scroll_status_delivery_incident_active{{{labels}}} {int(active is not None)}')
            identity = f'environment="{self.config["environment"]}",chain_id="{self.config["chainId"]}"'
            lines.append(f"scroll_status_health_evaluated_timestamp_seconds{{{identity}}} {self.last_tick}")
            for key, decision in self.decisions.items():
                lines.append(f'scroll_status_health_monitoring_required{{{identity},component_key="{key}"}} {int(decision["monitoringRequired"])}')
                for status in ("operational", "degraded", "unavailable", "unknown"):
                    lines.append(f'scroll_status_health{{{identity},component_key="{key}",status="{status}"}} {int(decision["status"] == status)}')
                lines.append(f'scroll_status_health_observation_complete{{{identity},component_key="{key}"}} {int(decision["observation"] == "complete")}')
            return "\n".join(lines) + "\n"


def main():
    with open("/config/delivery.json") as file:
        config = json.load(file)
    delivery = Delivery(config, "/state/delivery.sqlite3")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/metrics":
                body, code = delivery.metrics().encode(), 200
            elif self.path == "/health":
                with delivery.lock:
                    body = json.dumps({"environment": config["environment"], "chainId": config["chainId"],
                        "evaluatedAt": delivery.last_tick, "validUntil": delivery.last_tick + 2 * delivery.config["intervalSeconds"],
                        "components": delivery.decisions}).encode()
                code = 200 if delivery.last_tick > 0 and 0 <= time.time() - delivery.last_tick <= 2 * delivery.config["intervalSeconds"] else 503
            elif self.path == "/healthz":
                body, code = b"ok\n", 200 if 0 <= time.time() - delivery.last_tick < 120 else 503
            else:
                body, code = b"not found\n", 404
            self.send_response(code)
            self.send_header("Content-Type", "application/json" if self.path == "/health" else "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body)

    def worker():
        while True:
            delivery.collect()
            time.sleep(delivery.config["intervalSeconds"])
    threading.Thread(target=worker, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", 9110), Handler)
    server.timeout = 10
    server.serve_forever()


if __name__ == "__main__":
    main()
