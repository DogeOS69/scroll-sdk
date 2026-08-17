#!/usr/bin/env python3

import glob
import os
import re
import sys
from difflib import unified_diff
from pathlib import Path

import yaml

from validate_production_values import validate as validate_production_values


def load_yaml_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return None, None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
            yaml_content = yaml.safe_load(raw_content)
            return yaml_content, raw_content
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None, None


def compare_yaml_files(file1, file2):
    result1 = load_yaml_file(file1)
    result2 = load_yaml_file(file2)

    if result1[0] is None or result2[0] is None:
        return False

    content1, raw1 = result1
    content2, raw2 = result2

    if content1 != content2:
        print("❌ Files are not in sync!")
        print(f"Source file: {file1}")
        print(f"Target file: {file2}")
        print("-" * 80)

        # Generate and print git-style diff
        diff = unified_diff(
            raw1.splitlines(keepends=True),
            raw2.splitlines(keepends=True),
            fromfile="Source",
            tofile="Target",
            lineterm="",
        )
        print("".join(list(diff)))
        return False
    return True


def validate_production_files():
    success = True

    # Check values files sync
    chart_values = glob.glob("charts/**/values/production*.yaml", recursive=True)
    for chart_value_file in chart_values:
        service_name = Path(chart_value_file).parts[-3]
        production_file = Path(chart_value_file).parts[-1]  # e.g. "production-0.yaml"

        # Construct the corresponding example file path
        example_file = f"examples/values/{service_name}-{production_file}"

        if os.path.exists(example_file):
            if not compare_yaml_files(chart_value_file, example_file):
                success = False
        else:
            print(f"❌ Missing example values file: {example_file}")
            success = False

    return success


def validate_example_makefile():
    makefile_path = "examples/Makefile.example"
    if not os.path.exists(makefile_path):
        return True

    with open(makefile_path, "r") as f:
        raw_makefile_content = f.read()
        # Replace line continuations (\newline) with spaces
        makefile_content = re.sub(r"\\\n\s*", " ", raw_makefile_content)

    # Modified regex to extract service name from URL and version
    # Modified regex to support versions with suffixes like -dogeos
    version_patterns = set(re.findall(
        r"helm upgrade -i [^\s]+\s+oci://.+?/helm/?.*?([^/\s]+)\s+.*?--version=(\d+\.\d+\.\d+(?:-[a-zA-Z0-9]+)?)",
        makefile_content,
    ))

    # Mode-agnostic installers such as `scrollsdk helper proof-helm` receive
    # their chart and version through variables rather than a literal Helm
    # command. Keep those examples covered by the same chart-sync check.
    chart_variables = dict(re.findall(
        r"^([A-Z][A-Z0-9_]*)_CHART\s*\?=\s*oci://[^\s]+/helm/([^\s]+)\s*$",
        raw_makefile_content,
        re.MULTILINE,
    ))
    version_variables = dict(re.findall(
        r"^([A-Z][A-Z0-9_]*)_CHART_VERSION\s*\?=\s*([0-9A-Za-z.-]+)\s*$",
        raw_makefile_content,
        re.MULTILINE,
    ))
    for variable, service in chart_variables.items():
        if variable in version_variables:
            version_patterns.add((service, version_variables[variable]))

    success = True
    for service, version in version_patterns:
        chart_file = f"charts/{service}/Chart.yaml"
        if not os.path.exists(chart_file):
            print(f"❌ Chart file not found for service: {service}")
            success = False
            continue

        chart_data = load_yaml_file(chart_file)
        if not chart_data[0]:
            continue

        chart_version = chart_data[0].get("version")
        if version != chart_version:
            print(f"❌ Version mismatch in Makefile.example for {service}")
            print(f"  Makefile version: {version}")
            print(f"  Chart version: {chart_version}")
            success = False

    return success


def validate_attestation_signer_partner_kit():
    """Keep the partner-owned Compose handoff from being removed as unused."""
    root = Path("partner-kit/attestation-signer")
    required_files = [
        root / "README.md",
        root / "docker-compose/.env.example",
        root / "docker-compose/docker-compose.yml",
        root / "docker-compose/signer-policy.env",
    ]
    success = True

    for file_path in required_files:
        if not file_path.is_file():
            print(f"❌ Missing attestation-signer partner-kit file: {file_path}")
            success = False

    if not success:
        return False

    if (root / "helm").exists():
        print("❌ attestation-signer partner kit must remain Docker Compose-only")
        success = False

    readme = (root / "README.md").read_text(encoding="utf-8")
    for command in [
        "scrollsdk signer init",
        "scrollsdk signer preflight",
        "docker compose --project-directory docker-compose",
        "signer-policy-bundle/PARTNER-COMMANDS.md",
    ]:
        if command not in readme:
            print(f"❌ Partner README is missing the canonical flow: {command}")
            success = False

    compose, _ = load_yaml_file(root / "docker-compose/docker-compose.yml")
    signer = (compose or {}).get("services", {}).get("attestation-signer", {})
    if signer.get("env_file") != [
        "attestation-signer.env",
        "signer-policy.env",
    ]:
        print("❌ Partner Compose must load operator key env before bridge policy env")
        success = False

    volumes = signer.get("volumes", [])
    if "./policy:/etc/dogeos:ro" not in volumes:
        print("❌ Partner Compose must mount the generated policy directory read-only")
        success = False

    return success


def main():
    success = True

    if not validate_production_values():
        success = False

    # Check production files sync
    # if not validate_production_files():
    #     success = False

    # Check example Makefile versions
    if not validate_example_makefile():
        success = False

    if not validate_attestation_signer_partner_kit():
        success = False

    if not success:
        sys.exit(1)

    print("✅ All checks passed!")


if __name__ == "__main__":
    main()
