#!/usr/bin/env python3
"""Seed UI-editable Grafana rules without replacing operators' existing rules."""

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASELINE = "__scroll_monitor_last_applied__"
ALERTMANAGER_CONFIG_PATH = "/api/alertmanager/grafana/config/api/v1/alerts"
TEMPLATE_MARKER = re.compile(r"\{\{/\* scroll-monitor managed template sha256=([0-9a-f]{64}) \*/\}\}\n")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def managed_fields(rule):
    """Only manage expression A, pending period and chart annotations.

    Pause, routing, labels, group interval, and expression pipeline B/C remain
    operator-owned. Include the datasource in A's fingerprint so a UI datasource
    change prevents an expression update against a different source.
    """
    queries = [q for q in rule.get("data", []) if q.get("refId") == "A"]
    fields = {"for": rule.get("for", "0s")}
    if len(queries) == 1:
        fields["queryA"] = {
            "expr": queries[0].get("model", {}).get("expr"),
            "datasourceUid": queries[0].get("datasourceUid"),
        }
    for key, value in rule.get("annotations", {}).items():
        if key != BASELINE:
            fields["annotation:" + key] = value
    return fields


def reconcile_rule(existing, source, desired, pause=None):
    """Three-way merge; unknown legacy differences are reported, never guessed."""
    if existing.get("labels", {}).get("managed_by") != "scroll-monitor":
        print(f'DRIFT {desired["title"]}: UID belongs to an unmanaged rule; preserved', flush=True)
        return None
    updated = migrate_expression(existing, source, desired) or copy.deepcopy(existing)
    try:
        baseline = json.loads(existing.get("annotations", {}).get(BASELINE, "{}"))
        if not isinstance(baseline, dict):
            baseline = {}
    except (ValueError, TypeError):
        baseline = {}
    current_fields = managed_fields(updated)
    desired_fields = managed_fields(desired)
    changed = []
    conflicts = []
    # Track only known untouched fields; never adopt a differing legacy field.
    next_baseline = {k: v for k, v in baseline.items() if k in desired_fields}
    for field, target in desired_fields.items():
        current = current_fields.get(field)
        if current == target:
            next_baseline[field] = fingerprint(target)
            continue
        if field not in baseline or fingerprint(current) != baseline[field]:
            conflicts.append(field)
            continue
        if field == "queryA":
            for query in updated["data"]:
                if query.get("refId") == "A":
                    query["model"]["expr"] = target["expr"]
                    query["datasourceUid"] = target["datasourceUid"]
                    if "datasource" in query["model"]:
                        query["model"]["datasource"]["uid"] = target["datasourceUid"]
        elif field == "for":
            updated["for"] = target
        else:
            updated.setdefault("annotations", {})[field.removeprefix("annotation:")] = target
        next_baseline[field] = fingerprint(target)
        changed.append(field)
    if pause is not None and updated.get("isPaused", False) != pause:
        updated["isPaused"] = pause
        changed.append("isPaused (explicit override)")
    updated.setdefault("annotations", {})[BASELINE] = json.dumps(next_baseline, sort_keys=True)
    if conflicts:
        print(f'DRIFT {desired["title"]}: preserved UI/legacy differences in {", ".join(conflicts)}', flush=True)
    if "notification_settings" in desired and updated.get("notification_settings") != desired["notification_settings"]:
        updated["notification_settings"] = copy.deepcopy(desired["notification_settings"])
        changed.append("notification_settings (explicit backend selection)")
    if changed:
        print(f'UPDATE {desired["title"]}: {", ".join(changed)}', flush=True)
    if updated == existing:
        return None
    for field in ("id", "updated", "provenance"):
        updated.pop(field, None)
    return updated


