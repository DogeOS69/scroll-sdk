"""Render the l2-reth chart's opt-in external P2P Service and its guards."""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/l2-reth"
EXTERNAL_P2P = CHART / "ci/external-p2p-values.yaml"
BOOTNODE_EXAMPLE = ROOT / "examples/values/l2-reth-bootnode-production.yaml"
AWS_ANNOTATION = "service.beta.kubernetes.io/aws-load-balancer-"
NLB_ANNOTATIONS = {
    AWS_ANNOTATION + "type": "external",
    AWS_ANNOTATION + "nlb-target-type": "ip",
    AWS_ANNOTATION + "scheme": "internet-facing",
    AWS_ANNOTATION + "subnets": "<TODO subnet-id>",
    AWS_ANNOTATION + "eip-allocations": "<TODO eipalloc-id>",
}
POD_NAME = "statefulset.kubernetes.io/pod-name"


def helm_template(*value_files, values=None):
    with tempfile.TemporaryDirectory() as directory:
        overlay = Path(directory) / "values.yaml"
        overlay.write_text(yaml.safe_dump(values or {}))
        command = ["helm", "template", "review", str(CHART)]
        for path in value_files:
            command.extend(["-f", str(path)])
        command.extend(["-f", str(overlay)])
        return subprocess.run(command, capture_output=True, text=True)


def commented_extra_example():
    """Uncomment the disabled `extra:` block in the bootnode example."""
    lines = BOOTNODE_EXAMPLE.read_text().splitlines()
    start = lines.index("    # extra:")
    block = []
    for line in lines[start:]:
        if not line.startswith("    #"):
            break
        block.append(re.sub(r"^    # ?", "", line))
    return yaml.safe_load("\n".join(block))["extra"]


class L2RethP2PTests(unittest.TestCase):
    def render(self, *value_files, values=None):
        result = helm_template(*value_files, values=values)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    def assert_fails(self, message, *value_files, values=None):
        result = helm_template(*value_files, values=values)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def services(self, docs):
        return {doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "Service"}

    def statefulset(self, docs):
        return next(doc for doc in docs if doc["kind"] == "StatefulSet")

    def assert_internal(self, service):
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertNotIn("loadBalancerSourceRanges", service["spec"])
        annotations = service["metadata"].get("annotations") or {}
        self.assertFalse([key for key in annotations if key.startswith(AWS_ANNOTATION)])

    def test_disabled_by_default(self):
        for role in ["rpc", "bootnode"]:
            with self.subTest(role=role):
                services = self.services(self.render(values={"role": role}))
                self.assertEqual(list(services), ["review-l2-reth"])
                main = services["review-l2-reth"]
                self.assert_internal(main)
                self.assertEqual(
                    {port["name"]: port["port"] for port in main["spec"]["ports"]},
                    {"http": 8545, "ws": 8546, "metrics": 6060},
                )

    def test_bootnode_example_keeps_p2p_internal(self):
        services = self.services(self.render(BOOTNODE_EXAMPLE))
        self.assertEqual(list(services), ["review-l2-reth"])
        self.assert_internal(services["review-l2-reth"])

    def test_ci_fixture_matches_commented_example(self):
        fixture = yaml.safe_load(EXTERNAL_P2P.read_text())
        self.assertEqual(fixture["reth"]["service"]["extra"], commented_extra_example())

    def test_enabled_renders_one_p2p_only_nlb_for_one_pod(self):
        docs = self.render(EXTERNAL_P2P)
        services = self.services(docs)
        self.assertEqual(sorted(services), ["review-l2-reth", "review-l2-reth-p2p"])
        self.assert_internal(services["review-l2-reth"])

        p2p = services["review-l2-reth-p2p"]
        self.assertEqual(p2p["spec"]["type"], "LoadBalancer")
        self.assertEqual(p2p["metadata"]["annotations"], NLB_ANNOTATIONS)
        self.assertEqual(p2p["spec"]["loadBalancerSourceRanges"], ["<TODO partner CIDR>"])
        self.assertEqual(
            p2p["spec"]["ports"],
            [{"port": 30303, "targetPort": 30303, "protocol": "TCP", "name": "p2p-tcp"}],
        )

        # One bootnode release runs one pod, and the Service selects that release.
        workload = self.statefulset(docs)
        self.assertEqual(workload["spec"]["replicas"], 1)
        pod_labels = workload["spec"]["template"]["metadata"]["labels"]
        for key, value in p2p["spec"]["selector"].items():
            self.assertEqual(pod_labels.get(key), value)

        args = workload["spec"]["template"]["spec"]["containers"][0]["args"]
        self.assertIn("--disable-discovery", args)
        self.assertIn("--port=30303", args)

    def test_node_key_is_persistent(self):
        # secret mode: the bootnode example mounts the node key from its Secret.
        docs = self.render(EXTERNAL_P2P)
        pod = self.statefulset(docs)["spec"]["template"]["spec"]
        args = pod["containers"][0]["args"]
        self.assertEqual(args[args.index("--p2p-secret-key") + 1], "/keys/nodekey")
        nodekey = next(volume for volume in pod["volumes"] if volume["name"] == "nodekey")
        self.assertEqual(nodekey["secret"]["secretName"], "review-l2-reth-secret-env")

        # pvcAutoGenerate mode: the key is generated once onto the data PVC.
        docs = self.render(EXTERNAL_P2P, values={"reth": {"nodeKey": {"mode": "pvcAutoGenerate"}}})
        pod = self.statefulset(docs)["spec"]["template"]["spec"]
        generate = next(c for c in pod["initContainers"] if c["name"] == "generate-nodekey")
        self.assertIn('if [ ! -s "/data/nodekey" ]', generate["command"][-1])
        self.assertIn({"name": "data", "mountPath": "/data"}, generate["volumeMounts"])
        data = next(volume for volume in pod["volumes"] if volume["name"] == "data")
        self.assertEqual(data["persistentVolumeClaim"]["claimName"], "review-l2-reth-data")

    def test_refuses_public_main_service(self):
        for main_type in ["LoadBalancer", "NodePort"]:
            with self.subTest(main_type=main_type):
                self.assert_fails(
                    "service.main.type must be ClusterIP",
                    EXTERNAL_P2P,
                    values={"service": {"main": {"type": main_type}}},
                )

    def test_refuses_sequencer(self):
        self.assert_fails(
            "designated non-sequencer nodes only",
            EXTERNAL_P2P,
            values={"role": "sequencer", "reth": {"signer": {"type": "awsKms", "awsKmsKeyId": "k"}}},
        )

    def test_replicas_require_a_pod_name_selector(self):
        replicated = {"role": "rpc", "controller": {"replicas": 3}}
        self.assert_fails("statefulset.kubernetes.io/pod-name", EXTERNAL_P2P, values=replicated)

        selected = dict(replicated, reth={"service": {"extra": {"p2p": {
            "extraSelectorLabels": {POD_NAME: "review-l2-reth-1"},
        }}}})
        p2p = self.services(self.render(EXTERNAL_P2P, values=selected))["review-l2-reth-p2p"]
        self.assertEqual(p2p["spec"]["selector"][POD_NAME], "review-l2-reth-1")

    def test_disabled_extra_service_is_not_guarded(self):
        values = {
            "service": {"main": {"type": "LoadBalancer"}},
            "reth": {"service": {"extra": {"p2p": {"enabled": False}}}},
        }
        services = self.services(self.render(EXTERNAL_P2P, values=values))
        self.assertEqual(list(services), ["review-l2-reth"])


if __name__ == "__main__":
    unittest.main()
