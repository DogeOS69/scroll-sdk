#!/usr/bin/env python3
"""Print account-enabled EC2 regions; never provision or change AWS settings."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REGION = re.compile(r"[a-z]+(?:-[a-z0-9]+)+-[1-9][0-9]*")
STATUSES = {"opt-in-not-required", "opted-in", "not-opted-in"}


def enabled_regions(payload):
    rows = payload.get("Regions") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("Missing regions")
    seen = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed region")
        name, status = row.get("RegionName"), row.get("OptInStatus")
        if (not isinstance(name, str) or not REGION.fullmatch(name)
                or not isinstance(status, str) or status not in STATUSES):
            raise ValueError("Malformed region or unknown opt-in status")
        if name in seen and seen[name] != status:
            raise ValueError("Conflicting region statuses")
        seen[name] = status
    regions = sorted(name for name, status in seen.items() if status != "not-opted-in")
    if not regions:
        raise ValueError("No enabled regions")
    return regions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="Optional existing AWS CLI profile")
    parser.add_argument("--query-region", default="us-east-1", help="Bootstrap API region only")
    parser.add_argument("--output", type=Path, help="Exclusively create a new JSON/YAML fragment")
    args = parser.parse_args(argv)
    try:
        if not REGION.fullmatch(args.query_region):
            raise ValueError("Invalid query region")
        command = ["aws", "ec2", "describe-regions", "--all-regions", "--region",
                   args.query_region, "--output", "json", "--no-cli-pager"]
        if args.profile is not None:
            command.extend(["--profile", args.profile])
        result = subprocess.run(command, capture_output=True, text=True, check=True,
                                stdin=subprocess.DEVNULL, timeout=60)
        fragment = json.dumps({"regions": enabled_regions(json.loads(result.stdout))}, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(fragment)
        else:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(fragment)
        return 0
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        # AWS diagnostics and malformed responses may contain private data.
        print("AWS region discovery or output creation failed; details omitted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
