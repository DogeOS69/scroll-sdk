"""Pure and mocked checks: no AWS command is executed by these tests."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/discover-aws-regions.py"
SPEC = importlib.util.spec_from_file_location("discover_aws_regions", SCRIPT)
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)


def region(name, status="opt-in-not-required"):
    return {"RegionName": name, "OptInStatus": status}


class DiscoverAwsRegions(unittest.TestCase):
    def test_enabled_regions_are_sorted_deduplicated_and_not_bootstrap_limited(self):
        payload = {"Regions": [region("us-west-2"), region("eu-south-2", "opted-in"),
                               region("us-west-2"), region("ap-east-1", "not-opted-in")]}
        self.assertEqual(discovery.enabled_regions(payload), ["eu-south-2", "us-west-2"])

    def test_malformed_unknown_disabled_empty_and_conflicting_responses_fail(self):
        cases = [None, {}, {"Regions": {}}, {"Regions": []}, {"Regions": [None]},
                 {"Regions": [{"RegionName": "us-east-1"}]},
                 {"Regions": [region("us-east-1", "future-status")]},
                 {"Regions": [region("us-east-1", None)]},
                 {"Regions": [region("us-east-1", [])]},
                 {"Regions": [region("not a region")]},
                 {"Regions": [region(123)]},
                 {"Regions": [region("us-east-1", "not-opted-in")]},
                 {"Regions": [region("us-east-1"), region("us-east-1", "not-opted-in")]}]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                discovery.enabled_regions(payload)

    def test_cli_executes_only_readonly_discovery_with_profile_and_bootstrap_region(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"Regions": [region("eu-west-3")]}), "")
        output = io.StringIO()
        with mock.patch.object(discovery.subprocess, "run", return_value=result) as run, \
                contextlib.redirect_stdout(output):
            self.assertEqual(discovery.main(["--profile", "fixture", "--query-region", "us-west-2"]), 0)
        self.assertEqual(json.loads(output.getvalue()), {"regions": ["eu-west-3"]})
        self.assertEqual(run.call_args.args[0], ["aws", "ec2", "describe-regions", "--all-regions",
                         "--region", "us-west-2", "--output", "json", "--no-cli-pager", "--profile", "fixture"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def test_aws_errors_and_malformed_private_output_are_not_echoed(self):
        marker = "PRIVATE-DIAGNOSTIC-MUST-NOT-APPEAR"
        failures = [subprocess.CalledProcessError(1, ["aws"], output=marker, stderr=marker),
                    subprocess.TimeoutExpired(["aws"], 60, output=marker, stderr=marker),
                    FileNotFoundError(marker)]
        for failure in failures:
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(discovery.subprocess, "run", side_effect=failure), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(discovery.main([]), 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn(marker, stderr.getvalue())
        with mock.patch.object(discovery.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 0, marker, marker)), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(discovery.main([]), 1)
        self.assertNotIn(marker, stdout.getvalue() + stderr.getvalue())

    def test_output_is_exclusive_and_existing_content_is_preserved(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"Regions": [region("us-east-1")]}), "")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "regions.json"
            with mock.patch.object(discovery.subprocess, "run", return_value=result), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(discovery.main(["--output", str(path)]), 0)
                original = path.read_bytes()
                self.assertEqual(json.loads(original), {"regions": ["us-east-1"]})
                self.assertEqual(discovery.main(["--output", str(path)]), 1)
                self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