class Grafana:
    def __init__(self):
        self.url = os.environ["GRAFANA_URL"].rstrip("/")
        token = os.environ.get("GRAFANA_TOKEN")
        if token:
            auth = f"Bearer {token}"
        else:
            credentials = f'{os.environ["GRAFANA_USER"]}:{os.environ["GRAFANA_PASSWORD"]}'
            auth = "Basic " + base64.b64encode(credentials.encode()).decode()
        self.headers = {
            "Authorization": auth,
            "Content-Type": "application/json",
            # File provisioning locks alert resources in the UI. This API
            # header makes the entire group editable, including pause/resume.
            "X-Disable-Provenance": "true",
            "X-Grafana-Org-Id": "1",
        }

    def request(self, method, path, body=None, allow_missing=False):
        request = Request(
            self.url + path,
            data=None if body is None else json.dumps(body).encode(),
            headers=self.headers,
            method=method,
        )
        for attempt in range(30):
            try:
                with urlopen(request, timeout=10) as response:
                    data = response.read()
                    return json.loads(data) if data else None
            except HTTPError as error:
                if allow_missing and error.code == 404:
                    return None
                if error.code < 500 or (method == "POST" and path == ALERTMANAGER_CONFIG_PATH):
                    # Do not dump response bodies or credentials into Job logs.
                    raise RuntimeError(f"Grafana {method} {path}: HTTP {error.code}") from None
            except (URLError, TimeoutError):
                if method == "POST" and path == ALERTMANAGER_CONFIG_PATH:
                    raise RuntimeError("Grafana configuration POST outcome unknown; rerun to reread current UI state") from None
            if attempt < 29:
                time.sleep(5)
        raise RuntimeError(f"Grafana {method} {path} unavailable after retries")


def default_contact_point_plan(client, config):
    """Bootstrap an empty destination through the UI API, preserving integrations."""
    spec = config.get("defaultContactPoint")
    if not spec:
        return None
    name = spec["name"]
    current = client.request("GET", ALERTMANAGER_CONFIG_PATH)
    updated = copy.deepcopy(current)
    am = updated.get("alertmanager_config", {}) if isinstance(updated, dict) else {}
    route, receivers = am.get("route", {}), am.get("receivers")
    if not route.get("receiver") or not isinstance(receivers, list):
        raise RuntimeError("Missing existing Alertmanager configuration; refusing to replace it")
    receiver = next((r for r in receivers if r.get("name") == name), None)
    if receiver is None:
        receiver = {"name": name, "grafana_managed_receiver_configs": []}
        receivers.append(receiver)
    if route["receiver"] == "grafana-default-email":
        route["receiver"] = name
    template = config.get("notificationTemplate")
    if template and template.get("bindDefaultContactPoint", True):
        for integration in receiver.get("grafana_managed_receiver_configs", []):
            if integration.get("type") != "slack":
                continue
            settings = integration.setdefault("settings", {})
            for field, definition in (("title", "title"), ("text", "text")):
                if not (settings.get(field) or "").strip():
                    settings[field] = '{{ template "scroll-monitor.slack.' + definition + '" . }}'
    # Empty receivers are valid destinations. A Slack integration is added in
    # the UI later; no dummy URL, required Slack Secret or file provenance.
    return {"name": name, "updated": updated, "changed": updated != current,
            "empty": not receiver.get("grafana_managed_receiver_configs")}


def seed_default_contact_point(client, plan, dry_run=False):
    if not plan or not plan["changed"]:
        return
    if dry_run:
        print(f'PLAN default contact point: {plan["name"]}', flush=True)
        return
    # The payload may contain credentials for unrelated integrations. Never
    # log it. Grafana retains their encrypted secrets via existing secureFields.
    client.request("POST", ALERTMANAGER_CONFIG_PATH, plan["updated"])
    print(f'Seeded default contact point {plan["name"]}; preserved UI integrations and custom routing', flush=True)


def notification_route_id(config, scope):
    identity = f'{config["folderUID"]}/{scope}'
    return "scroll-" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def notification_routes(config):
    routes = {}
    for scope, key, identity in (
        ("business-pods", "businessPodContactPoint", ["namespace", "pod", "uid", "deployment", "statefulset", "daemonset", "job_name"]),
        ("disks", "diskContactPoint", ["cluster", "namespace", "persistentvolumeclaim", "instance", "device", "mountpoint"]),
        ("resources", "resourceContactPoint", ["cluster", "node", "instance", "namespace", "pod", "container"]),
    ):
        if not config.get(key):
            continue
        routes[scope] = {
            "receiver": config[key],
            "object_matchers": [["managed_by", "=", "scroll-monitor"],
                                ["scroll_monitor_route", "=", notification_route_id(config, scope)]],
            "group_by": ["grafana_folder", "alert_category", "severity", *identity],
            "group_wait": "30s", "group_interval": "5m", "repeat_interval": "4h",
            "continue": False,
            "routes": [{"receiver": config[key], "object_matchers": [["severity", "=", "critical"]],
                        "group_wait": "0s", "continue": False}],
        }
    return routes


