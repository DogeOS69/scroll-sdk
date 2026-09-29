#!/usr/bin/env python3
"""Seed UI-editable Grafana rules without replacing operators' existing rules."""

import argparse
import base64
import copy
import hashlib
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASELINE = "__scroll_monitor_last_applied__"


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
                if error.code < 500:
                    # Do not dump response bodies or credentials into Job logs.
                    raise RuntimeError(f"Grafana {method} {path}: HTTP {error.code}") from None
            except (URLError, TimeoutError):
                pass
            if attempt < 29:
                time.sleep(5)
        raise RuntimeError(f"Grafana {method} {path} unavailable after retries")


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


def seed(client, config, dry_run=False):
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
