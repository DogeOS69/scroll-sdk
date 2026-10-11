# Production network and workload IAM

The AWS production examples use the AWS Load Balancer Controller (ALB for
HTTPS). They do not require ingress-nginx or cert-manager. The frontend image's
own static-file nginx server is unrelated and remains part of that image.
Grafana and Dogecoin ingress are disabled by default; Blockscout is an explicit
optional installation. Snapshot access is outside this change.

## Prepare HTTPS edges

After spec bootstrap, edit the generated `values/*-production.yaml` files.
Keep certificates, subnets, WAF and source CIDRs in those files, not in spec.
Use an issued ACM certificate in the ALB region covering each enabled host.
For a certificate covering all enabled hosts:

```bash
scrollsdk setup tls --certificate-arn "$ACM_CERTIFICATE_ARN" --non-interactive
```

Alternatively set `alb.ingress.kubernetes.io/certificate-arn` separately on
each enabled ingress. `setup tls` only updates local values; it neither issues
certificates nor changes Kubernetes. Re-running spec generation preserves the
operator's annotations. Explicit legacy controller selections are rejected;
review and change the class to `alb` before regenerating.

TSO and Proof Coordinator each require their own ALB: never set `group.name`
for these services. TSO publishes only `/health` and signed `/signer/*` routes.
Proof Coordinator uses its bearer token and an ALB idle timeout of at least
120 seconds. JSON-RPC ingress health checks accept HTTP 200–499 because a GET
without a JSON-RPC body (or authentication) can return 400/401/405; this checks
HTTP reachability, not chain synchronization. 5xx/timeouts remain unhealthy.
Use application probes and RPC monitoring for chain readiness.

The optional Blockscout API and frontend share a hostname and therefore need
the same unique `alb.ingress.kubernetes.io/group.name` when explicitly enabled.
Do not reuse this group for TSO/Coordinator. Review RPC/browser CORS settings in
the application: ALB does not implement the removed nginx CORS annotations.
Bootnode TCP P2P NLBs remain separate from HTTPS ingress.

An existing cluster migration also needs DNS cutover and verification before
removing its ingress-nginx release. These tools do not uninstall an existing
controller or change its load balancers automatically.

## Enable and verify TSO/WP isolation

The production examples enable `networkPolicy`. `setup prep-charts` rejects a
disabled TSO/WP policy, missing mandatory peers, placeholder CIDRs, all-address
CIDRs and empty pod selectors. Helm also guards required peers and obvious
unrestricted inputs when NetworkPolicy is enabled.

| Destination | Allowed callers | TCP port |
| --- | --- | --- |
| TSO API | WP, CubeSigner signer, ALB subnets, selected monitoring/operator pods | 3000 |
| WP API | TSO, selected monitoring/operator pods | 3000 |
| WP proof-work | Proof Coordinator | 9300 |

Replace `tso-service.networkPolicy.allowFrom.edge` with the CIDRs of the
subnets actually selected for its ALB. Prefer explicit
`alb.ingress.kubernetes.io/subnets` so the two configurations cannot drift.
These are ALB source subnet CIDRs, not the remote signer addresses and not the
Ingress inbound client allowlist. Pods in those CIDRs can also match this rule;
use suitably dedicated ALB subnets and security groups. Do not use `0.0.0.0/0`.

Default pod selectors use the example chart labels in the same namespace.
For Prometheus or an operator toolbox in another namespace, put both selectors
in the **same peer** (AND), for example:

```yaml
monitoring:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: monitoring
    podSelector:
      matchLabels:
        app.kubernetes.io/name: prometheus
```

Do not split the selectors into separate list items (OR). External attestation
signers need no inbound ports; they connect through the TSO ALB. In-cluster
CubeSigner callbacks go directly to the TSO Service.

These policies isolate inbound traffic only. Outbound RPC, DNS, S3 and KMS
remain available. API, health and metrics share a listener: a permitted
monitoring pod can also reach that listener's management routes. NetworkPolicy
cannot restrict HTTP paths; the public Ingress path rules do that at the edge.

Before launch, enable NetworkPolicy enforcement in the cluster CNI and verify:

1. An ordinary pod with no allowed labels cannot reach TSO:3000 or WP:3000/9300.
2. WP reaches TSO, TSO reaches WP, CubeSigner reaches TSO, and Coordinator
   reaches WP:9300. Monitoring targets remain up.
3. Public signed signer polling works; `/propose`, `/register-signer`, `/metrics`
   and WP management endpoints are not exposed on public ALBs.
4. Review every other NetworkPolicy selecting these pods. Kubernetes combines
   allowed traffic across policies; another allow-all policy defeats isolation.

Helm rendering does not prove CNI enforcement. Kubernetes node/kubelet traffic
and `kubectl port-forward` are not substitutes for the pod-to-pod denial test.
An authorized operator can use port-forward or a narrowly selected toolbox pod
for rotation administration; no broad public WP ingress is needed.

## Workload IAM upper bounds

| Workload | Resource | Allowed S3 actions |
| --- | --- | --- |
| eth-da-submitter | Its DA prefix plus the two configured proof sidecar prefixes | GetObject, PutObject |
| WP | Its proof artifact prefix | GetObject, PutObject |
| Proof Coordinator | Its proof artifact prefix | GetObject, PutObject, DeleteObject; ListBucket with prefix condition |

GetObject is required for existing-object verification/readback. Coordinator
listing and deletion support recovery. WP and submitter receive neither list
nor delete grants. KMS signing policies contain only GetPublicKey and Sign on
the selected key ARN. IRSA trust binds the exact cluster OIDC provider,
namespace and service account, with `aud=sts.amazonaws.com`.

Provisioning and read-only proof-resource reuse inspect other inline and
attached IAM policies for S3 grants exceeding the intended workload scope.
KMS role reconciliation additionally checks KMS grants against the selected
key. Managed policy default versions are inspected, including URL-encoded IAM
documents. An unreadable inventory, wildcard action, broad resource, or an
unprovable prefix condition stops the operation with the role/policy name.
Only the policy explicitly being replaced is excluded from this check.
The CLI does not delete third-party policies. Review those separately and
rerun; the AWS caller needs IAM list/get policy permissions for this audit.

This is a conservative upper-bound check, not a claim about all effective AWS
permissions. Bucket/key resource policies, organization controls, permission
boundaries, sessions and node-role credential fallback also affect access.
Keep workload roles dedicated; restrict pod access to node IMDS. Verify actual
runtime calls with the workload identity before launch. `setup artifact-access`
can check the DA writer's expected actions using IAM simulation, but simulation
alone is not a real S3 transfer test.

Public read delivery is a separate bucket-policy decision. DA public reads and
the independent VPC endpoint read statement remain separate (the DA kill
switch removes only public read). Required proof-consumer object paths remain
publicly readable for external signers/workers per the decisions document;
public listing, writes and deletion are never granted by these generated
bucket policies.
