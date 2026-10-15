"""Offline checks for resources owned by the binding Helm release."""
import copy
import pathlib
import subprocess
import unittest

import yaml


CHART = pathlib.Path(__file__).resolve().parents[1]


class BindingsTest(unittest.TestCase):
    def setUp(self):
        self.values = yaml.safe_load((CHART / "ci/render-values.yaml").read_text())

    def render(self, values):
        return subprocess.run(
            ["helm", "template", "alb-bindings", str(CHART), "-n", "operator", "-f", "-"],
            input=yaml.safe_dump(values), text=True, capture_output=True, check=False,
        )

    def test_release_owns_bindings_only(self):
        result = self.render(self.values)
        self.assertEqual(result.returncode, 0, result.stderr)
        documents = list(yaml.safe_load_all(result.stdout))
        self.assertEqual(len(documents), 1)
        binding = documents[0]
        self.assertEqual(binding["kind"], "TargetGroupBinding")
        self.assertEqual(binding["metadata"]["namespace"], "operator")
        self.assertNotIn("annotations", binding["metadata"])
        self.assertNotIn("ownerReferences", binding["metadata"])
        self.assertEqual(binding["spec"], self.values["bindings"]["tso-service"])
        # No Ingress, LoadBalancer Service, AWS-resource controller CR or delete hook.
        self.assertNotIn("helm.sh/hook", result.stdout)
        self.assertNotIn("helm.sh/resource-policy", result.stdout)

    def test_invalid_inputs_fail_before_install(self):
        for field, value in [("targetType", "instance"), ("targetGroupARN", "REPLACE_WITH_ARN")]:
            with self.subTest(field=field):
                values = copy.deepcopy(self.values)
                values["bindings"]["tso-service"][field] = value
                self.assertNotEqual(self.render(values).returncode, 0)
        for port in [0, 65536, "http"]:
            with self.subTest(port=port):
                values = copy.deepcopy(self.values)
                values["bindings"]["tso-service"]["serviceRef"]["port"] = port
                self.assertNotEqual(self.render(values).returncode, 0)

    def test_duplicate_target_groups_rejected(self):
        self.values["bindings"]["frontends"] = copy.deepcopy(self.values["bindings"]["tso-service"])
        self.assertIn("distinct", self.render(self.values).stderr)

    def test_empty_defaults_create_nothing(self):
        result = self.render({"bindings": {}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse([doc for doc in yaml.safe_load_all(result.stdout) if doc])


if __name__ == "__main__":
    unittest.main()