def seed_notification_policies(client, config, dry_run=False):
    """Add scoped policy branches once; preserve all existing and UI-edited routes."""
    desired = notification_routes(config)
    if not desired:
        return
    path = "/api/v1/provisioning/policies"
    current = client.request("GET", path)
    if not isinstance(current, dict) or not current.get("receiver"):
        raise RuntimeError("Cannot read existing Grafana notification policy tree; refusing to replace it")
    updated = copy.deepcopy(current)
    existing = updated.get("routes", [])
    def contains_route(route, marker):
        if marker in route.get("object_matchers", []):
            return True
        return any(contains_route(child, marker) for child in route.get("routes", []))
    added = []
    for scope, route in desired.items():
        marker = ["scroll_monitor_route", "=", notification_route_id(config, scope)]
        if contains_route(updated, marker):
            continue  # Policy changes after first creation remain UI-owned.
        added.append(route)
    if not added:
        return
    # Match only our route identity before broader policies; preserve their order.
    updated["routes"] = added + existing
    if dry_run:
        print(f"PLAN notification policies: add {len(added)} scoped branches", flush=True)
        return
    client.request("PUT", path, updated)
    print(f"Seeded notification policies: {len(added)} scoped branches", flush=True)


def alert_rule(source, config, group):
    identity = f'{config["folderUID"]}/{group}/{source["alert"]}'
    uid = "scroll-" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    datasource_type = source.get("datasourceType", "prometheus")
    datasource = config["lokiDatasourceUID"] if datasource_type == "loki" else config["datasourceUID"]
    annotations = {
        key: value.replace("$value", "$values.A.Value")
        for key, value in source.get("annotations", {}).items()
    }
    rule = {
        "uid": uid,
        "orgID": 1,
        "folderUID": config["folderUID"],
        "ruleGroup": group,
        "title": source["alert"],
        "condition": "C",
        "for": source.get("for", "0s"),
        "noDataState": "OK",
        "execErrState": "Error",
        "isPaused": config.get("pauseRules", {}).get(source["alert"], source.get("isPaused", False)),
        "labels": {**source.get("labels", {}), "managed_by": "scroll-monitor"},
        "annotations": annotations,
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": 3600, "to": 0},
                "datasourceUid": datasource,
                "model": {
                    "refId": "A",
                    "datasource": {"type": datasource_type, "uid": datasource},
                    "expr": source["expr"],
                    **({"queryType": "instant"} if datasource_type == "loki" else {}),
                    "instant": True,
                    "range": False,
                    "intervalMs": 1000,
                    "maxDataPoints": 43200,
                },
            },
            {
                "refId": "B",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "refId": "B",
                    "type": "math",
                    # Prometheus alert expressions filter healthy series out.
                    # Any returned sample means firing, even if its value is 0.
                    "expression": "$A * 0 + 1",
                },
            },
            {
                "refId": "C",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "refId": "C",
                    "type": "threshold",
                    "expression": "B",
                    "conditions": [{
                        "type": "query",
                        "query": {"params": ["C"]},
                        "reducer": {"type": "last", "params": []},
                        "evaluator": {"type": "gt", "params": [0]},
                        "operator": {"type": "and"},
                    }],
                },
            },
        ],
    }
    if config.get("forwardAlertmanager"):
        # Forward promptly and refresh firing state before Alertmanager expiry.
        # The independent Alertmanager owns user-facing grouping/repetition.
        rule["notification_settings"] = {
            "receiver": config["forwardAlertmanager"]["name"],
            "group_wait": "0s", "group_interval": "10s", "repeat_interval": "1m",
        }
    scope = source.get("labels", {}).get("alert_scope")
    if scope in notification_routes(config):
        # Grafana 11 per-rule routing requires alertname in group_by. Use a
        # narrowly matched policy branch so related rules can share a group.
        rule["labels"]["scroll_monitor_route"] = notification_route_id(config, scope)
    rule["annotations"][BASELINE] = json.dumps(
        {key: fingerprint(value) for key, value in managed_fields(rule).items()}, sort_keys=True)
    return rule


