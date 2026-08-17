#!/usr/bin/env python3
"""Enforce operator-readable, self-contained production values contracts."""

from pathlib import Path
import sys

import yaml


SERVICES = (
    "l1-interface",
    "withdrawal-processor",
    "eth-da-submitter",
    "proof-coordinator",
    "cubesigner-signer",
)

REQUIRED_TOP_LEVEL = {
    "l1-interface": {
        "global", "image", "command", "service", "probes",
        "env", "envFrom", "configMaps", "externalSecrets", "persistence",
        "resources", "serviceMonitor",
    },
    "withdrawal-processor": {
        "global", "image", "command", "args", "service",
        "probes", "env", "envFrom", "externalSecrets", "tsoSigners",
        "persistence", "resources", "serviceMonitor",
    },
    "eth-da-submitter": {
        "global", "image", "command", "args", "service",
        "probes", "ingress", "env", "envFrom", "configMaps",
        "externalSecrets", "persistence", "resources", "serviceMonitor",
    },
    "proof-coordinator": {
        "global", "image", "command", "service", "probes",
        "proofCoordinator", "initContainers", "serviceAccount", "env",
        "envFrom", "externalSecrets", "configMaps", "persistence",
        "resources", "podSecurityContext", "securityContext", "serviceMonitor",
        "ingress",
    },
    "cubesigner-signer": {
        "global", "image", "command", "args", "service",
        "probes", "env", "externalSecrets", "persistence",
        "volumeClaimTemplates", "resources", "serviceMonitor",
    },
}

SHARED_CONFIG_FILES = {
    "l1-interface": {
        "genesis": ("genesis-config", "genesis.json"),
        "protocol-context": ("protocol-context-config", "protocol_context.json"),
    },
    "withdrawal-processor": {
        "protocol-context": ("protocol-context-config", "protocol_context.json"),
    },
    "eth-da-submitter": {
        "genesis": ("genesis-config", "genesis.json"),
        "protocol-context": ("protocol-context-config", "protocol_context.json"),
    },
    "proof-coordinator": {
        "protocol-context": ("protocol-context-config", "protocol_context.json"),
    },
    "cubesigner-signer": {
        "protocol-context": ("protocol-context-config", "protocol_context.json"),
    },
}


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return value


def leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        if not value:
            yield prefix
        for key, child in value.items():
            yield from leaf_paths(child, prefix + (key,))
    else:
        # Lists are treated as an explicitly selected unit. Requiring every
        # default list element would prevent production from replacing probes,
        # commands, environment entries, and monitor endpoints intentionally.
        yield prefix


def has_path(value, path):
    current = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def path_text(path):
    return ".".join(path)


def validate_file(service, path, defaults):
    errors = []
    values = load_yaml(path)

    missing_top_level = REQUIRED_TOP_LEVEL[service] - values.keys()
    for key in sorted(missing_top_level):
        errors.append(f"missing production section: {key}")

    # A production file may choose different values, but it must explicitly
    # declare every runtime-affecting value exposed by the chart defaults.
    for default_path in leaf_paths(defaults):
        # Controller kind/replicas/strategy define the fixed workload model.
        # They belong to the chart and its schema, not environment overlays.
        if default_path and default_path[0] in {"controller", "defaultProbes"}:
            continue
        if not has_path(values, default_path):
            errors.append(f"inherits hidden chart default: {path_text(default_path)}")

    if "controller" in values:
        errors.append(
            "controller is a fixed chart property and must not be in production values"
        )

    image = values.get("image", {})
    for key in ("repository", "pullPolicy", "tag"):
        if not image.get(key):
            errors.append(f"image.{key} must be explicit and non-empty")
    if str(image.get("tag", "")).lower() in {"latest", "head", "canary"}:
        errors.append("image.tag must not be a floating tag")

    service_main = values.get("service", {}).get("main", {})
    if "enabled" not in service_main:
        errors.append("service.main.enabled must be explicit")
    for port_name, port in service_main.get("ports", {}).items():
        for key in ("enabled", "port", "targetPort", "protocol"):
            if key not in port:
                errors.append(f"service.main.ports.{port_name}.{key} must be explicit")

    for probe_name in ("startup", "liveness", "readiness"):
        probe = values.get("probes", {}).get(probe_name, {})
        for key in ("enabled", "custom", "spec"):
            if key not in probe:
                errors.append(f"probes.{probe_name}.{key} must be explicit")
        spec = probe.get("spec", {})
        for key in (
            "httpGet", "initialDelaySeconds", "periodSeconds", "timeoutSeconds",
            "failureThreshold",
        ):
            if key not in spec:
                errors.append(f"probes.{probe_name}.spec.{key} must be explicit")

    resources = values.get("resources", {})
    for scope in ("requests", "limits"):
        for resource in ("cpu", "memory"):
            if resource not in resources.get(scope, {}):
                errors.append(f"resources.{scope}.{resource} must be explicit")

    persistence = values.get("persistence", {})
    for mount_name, (config_map_name, key) in SHARED_CONFIG_FILES[service].items():
        mount = persistence.get(mount_name, {})
        expected = {
            "enabled": True,
            "type": "configMap",
            "name": config_map_name,
            "subPath": key,
            "readOnly": True,
        }
        for field, expected_value in expected.items():
            if mount.get(field) != expected_value:
                errors.append(
                    f"persistence.{mount_name}.{field} must be {expected_value!r}"
                )
        if not str(mount.get("mountPath", "")).startswith("/"):
            errors.append(f"persistence.{mount_name}.mountPath must be absolute")
        items = mount.get("items", [])
        if {"key": key, "path": key} not in items:
            errors.append(
                f"persistence.{mount_name}.items must explicitly project {key}"
            )

    return [f"{path}: {error}" for error in errors]


def validate():
    errors = []
    for service in SERVICES:
        defaults_path = Path("charts") / service / "values.yaml"
        chart_production = Path("charts") / service / "values" / "production.yaml"
        example_production = Path("examples/values") / f"{service}-production.yaml"
        defaults = load_yaml(defaults_path)
        for production_path in (chart_production, example_production):
            if not production_path.is_file():
                errors.append(f"{production_path}: missing production values file")
                continue
            errors.extend(validate_file(service, production_path, defaults))

    for error in errors:
        print(f"❌ {error}")
    if not errors:
        print("✅ Production values are explicit and operator-readable")
    return not errors


if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
