"""Render the l2-reth chart's opt-in external P2P Service and its guards."""

from pathlib import Path
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
P2P_PORTS = [{"port": 30303, "targetPort": 30303, "protocol": "TCP", "name": "p2p-tcp"}]
POD_NAME = "statefulset.kubernetes.io/pod-name"
RPC_PORT = {"enabled": True, "port": 8545, "targetPort": 8545, "protocol": "TCP"}


def helm_template(*value_files, values=None):
    with tempfile.TemporaryDirectory() as directory:
        overlay = Path(directory) / "values.yaml"
        overlay.write_text(yaml.safe_dump(values or {}))
        command = ["helm", "template", "review", str(CHART)]
        for path in value_files:
            command.extend(["-f", str(path)])
        command.extend(["-f", str(overlay)])
        return subprocess.run(command, capture_output=True, text=True)


def p2p_external(**settings):
    return {"reth": {"p2pExternal": settings}}


def extra(name, service):
    return {"reth": {"service": {"extra": {name: service}}}}


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

    def external(self, *value_files, values=None):
        return self.services(self.render(*value_files, values=values))["review-l2-reth-p2p"]

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

    def test_ci_fixture_matches_example(self):
        fixture = yaml.safe_load(EXTERNAL_P2P.read_text())["reth"]["p2pExternal"]
        example = yaml.safe_load(BOOTNODE_EXAMPLE.read_text())["reth"]["p2pExternal"]
        self.assertEqual(fixture, dict(example, enabled=True))

    def test_enabled_renders_one_p2p_only_nlb_for_one_pod(self):
        docs = self.render(EXTERNAL_P2P)
        services = self.services(docs)
        self.assertEqual(sorted(services), ["review-l2-reth", "review-l2-reth-p2p"])
        self.assert_internal(services["review-l2-reth"])

        p2p = services["review-l2-reth-p2p"]
        self.assertEqual(p2p["spec"]["type"], "LoadBalancer")
        self.assertEqual(p2p["metadata"]["annotations"], NLB_ANNOTATIONS)
        self.assertEqual(p2p["spec"]["loadBalancerSourceRanges"], ["<TODO partner CIDR>"])
        self.assertEqual(p2p["spec"]["ports"], P2P_PORTS)
        self.assertEqual(p2p["spec"]["selector"], {
            "app.kubernetes.io/instance": "review",
            "app.kubernetes.io/name": "l2-reth",
            POD_NAME: "review-l2-reth-0",
        })

        workload = self.statefulset(docs)
        self.assertEqual(workload["metadata"]["name"], "review-l2-reth")
        self.assertEqual(workload["spec"]["replicas"], 1)
        pod_labels = workload["spec"]["template"]["metadata"]["labels"]
        for key in ["app.kubernetes.io/instance", "app.kubernetes.io/name"]:
            self.assertEqual(pod_labels[key], p2p["spec"]["selector"][key])

        args = workload["spec"]["template"]["spec"]["containers"][0]["args"]
        self.assertIn("--disable-discovery", args)
        self.assertIn("--port=30303", args)

    def test_operator_annotations_cannot_change_fixed_settings(self):
        values = p2p_external(annotations={
            AWS_ANNOTATION + "scheme": "internal",
            AWS_ANNOTATION + "nlb-target-type": "instance",
            AWS_ANNOTATION + "name": "bootnode-0",
        })
        values["global"] = {"annotations": {AWS_ANNOTATION + "type": "nlb"}}
        annotations = self.external(EXTERNAL_P2P, values=values)["metadata"]["annotations"]
        self.assertEqual(annotations, dict(NLB_ANNOTATIONS, **{AWS_ANNOTATION + "name": "bootnode-0"}))

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
                    "requires service.main.type ClusterIP",
                    EXTERNAL_P2P,
                    values={"service": {"main": {"type": main_type}}},
                )

    def test_refuses_sequencer(self):
        self.assert_fails(
            "designated non-sequencer nodes only",
            EXTERNAL_P2P,
            values={"role": "sequencer", "reth": {"signer": {"type": "awsKms", "awsKmsKeyId": "k"}}},
        )

    def test_ordinal_selects_a_pod_of_this_release(self):
        replicated = {"role": "rpc", "controller": {"replicas": 3}}
        p2p = self.external(EXTERNAL_P2P, values=dict(replicated, **p2p_external(ordinal=2)))
        self.assertEqual(p2p["spec"]["selector"][POD_NAME], "review-l2-reth-2")
        self.assertEqual(p2p["spec"]["ports"], P2P_PORTS)

        for ordinal in [3, -1]:
            with self.subTest(ordinal=ordinal):
                self.assert_fails("must name a pod of this release", EXTERNAL_P2P,
                                  values=dict(replicated, **p2p_external(ordinal=ordinal)))
        self.assert_fails("must name a pod of this release", EXTERNAL_P2P,
                          values=p2p_external(ordinal=1))

    def test_internet_facing_requires_sources_or_open_opt_in(self):
        self.assert_fails("set sourceRanges, or allowOpenPeering: true",
                          EXTERNAL_P2P, values=p2p_external(sourceRanges=[]))
        self.assert_fails("set sourceRanges, or allowOpenPeering: true",
                          EXTERNAL_P2P, values=p2p_external(sourceRanges=[], allowOpenPeering="true"))

        p2p = self.external(EXTERNAL_P2P, values=p2p_external(sourceRanges=[], allowOpenPeering=True))
        self.assertNotIn("loadBalancerSourceRanges", p2p["spec"])
        self.assertEqual(p2p["metadata"]["annotations"][AWS_ANNOTATION + "scheme"], "internet-facing")

    def test_eip_allocations_match_subnets(self):
        self.assert_fails("one entry per reth.p2pExternal.subnets entry", EXTERNAL_P2P,
                          values=p2p_external(subnets=["subnet-a", "subnet-b"]))

    def test_refuses_annotations_that_bypass_sources_or_add_proxy_protocol(self):
        for key in ["security-groups", "disable-nlb-sg", "proxy-protocol"]:
            annotation = {AWS_ANNOTATION + key: "x"}
            for values in [p2p_external(annotations=annotation), {"global": {"annotations": annotation}}]:
                with self.subTest(key=key, values=values):
                    self.assert_fails("is not allowed", EXTERNAL_P2P, values=values)

    # Review bypasses through reth.service.extra (F1, F3); NodePort included.
    def test_extra_services_cannot_publish_ports(self):
        for service_type in ["LoadBalancer", "NodePort"]:
            for ports in [
                {"rpc": RPC_PORT},
                {"p2p-tcp": {"enabled": True, "port": 30303, "targetPort": 8545, "protocol": "TCP"}},
            ]:
                service = {"enabled": True, "type": service_type, "ports": ports}
                with self.subTest(service_type=service_type, ports=ports):
                    self.assert_fails("must stay internal", values=extra("public", service))
                    self.assert_fails("must stay internal", EXTERNAL_P2P, values=extra("public", service))
        self.assert_fails("must stay internal", values=extra("public", {
            "externalIPs": ["203.0.113.1"], "ports": {"rpc": RPC_PORT},
        }))

    def test_extra_cannot_replace_main_or_p2p(self):
        self.assert_fails("reserved for the chart's main Service", values=extra("main", {
            "type": "ClusterIP", "ports": {"http": RPC_PORT},
        }))
        self.assert_fails("reserved for reth.p2pExternal", EXTERNAL_P2P, values=extra("p2p", {
            "ports": {"http": RPC_PORT},
        }))

    def test_extra_selectors_cannot_retarget_the_external_service(self):
        values = extra("internal", {
            "extraSelectorLabels": {
                "app.kubernetes.io/instance": "other-release",
                POD_NAME: "other-release-0",
            },
            "ports": {"p2p-tcp": {"enabled": True, "port": 30303, "targetPort": 30303}},
        })
        p2p = self.external(EXTERNAL_P2P, values=values)
        self.assertEqual(p2p["spec"]["selector"]["app.kubernetes.io/instance"], "review")
        self.assertEqual(p2p["spec"]["selector"][POD_NAME], "review-l2-reth-0")

    def test_inherited_annotations_cannot_make_it_internal_or_open(self):
        # F2: global annotations merge under the Service's own, so the fixed
        # scheme wins and the source-range check still applies.
        values = p2p_external(sourceRanges=[])
        values["global"] = {"annotations": {AWS_ANNOTATION + "scheme": "internal"}}
        self.assert_fails("set sourceRanges, or allowOpenPeering: true", EXTERNAL_P2P, values=values)

        p2p = self.external(EXTERNAL_P2P, values={"global": {"annotations": {AWS_ANNOTATION + "scheme": "internal"}}})
        self.assertEqual(p2p["metadata"]["annotations"][AWS_ANNOTATION + "scheme"], "internet-facing")


if __name__ == "__main__":
    unittest.main()