def alternatives(value):
    """Allow a single legacy value or multiple exactly known shipped values."""
    return value if isinstance(value, list) else [value]


def migrate_expression(existing, source, desired):
    """Migrate known shipped defaults while preserving operator edits."""
    previous = source.get("previousExpr")
    if not previous or existing.get("labels", {}).get("managed_by") != "scroll-monitor":
        return None
    queries = [query for query in existing.get("data", []) if query.get("refId") == "A"]
    if len(queries) != 1:
        return None
    query = queries[0]
    # Be conservative: even whitespace edits inside strings may be intentional.
    if query.get("model", {}).get("expr") not in alternatives(previous):
        return None
    if query.get("datasourceUid") != desired["data"][0]["datasourceUid"]:
        return None
    updated = copy.deepcopy(existing)
    for query in updated["data"]:
        if query["refId"] == "A":
            query["model"]["expr"] = source["expr"]
    # Correct shipped explanations only when the operator has not edited them.
    for key, previous in source.get("previousAnnotations", {}).items():
        previous = [value.replace("$value", "$values.A.Value") for value in alternatives(previous)]
        if updated.get("annotations", {}).get(key) in previous:
            updated["annotations"][key] = desired["annotations"][key]
    if "previousFor" in source and updated.get("for") == source["previousFor"]:
        updated["for"] = desired["for"]
    for field in ("id", "updated", "provenance"):
        updated.pop(field, None)
    return updated


def managed_template(body):
    # Grafana trims stored templates, so hash exactly what it will return.
    body = body.strip()
    digest = hashlib.sha256(body.encode()).hexdigest()
    return f"{{{{/* scroll-monitor managed template sha256={digest} */}}}}\n{body}"


def seed_template(client, spec, dry_run=False):
    """Create or upgrade the shipped template; preserve UI or unmanaged edits."""
    name = spec["name"]
    path = f"/api/v1/provisioning/templates/{quote(name, safe='')}"
    desired = managed_template(spec["template"])
    existing = client.request("GET", path, allow_missing=True)
    if existing is not None:
        current = existing.get("template", "")
        if current == desired:
            print(f"Preserved notification template {name}", flush=True)
            return
        marker = TEMPLATE_MARKER.match(current)
        body = current[marker.end():] if marker else ""
        if not marker or hashlib.sha256(body.encode()).hexdigest() != marker.group(1):
            print(f"DRIFT notification template {name}: preserved UI or unmanaged content", flush=True)
            return
    action = "update" if existing is not None else "create"
    if dry_run:
        print(f"PLAN notification template {name}: {action}", flush=True)
        return
    client.request("PUT", path, {"template": desired})
    print(f"Seeded notification template {name}: {action}", flush=True)


def seed_forwarder(client, spec, dry_run=False):
    """Route Grafana-evaluated logs to the independent notification owner."""
    path = "/api/v1/provisioning/contact-points"
    desired = {"uid": spec["uid"], "name": spec["name"], "type": "prometheus-alertmanager",
               "settings": {"url": spec["url"]}, "disableResolveMessage": False}
    existing = next((p for p in client.request("GET", path) or [] if p.get("uid") == spec["uid"]), None)
    if existing and any(existing.get(k) != desired[k] for k in ("name", "type")):
        raise RuntimeError("External Alertmanager contact UID is already owned by another integration")
    # Grafana returns redacted optional secure fields even when unconfigured.
    # Compare only managed settings; never rewrite those fields on each upgrade.
    if (existing and all(existing.get(k) == desired[k] for k in ("uid", "name", "type", "disableResolveMessage"))
            and all(existing.get("settings", {}).get(k) == v for k, v in desired["settings"].items())):
        return
    if not dry_run:
        client.request("PUT" if existing else "POST", path + ("/" + quote(spec["uid"], safe="") if existing else ""), desired)


