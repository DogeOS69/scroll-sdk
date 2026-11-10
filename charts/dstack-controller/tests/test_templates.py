"""Offline behavior checks; never contact Kubernetes or a compute provider."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]


def render(values=None, overlays=(), namespace="dstack-system"):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "values.yaml"
        path.write_text(yaml.safe_dump(values or {}))
        command = [
            "helm", "template", "gpu", str(CHART), "--namespace", namespace,
        ]
        for overlay in overlays:
            command.extend(["-f", str(overlay)])
        command.extend(["-f", str(path)])
        return subprocess.run(command, text=True, capture_output=True)


def resources(values=None):
    result = render(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(docs, kind):
    return next(doc for doc in docs if doc["kind"] == kind)


class ControllerTemplates(unittest.TestCase):
    def test_prepared_private_endpoint_binding_uses_chart_service_and_rejects_dual_owner(self):
        binding = {'targetGroupARN': 'arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/example/0000',
                   'networking': {'ingress': [{'from': [{'securityGroup': {'groupID': 'sg-00000000'}}],
                                             'ports': [{'port': 3000, 'protocol': 'TCP'}]}]}}
        docs = resources({'fullnameOverride': 'controller', 'targetGroupBinding': binding})
        target = resource(docs, 'TargetGroupBinding')
        self.assertEqual(target['spec']['serviceRef'], {'name': 'controller', 'port': 3000})
        self.assertEqual(target['spec']['networking'], binding['networking'])
        self.assertEqual(target['spec']['targetGroupARN'], binding['targetGroupARN'])
        self.assertEqual(target['spec']['targetType'], 'ip')
        self.assertNotEqual(render({'targetGroupBinding': binding, 'ingress': {'enabled': True}}).returncode, 0)

    def test_default_has_no_provisioning_hooks_gpu_or_cluster_privileges(self):
        docs = resources()
        self.assertEqual({d["kind"] for d in docs}, {
            "Deployment", "Service", "ServiceAccount", "PersistentVolumeClaim", "ServiceMonitor"})
        self.assertTrue(all("helm.sh/hook" not in d["metadata"].get("annotations", {}) for d in docs))
        deployment = resource(docs, "Deployment")
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(deployment["spec"]["replicas"], 1)
        pod = deployment["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertNotIn("initContainers", pod)
        container = pod["containers"][0]
        env = {e["name"]: e for e in container["env"]}
        self.assertEqual(env["DSTACK_DEFAULT_CREDS_DISABLED"]["value"], "1")
        self.assertIn("@sha256:", container["image"])
        self.assertNotIn("nvidia.com/gpu", str(container["resources"]))
        self.assertNotIn("command", container)
        self.assertNotIn("args", container)
        self.assertEqual(resource(docs, "Service")["spec"]["type"], "ClusterIP")
        pvc = resource(docs, "PersistentVolumeClaim")
        self.assertEqual(pvc["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
        self.assertNotIn("storageClassName", pvc["spec"])

    def test_default_credentials_opt_in_preserves_irsa_and_no_kubernetes_token(self):
        role = "arn:aws:iam::123456789012:role/test-dstack"
        docs = resources({
            "defaultCredentialsEnabled": True,
            "serviceAccount": {"annotations": {"eks.amazonaws.com/role-arn": role}},
        })
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        env = {e["name"]: e for e in pod["containers"][0]["env"]}
        self.assertNotIn("DSTACK_DEFAULT_CREDS_DISABLED", env)
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(resource(docs, "ServiceAccount")["metadata"]["annotations"],
                         {"eks.amazonaws.com/role-arn": role})

    def test_aws_irsa_overlay_prepares_only_the_credential_chain(self):
        values = yaml.safe_load((CHART / "values/aws-irsa.yaml").read_text())
        # The shipped placeholder is deliberately not a usable role. A site
        # supplies its existing role; this fake fixture performs no AWS call.
        self.assertIn("REPLACE_WITH_DSTACK_CONTROLLER_ROLE",
                      values["serviceAccount"]["annotations"]["eks.amazonaws.com/role-arn"])
        role = "arn:aws:iam::123456789012:role/test-dstack"
        # Apply only site-specific overrides after the actual shipped overlay.
        # This exercises Helm's layering, not a Python copy of the overlay.
        result = render({
            "serviceAccount": {"annotations": {"eks.amazonaws.com/role-arn": role}},
            "serverConfig": {"existingSecret": "existing-native-projects", "key": "config.yml"},
            "persistence": {"existingClaim": "existing-controller-state"},
        }, overlays=[CHART / "values/aws-irsa.yaml"])
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        env = {e["name"]: e for e in pod["containers"][0]["env"]}
        self.assertNotIn("DSTACK_DEFAULT_CREDS_DISABLED", env)
        self.assertEqual(env["AWS_EC2_METADATA_DISABLED"],
                         {"name": "AWS_EC2_METADATA_DISABLED", "value": "true"})
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(resource(docs, "ServiceAccount")["metadata"]["annotations"],
                         {"eks.amazonaws.com/role-arn": role})
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertEqual(volumes["config"]["secret"]["secretName"], "existing-native-projects")
        self.assertEqual(volumes["state"]["persistentVolumeClaim"]["claimName"],
                         "existing-controller-state")
        self.assertNotIn("AWS_ACCESS_KEY_ID", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertFalse(any(d["kind"] in {
            "Secret", "ConfigMap", "Job", "Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding",
        } for d in docs))
        self.assertNotIn("initContainers", pod)
        self.assertTrue(all("helm.sh/hook" not in d["metadata"].get("annotations", {}) for d in docs))

    def test_config_and_credentials_reference_secrets_without_rendering_values(self):
        docs = resources({
            "serverConfig": {"existingSecret": "multi-cloud", "key": "server.yaml"},
            "credentialSecrets": [{"name": "gcp", "secretName": "gcp-key"},
                                  {"name": "aws", "secretName": "aws-key"}],
            "extraEnv": [{"name": "GOOGLE_APPLICATION_CREDENTIALS",
                          "value": "/etc/dstack/credentials/gcp/key.json"}],
        })
        self.assertFalse(any(d["kind"] in {"Secret", "ConfigMap"} for d in docs))
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertEqual(volumes["config"]["secret"]["secretName"], "multi-cloud")
        self.assertEqual(volumes["config"]["secret"]["items"], [{"key": "server.yaml", "path": "config.yml"}])
        mounts = {v["name"]: v for v in pod["containers"][0]["volumeMounts"]}
        self.assertEqual(mounts["state"]["mountPath"], "/root/.dstack/server")
        self.assertEqual(mounts["config"]["subPath"], "config.yml")
        for name in ("gcp", "aws"):
            self.assertTrue(mounts[f"credentials-{name}"]["readOnly"])
            self.assertEqual(volumes[f"credentials-{name}"]["secret"]["secretName"], f"{name}-key")

    def test_postgres_existing_claim_and_service_account(self):
        docs = resources({
            "database": {"type": "postgresql", "existingSecret": "db", "key": "url"},
            "persistence": {"existingClaim": "restored-state"},
            "serviceAccount": {"create": False, "name": "workload-identity"},
        })
        self.assertFalse(any(d["kind"] in {"PersistentVolumeClaim", "ServiceAccount"} for d in docs))
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "workload-identity")
        self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], "restored-state")
        env = {e["name"]: e for e in pod["containers"][0]["env"]}
        self.assertEqual(env["DSTACK_DATABASE_URL"]["valueFrom"]["secretKeyRef"], {"name": "db", "key": "url"})

    def test_ingress_tls_and_named_target_port(self):
        docs = resources({"service": {"port": 8080}, "ingress": {
            "enabled": True, "className": "nginx", "hosts": ["dstack.example.com"],
            "tls": [{"secretName": "tls", "hosts": ["dstack.example.com"]}],
        }})
        ingress = resource(docs, "Ingress")["spec"]
        self.assertEqual(ingress["ingressClassName"], "nginx")
        self.assertEqual(ingress["tls"][0]["secretName"], "tls")
        self.assertEqual(ingress["rules"][0]["http"]["paths"][0]["backend"]["service"]["port"], {"name": "http"})
        self.assertEqual(resource(docs, "Service")["spec"]["ports"][0]["targetPort"], "http")

    def test_invalid_and_unsafe_combinations_fail_before_install(self):
        cases = [
            ({"replicaCount": 2}, "replicaCount"),
            ({"database": {"type": "postgresql"}}, "database.existingSecret"),
            ({"ingress": {"enabled": True}}, "ingress.hosts"),
            ({"serverConfig": {"existingSecret": ""}}, "existingSecret"),
            ({"image": {"digest": "sha256:bad"}}, "digest"),
            ({"image": {"digest": "", "tag": ""}}, "image.tag"),
            ({"serviceAccount": {"automountServiceAccountToken": "false"}}, "boolean"),
            ({"defaultCredentialsEnabled": "true"}, "boolean"),
            ({"extraEnv": [{"name": "DSTACK_DEFAULT_CREDS_DISABLED", "value": "0"}]}, "reserved"),
            ({"extraEnv": [{"name": "DSTACK_DATABASE_URL", "value": "sqlite://"}]}, "reserved"),
            ({"extraEnv": [{"name": "HOME", "value": "/tmp"}]}, "reserved"),
            ({"extraEnv": [{"name": "A", "value": "1"}, {"name": "A", "value": "2"}]}, "duplicate"),
            ({"credentialSecrets": [{"name": "same", "secretName": "one"},
                                    {"name": "same", "secretName": "two"}]}, "duplicate"),
        ]
        for values, message in cases:
            with self.subTest(values=values):
                result = render(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_tls_keeps_dstack_on_loopback_behind_a_private_ca(self):
        docs = resources({"fullnameOverride": "controller", "tls": {"enabled": True}})
        issuers = {d["metadata"]["name"]: d["spec"] for d in docs if d["kind"] == "Issuer"}
        self.assertEqual(issuers, {"controller-selfsigned": {"selfSigned": {}},
                                   "controller-ca": {"ca": {"secretName": "controller-ca"}}})
        certificates = {d["metadata"]["name"]: d["spec"] for d in docs if d["kind"] == "Certificate"}
        ca, server = certificates["controller-ca"], certificates["controller-tls"]
        self.assertTrue(ca["isCA"])
        self.assertEqual(ca["privateKey"]["rotationPolicy"], "Never")
        self.assertEqual(ca["issuerRef"]["name"], "controller-selfsigned")
        self.assertEqual(server["issuerRef"]["name"], "controller-ca")
        self.assertEqual(server["secretName"], "controller-tls")
        self.assertEqual(server["dnsNames"], [
            "controller", "controller.dstack-system", "controller.dstack-system.svc",
            "controller.dstack-system.svc.cluster.local"])
        self.assertNotIn("isCA", server)

        pod = resource(docs, "Deployment")["spec"]["template"]
        self.assertIn("checksum/tls-proxy", pod["metadata"]["annotations"])
        containers = {c["name"]: c for c in pod["spec"]["containers"]}
        controller, proxy = containers["controller"], containers["tls-proxy"]
        self.assertEqual(controller["command"], ["/usr/bin/tini", "--", "dstack", "server", "--host", "127.0.0.1"])
        self.assertNotIn("ports", controller)
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertNotIn("httpGet", controller[probe])
            self.assertEqual(controller[probe]["exec"]["command"][-1], "http://127.0.0.1:3000/")
        self.assertRegex(proxy["image"], r"@sha256:[a-f0-9]{64}$")
        self.assertTrue(proxy["securityContext"]["runAsNonRoot"])
        self.assertTrue(proxy["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(proxy["ports"], [{"name": "https", "containerPort": 8443}])
        volumes = {v["name"]: v for v in pod["spec"]["volumes"]}
        self.assertEqual(volumes["tls"]["secret"]["secretName"], "controller-tls")

        self.assertEqual(resource(docs, "Service")["spec"]["ports"],
                         [{"name": "https", "port": 8443, "targetPort": "https"}])
        endpoint = resource(docs, "ServiceMonitor")["spec"]["endpoints"][0]
        self.assertEqual((endpoint["port"], endpoint["scheme"]), ("https", "https"))
        self.assertEqual(endpoint["tlsConfig"], {"serverName": "controller.dstack-system.svc",
                                                 "ca": {"secret": {"name": "controller-tls", "key": "ca.crt"}}})
        files = resource(docs, "ConfigMap")["data"]
        self.assertIn("listen 8443 ssl;", files["nginx.conf"])
        self.assertIn("proxy_pass http://127.0.0.1:3000;", files["nginx.conf"])
        self.assertIn("TERM INT QUIT", files["run.sh"])

    def test_tls_rejects_public_entrypoints_and_the_plaintext_port(self):
        binding = {'targetGroupARN': 'arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/example/0000',
                   'networking': {'ingress': [{'ports': [{'port': 3000, 'protocol': 'TCP'}]}]}}
        cases = [
            ({"ingress": {"enabled": True, "hosts": ["dstack.example.com"]}}, "disable ingress"),
            ({"targetGroupBinding": binding}, "disable ingress"),
            ({"port": 3000}, "tls.port"),
            ({"proxy": {"image": {"digest": ""}}}, "digest"),
            # The image entrypoint, which handles these, is bypassed to bind loopback.
            ({"extraEnv": [{"name": "LITESTREAM_REPLICA_URL", "value": "s3://example.invalid/db"}]}, "image entrypoint"),
            ({"extraEnv": [{"name": "GOOGLE_APPLICATION_CREDENTIALS_JSON", "value": "{}"}]}, "image entrypoint"),
            ({"livenessProbe": {"tcpSocket": {"port": "http"}}}, "livenessProbe must use httpGet"),
            ({"readinessProbe": {"httpGet": None, "grpc": {"port": 3000}}}, "readinessProbe must use httpGet"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra):
                values = {"tls": {"enabled": True}}
                for key, value in extra.items():
                    (values["tls"] if key in ("port", "proxy") else values)[key] = value
                result = render(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
        # Without TLS the entrypoint runs, so these stay available.
        self.assertEqual(render({"extraEnv": [{"name": "LITESTREAM_REPLICA_URL", "value": "s3://example.invalid/db"}]}).returncode, 0)

    def test_tls_keeps_an_exec_probe_override_and_a_valid_ca_name(self):
        # Helm merges the override into the default httpGet; the user's command must still run.
        docs = resources({"tls": {"enabled": True}, "livenessProbe": {"exec": {"command": ["true"]}}})
        controller = resource(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(controller["livenessProbe"]["exec"], {"command": ["true"]})
        self.assertNotIn("httpGet", controller["livenessProbe"])
        self.assertIn("curl", controller["readinessProbe"]["exec"]["command"])
        # cert-manager rejects a commonName over 64 characters; namespaces can have 63.
        result = render({"fullnameOverride": "d" * 63, "tls": {"enabled": True}}, namespace="n" * 63)
        self.assertEqual(result.returncode, 0, result.stderr)
        ca = next(d for d in yaml.safe_load_all(result.stdout) if d and d["kind"] == "Certificate" and d["spec"].get("isCA"))
        self.assertLessEqual(len(ca["spec"]["commonName"]), 64)
        self.assertTrue(ca["spec"]["commonName"].endswith(" dstack CA"))

    def test_production_profile_and_explicit_storage_class(self):
        values = yaml.safe_load((CHART / "values/production.yaml").read_text())
        values["persistence"]["storageClass"] = ""
        docs = resources(values)
        self.assertEqual(resource(docs, "PersistentVolumeClaim")["spec"]["storageClassName"], "")
        self.assertEqual(resource(docs, "Deployment")["spec"]["replicas"], 1)


if __name__ == "__main__":
    unittest.main()
