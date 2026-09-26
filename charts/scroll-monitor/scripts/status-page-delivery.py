#!/usr/bin/env python3
"""Durable, evidence-checked delivery of component-scoped Grafana notifications.

No management API credentials, no inbound public endpoint, no provider state reads.
Raw Grafana resolved notifications never resolve a public incident.
"""
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as response:
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("response too large")
        return json.loads(raw) if payload is None else None


def observation(response, now, max_age):
    if response.get("status") != "success" or response.get("warnings"):
        return None
    data = response.get("data", {})
    samples = data.get("result", [])
    if data.get("resultType") != "vector" or len(samples) != 1:
        return None
    try:
        stamp, value = map(float, samples[0]["value"])
        if value not in (0, 1) or not math.isfinite(stamp) or not 0 <= now - stamp <= max_age:
            return None
        return int(value)
    except (KeyError, ValueError, TypeError):
        return None


def iso(stamp):
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class Delivery:
    def __init__(self, config, database, send=None):
        self.config = config
        self.components = config["components"]
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (key TEXT PRIMARY KEY, identity TEXT NOT NULL, active TEXT, pending TEXT)")
        self.memory = {}
        self.send = send or request_json
        self.last_tick = 0
        for key, component in self.components.items():
            identity = json.dumps([config["environment"], config["chainId"], component["pageId"], component["componentId"]])
            row = self.db.execute("SELECT identity FROM events WHERE key=?", (key,)).fetchone()
            if row and row[0] != identity:
                raise ValueError("delivery target changed: restore the original state and binding")
            self.db.execute("INSERT OR IGNORE INTO events VALUES (?, ?, NULL, NULL)", (key, identity))
        self.db.commit()

    def notify(self, key, body, now):
        # Never trust transport status as business recovery. No raw incident text,
        # annotations, URLs or labels from Grafana are copied to the public payload.
        component = self.components.get(key)
        if component is None or body.get("status") != "firing":
            return False
        expected = {"component_key": key, "environment": self.config["environment"],
                    "chain_id": self.config["chainId"], "managed_by": "scroll-sdk-status-page",
                    "audience": "public-status"}
        alerts = body.get("alerts")
        if not isinstance(alerts, list) or len(alerts) != 1 or body.get("truncatedAlerts", 0):
            return False
        alert = alerts[0]
        if not isinstance(alert, dict) or alert.get("status") != "firing" or any(alert.get("labels", {}).get(k) != v for k, v in expected.items()):
            return False
        with self.lock:
            self.memory.setdefault(key, {})["armed"] = now
        return True

    def payload(self, key, now, active=None):
        component = self.components[key]
        status = "resolved" if active else "firing"
        identity = f'{self.config["environment"]}:{self.config["chainId"]}:{component["pageId"]}:{component["componentId"]}'
        fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:16]
        labels = {"alertname": f'{self.config["groupName"]} / {component["name"]}',
                  "component_key": key, "environment": self.config["environment"], "chain_id": self.config["chainId"]}
        start = active["alerts"][0]["startsAt"] if active else iso(now)
        return {"receiver": f"instatus-{key}", "status": status, "orgId": self.config["orgId"],
                "alerts": [{"status": status, "labels": labels, "annotations": {}, "startsAt": start,
                            "endsAt": iso(now) if active else "0001-01-01T00:00:00Z", "fingerprint": fingerprint}],
                "groupLabels": labels, "commonLabels": labels, "commonAnnotations": {}, "externalURL": "",
                "version": "1", "groupKey": identity, "truncatedAlerts": 0,
                "title": f'{labels["alertname"]}: {"recovered" if active else "service disruption"}',
                "state": "ok" if active else "alerting", "message": "Continuous fresh health observations confirm recovery." if active else "Service disruption confirmed by health observations."}

    def tick(self, samples, now):
        with self.lock:
            for key, component in self.components.items():
                state = self.memory.setdefault(key, {})
                value = samples.get(key)
                if value not in (0, 1):
                    value = None
                gap = now - state.get("last", now)
                if value is None or gap < 0 or gap > self.config["intervalSeconds"] * 2 or value != state.get("value"):
                    state["since"] = now
                state.update(last=now, value=value)
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
                    if value == 1 and active is None and 0 <= now - state.get("armed", -1e20) <= 18000:
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
                if value == 0:
                    state.pop("armed", None)
            self.last_tick = now

    def collect(self):
        def query(item):
            key, component = item
            try:
                now = time.time()
                url = self.config["prometheusUrl"].rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": component["expr"], "time": now})
                return key, observation(request_json(url), time.time(), self.config["intervalSeconds"] * 2)
            except Exception:
                return key, None
        with ThreadPoolExecutor(max_workers=8) as workers:
            samples = dict(workers.map(query, self.components.items()))
        self.tick(samples, time.time())

    def metrics(self):
        with self.lock:
            lines = [f"scroll_status_delivery_last_tick_seconds {self.last_tick}"]
            for key, state in self.memory.items():
                labels = f'component_key="{key}"'
                lines.append(f'scroll_status_delivery_observation_known{{{labels}}} {int(state.get("value") is not None)}')
                lines.append(f'scroll_status_delivery_error{{{labels}}} {state.get("delivery_error", 0)}')
                active, pending = self.db.execute("SELECT active, pending FROM events WHERE key=?", (key,)).fetchone()
                lines.append(f'scroll_status_delivery_pending{{{labels}}} {int(pending is not None)}')
                lines.append(f'scroll_status_delivery_incident_active{{{labels}}} {int(active is not None)}')
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
            elif self.path == "/healthz":
                body, code = b"ok\n", 200 if 0 <= time.time() - delivery.last_tick < 120 else 503
            else:
                body, code = b"not found\n", 404
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536 or not self.path.startswith("/notify/"):
                    raise ValueError("invalid request")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("invalid body")
                delivery.notify(self.path.removeprefix("/notify/"), body, time.time())
                code = 202
            except (ValueError, TypeError, AttributeError):
                code = 400
            self.send_response(code)
            self.end_headers()

    def worker():
        while True:
            delivery.collect()
            time.sleep(config["intervalSeconds"])
    threading.Thread(target=worker, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", 9110), Handler)
    server.timeout = 10
    server.serve_forever()


if __name__ == "__main__":
    main()