def seed(client, config, dry_run=False):
    if config.get("forwardAlertmanager"):
        seed_forwarder(client, config["forwardAlertmanager"], dry_run)
    default_plan = default_contact_point_plan(client, config)
    contact_points = {config[key] for key in ("businessPodContactPoint", "diskContactPoint", "resourceContactPoint") if config.get(key)}
    if contact_points:
        receivers = client.request("GET", "/api/v1/provisioning/contact-points")
        for contact_point in sorted(contact_points):
            if default_plan and default_plan["empty"] and contact_point == default_plan["name"]:
                continue  # Bootstrap destination intentionally has no integration yet.
            if not any(r.get("name") == contact_point and r.get("type") == "slack"
                       for r in (receivers or [])):
                raise RuntimeError(
                    f"Pod/disk/resource alerts require an existing Grafana Slack contact point named {contact_point!r}. "
                    "Create it in Grafana or set businessPodAlerts.contactPoint/diskAlerts.contactPoint/resourceAlerts.contactPoint "
                    "to the existing Slack contact name."
                )
    if config.get("notificationTemplate"):
        seed_template(client, config["notificationTemplate"], dry_run)
        # This API writes the entire Alertmanager configuration, including its
        # template files. Refresh after seeding to avoid restoring old templates.
        default_plan = default_contact_point_plan(client, config)
    seed_default_contact_point(client, default_plan, dry_run=dry_run)
    # During dry-run the empty destination has not been created yet, but policy
    # planning only reads the tree and never asks Grafana to validate/write it.
    seed_notification_policies(client, config, dry_run=dry_run)
    folder = quote(config["folderUID"], safe="")
    if client.request("GET", f"/api/folders/{folder}", allow_missing=True) is None and not dry_run:
        client.request("POST", "/api/folders", {
            "uid": config["folderUID"], "title": config["folderTitle"],
        })
    for group in config["groups"]:
        path = f'/api/v1/provisioning/folder/{folder}/rule-groups/{quote(group["name"], safe="")}'
        existing = client.request("GET", path, allow_missing=True)
        rules = copy.deepcopy((existing or {}).get("rules", []))
        if any(rule.get("provenance") == "file" for rule in rules):
            raise RuntimeError(
                f'Group {group["name"]} is file-provisioned. Remove its alerting '
                "file/sidecar configuration and reload Grafana before migrating."
            )
        existing_uids = {rule["uid"] for rule in rules}
        desired = [(source, alert_rule(source, config, group["name"])) for source in group["rules"]]
        additions = [rule for _, rule in desired if rule["uid"] not in existing_uids]
        migrations = []
        for source, rule in desired:
            current = next((item for item in rules if item["uid"] == rule["uid"]), None)
            if current is not None:
                migrated = reconcile_rule(current, source, rule,
                                          config.get("pauseRules", {}).get(source["alert"]))
                if migrated is not None:
                    migrations.append(migrated)
        unlock = any(rule.get("provenance") == "api" for rule in rules)
        if not additions and not unlock and not migrations:
            print(f'Preserved {group["name"]}: {len(rules)} existing rules', flush=True)
            continue
        if dry_run:
            print(f'PLAN {group["name"]}: {len(additions)} new, '
                  f'{len(migrations)} updates, unlock={unlock}', flush=True)
            continue
        if unlock:
            for rule in rules:
                for field in ("id", "updated", "provenance"):
                    rule.pop(field, None)
            client.request("PUT", path, {
                "title": group["name"],
                "folderUid": config["folderUID"],
                "interval": existing["interval"],
                "rules": rules,
            })
        # Grafana 11 group PUT treats a supplied UID as an update and rejects
        # unknown UIDs. Create each missing rule through POST instead. Stable
        # UIDs make retries after a partially completed import idempotent.
        for rule in additions:
            client.request("POST", "/api/v1/provisioning/alert-rules", rule)
        for rule in migrations:
            client.request("PUT", f'/api/v1/provisioning/alert-rules/{quote(rule["uid"], safe="")}', rule)
        print(f'Seeded {group["name"]}: {len(additions)} new, '
              f'{len(migrations)} rules updated, {len(rules)} existing', flush=True)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("config", help="rendered rules.json")
        parser.add_argument("--dry-run", action="store_true", help="GET only; report differences without writes")
        args = parser.parse_args()
        with open(args.config, encoding="utf-8") as source:
            seed(Grafana(), json.load(source), dry_run=args.dry_run)
    except (RuntimeError, OSError, ValueError) as error:
        sys.exit(str(error))
