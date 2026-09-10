#!/usr/bin/env python3
"""Evaluate the rendered rules with promtool, including configurable thresholds."""

from pathlib import Path
import subprocess
import tempfile

import yaml


CHART = Path(__file__).resolve().parents[1]
rendered = subprocess.check_output([
    "helm", "template", "scroll-monitor", str(CHART), "--namespace", "monitoring",
    "--set", "grafanaAlerting.enabled=false",
    "--set", "serviceAlerts.paused=false",
    "--set", "businessAlerts.requiredSignersByRole.Correctness=2",
    "--set", "dogecoinIndexerAlerts.confirmationsByJob.l1-interface=60",
    "--set", "dogecoinIndexerAlerts.confirmationsByJob.withdrawal-processor=120",
], text=True)
rules = next(doc["spec"] for doc in yaml.safe_load_all(rendered)
             if doc and doc["kind"] == "PrometheusRule"
             and doc["metadata"]["name"] == "scroll-monitor-dogeos")
with tempfile.TemporaryDirectory(prefix="scroll-monitor-tests-") as directory:
    root = Path(directory)
    root.chmod(0o755)
    (root / "rules.yaml").write_text(yaml.safe_dump(rules, sort_keys=False))
    files = []
    for source in sorted((CHART / "tests").glob("*.test.yaml")):
        data = yaml.safe_load(source.read_text())
        data["rule_files"] = ["rules.yaml"]
        (root / source.name).write_text(yaml.safe_dump(data, sort_keys=False))
        files.append("/work/" + source.name)
    subprocess.run([
        "docker", "run", "--rm", "--entrypoint", "promtool",
        "-v", f"{root}:/work:ro", "prom/prometheus:v2.52.0",
        "test", "rules", *files,
    ], check=True)
