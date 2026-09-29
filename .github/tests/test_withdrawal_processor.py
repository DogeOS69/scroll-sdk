"""Render allocator defaults with the chart's actual common-library dependency."""

from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/withdrawal-processor"
ARENA_DEFAULT = {
    "name": "MALLOC_ARENA_MAX",
    "valueFrom": {"resourceFieldRef": {"resource": "limits.cpu", "divisor": "1"}},
}


class AllocatorEnvironmentTests(unittest.TestCase):
    def render(self, values=None, production=False):
        with tempfile.TemporaryDirectory() as directory:
            overlay = Path(directory) / "values.yaml"
            overlay.write_text(yaml.safe_dump(values or {}))
            command = ["helm", "template", "review", str(CHART)]
            if production:
                command.extend(["-f", str(CHART / "values/production.yaml")])
            command.extend(["-f", str(overlay)])
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            workload = next(
                doc for doc in yaml.safe_load_all(result.stdout)
                if doc and doc.get("kind") == "StatefulSet"
            )
            return workload["spec"]["template"]["spec"]["containers"][0]

    def assert_arena(self, container, expected):
        entries = [env for env in container["env"] if env["name"] == "MALLOC_ARENA_MAX"]
        self.assertEqual(entries, [expected])

    def test_defaults_and_production_inject_cpu_reference(self):
        for production, cpu in [(False, "500m"), (True, "1500m")]:
            with self.subTest(production=production):
                container = self.render(production=production)
                self.assert_arena(container, ARENA_DEFAULT)
                self.assertEqual(container["resources"]["limits"]["cpu"], cpu)

    def test_injection_preserves_other_env_in_both_formats(self):
        for env in [{"RUST_LOG": "info"}, [{"name": "RUST_LOG", "value": "info"}]]:
            with self.subTest(env=env):
                container = self.render({"env": env})
                self.assert_arena(container, ARENA_DEFAULT)
                self.assertIn({"name": "RUST_LOG", "value": "info"}, container["env"])

    def test_explicit_values_win_in_both_formats(self):
        for value in ["2", "0"]:
            entry = {"name": "MALLOC_ARENA_MAX", "value": value}
            for env in [{"MALLOC_ARENA_MAX": value}, [entry]]:
                with self.subTest(env=env):
                    self.assert_arena(self.render({"env": env}), entry)

    def test_explicit_value_sources_win_in_both_formats(self):
        source = {"configMapKeyRef": {"name": "allocator", "key": "arenas"}}
        entry = {"name": "MALLOC_ARENA_MAX", "valueFrom": source}
        for env in [
            {"MALLOC_ARENA_MAX": {"valueFrom": source}},
            {"MALLOC_ARENA_MAX": source},
            [entry],
        ]:
            with self.subTest(env=env):
                self.assert_arena(self.render({"env": env}), entry)

    def test_empty_env_formats_still_receive_default(self):
        for env in [None, {}, []]:
            with self.subTest(env=env):
                self.assert_arena(self.render({"env": env}), ARENA_DEFAULT)

    def test_no_cpu_limit_allows_an_explicit_arena_limit(self):
        container = self.render({
            "resources": {"limits": {"cpu": None}},
            "env": {"MALLOC_ARENA_MAX": "2"},
        })
        self.assert_arena(container, {"name": "MALLOC_ARENA_MAX", "value": "2"})
        self.assertNotIn("cpu", container["resources"]["limits"])


if __name__ == "__main__":
    unittest.main()
