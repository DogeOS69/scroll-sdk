#!/usr/bin/env python3
"""Seed UI-editable Grafana rules without replacing operators' existing rules."""

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
    return {
        "uid": uid,
        "orgID": 1,
        "folderUID": config["folderUID"],
        "ruleGroup": group,
        "title": source["alert"],
        "condition": "C",
        "for": source.get("for", "0s"),
        "noDataState": "OK",
        "execErrState": "Error",
        "isPaused": source.get("isPaused", False),
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


def migrate_expression(existing, source, desired):
    """Replace only a known shipped query, keeping all other operator settings."""
    previous = source.get("previousExpr")
    if not previous or existing.get("labels", {}).get("managed_by") != "scroll-monitor":
        return None
    queries = [query for query in existing.get("data", []) if query.get("refId") == "A"]
    if len(queries) != 1:
        return None
    query = queries[0]
    # Be conservative: even whitespace edits inside strings may be intentional.
    if query.get("model", {}).get("expr") != previous:
        return None
    if query.get("datasourceUid") != desired["data"][0]["datasourceUid"]:
        return None
    updated = copy.deepcopy(existing)
    for query in updated["data"]:
        if query["refId"] == "A":
            query["model"]["expr"] = source["expr"]
    # Correct shipped explanations only when the operator has not edited them.
    for key, previous in source.get("previousAnnotations", {}).items():
        previous = previous.replace("$value", "$values.A.Value")
        if updated.get("annotations", {}).get(key) == previous:
            updated["annotations"][key] = desired["annotations"][key]
    for field in ("id", "updated", "provenance"):
        updated.pop(field, None)
    return updated


def seed(client, config):
    folder = quote(config["folderUID"], safe="")
    if client.request("GET", f"/api/folders/{folder}", allow_missing=True) is None:
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
                migrated = migrate_expression(current, source, rule)
                if migrated is not None:
                    migrations.append(migrated)
        unlock = any(rule.get("provenance") == "api" for rule in rules)
        if not additions and not unlock and not migrations:
            print(f'Preserved {group["name"]}: {len(rules)} existing rules', flush=True)
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
              f'{len(migrations)} queries migrated, {len(rules)} existing', flush=True)


if __name__ == "__main__":
    try:
        with open(sys.argv[1], encoding="utf-8") as source:
            seed(Grafana(), json.load(source))
    except (RuntimeError, OSError, ValueError) as error:
        sys.exit(str(error))
