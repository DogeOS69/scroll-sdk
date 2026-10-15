# Use existing ALBs without tying their lifetime to Helm

Use the paired scroll-sdk-cli release with `infrastructure.aws.alb.mode: existing`.
Provision the ALBs, HTTPS 443 listeners, ACM certificates, listener rules and
HTTP/IP target groups independently, before installing application bindings.
Neither CLI generation nor the `alb-bindings` chart creates these AWS resources.
Missing or mismatched references are errors; there is no create-new fallback.

The following is a **fragment** to merge into your deployment spec. Replace the
nonfunctional placeholders with identifiers of your externally managed resources:

```yaml
infrastructure:
  provider: aws
  kubeContext: REPLACE_WITH_EKS_CONTEXT
  namespace: default
  aws:
    accountId: "REPLACE_WITH_ACCOUNT_ID"
    region: us-east-1
    eksClusterName: REPLACE_WITH_CLUSTER
    alb:
      mode: existing
      endpoints:
        tso:
          loadBalancerArn: REPLACE_WITH_EXISTING_ALB_ARN
          listenerArn: REPLACE_WITH_EXISTING_HTTPS_443_LISTENER_ARN
        public:
          loadBalancerArn: REPLACE_WITH_EXISTING_PUBLIC_ALB_ARN
          listenerArn: REPLACE_WITH_EXISTING_PUBLIC_HTTPS_443_LISTENER_ARN
      bindings:
        tso-service:
          endpoint: tso
          targetGroupArn: REPLACE_WITH_EXISTING_TSO_TARGET_GROUP_ARN
          serviceRef:
            name: tso-service
            port: 3000
        frontends:
          endpoint: public
          targetGroupArn: REPLACE_WITH_EXISTING_FRONTENDS_TARGET_GROUP_ARN
          serviceRef:
            name: frontends
            port: 80
```

`serviceRef` is the **actual rendered Kubernetes Service name and service port**,
not the Helm release name or the Pod/container port. Set it explicitly to support
release overrides and vendor charts. Bindings live in `infrastructure.namespace`.

This fragment only selects two services. Add a binding for every other exposed
ingress, or explicitly set its `enabled: false` in operator values. CLI generation
fails if an enabled ingress has no binding. In particular, public HTTP RPC and
WebSocket RPC have separate binding keys and target groups. Give them distinct
hostnames (or explicitly configure distinct paths); identical host/path rules
cannot route to two unrelated target groups.

Supported binding keys:

| Binding | Values ingress |
| --- | --- |
| `tso-service`, `proof-coordinator`, `frontends`, `l1-devnet`, `l1-interface` | `ingress.main` of the corresponding production file |
| `l2-reth-rpc-public` | `l2-reth-rpc-public-production.yaml` / `ingress.main` |
| `l2-reth-rpc-public-ws` | Same file / `ingress.websocket` |
| `dogecoin`, `blockbook`, `dstack-controller` | `ingress` of the corresponding production file |
| `scroll-monitor` | `scroll-monitor-production.yaml` / `grafana.ingress` |
| `blockscout-api` | `blockscout-production.yaml` / `blockscout-stack.blockscout.ingress` |
| `blockscout-frontend` | Same file / `blockscout-stack.frontend.ingress` |

Hosts and paths remain in existing generated/operator values. CLI sets
`enabled: false` and `existingAlbBinding` on each selected ingress, retaining its
route metadata for verification. Regeneration keeps it disabled, even if a chart
preparation helper would normally enable the public endpoint. Do not delete the
marker manually or enable legacy Ingresses alongside bindings.

`values/alb-bindings-production.yaml` is generated from the spec. It is installed
as a separate release, allowing the same integration for native charts and
third-party subcharts without changing their resource ownership.

## Infrastructure requirements

- Use externally managed ALBs without Kubernetes load-balancer-controller
  ownership tags, in the EKS VPC/account/region. Existing resources still owned
  by an Ingress are not adopted by this workflow.
- Each selected listener must use HTTPS 443 and an issued, unexpired ACM
  certificate covering the generated hostnames. Configure DNS to the selected
  ALB independently. `setup tls` does not attach certificates to external ALBs.
- Configure explicit host-header/path-pattern forwarding rules to the selected
  target groups. Prefix `/signer` means ALB patterns `/signer` and `/signer/*`;
  Exact `/health` means `/health`. TSO permits only these paths, never `/*`.
  Rules pointing to a selected target group from another listener are rejected.
- TSO and Proof Coordinator retain their existing separate-ALB requirement.
  Coordinator idle timeout must be at least 120 seconds. Other services may
  share an externally managed ALB with separate target groups and routing rules.
- Target groups must be HTTP/IP, with HTTP health checks on `traffic-port`,
  the health path and success codes from application values. Configure the
  listener default action separately (for example, a fixed 404).
- Restrict ALB/backend security groups and configure Pod routing/NetworkPolicy.
  The binding chart does not manage security groups. TSO still requires edge
  NetworkPolicy peers even though its Kubernetes Ingress is disabled. Disable
  `preparation.tsoAlbEdge`; set edge CIDRs to the chosen ALB subnets explicitly.
- For dstack use an internal ALB, `dstackController.ingress.hosts`, and internal
  DNS. Do not combine existing mode with `dstackController.internalTls`, which
  describes a controller-created ALB. Keep the existing controller HTTPS URL
  consistent with the selected hostname.
- Target groups are exclusive to one binding. Do not mix manually registered
  targets, other clusters or other TargetGroupBindings in the same group.

`scrollsdk setup alb` uses read-only AWS Describe operations. Its checks verify
resource references and selected route policy, not end-to-end connectivity or
every possible listener-rule priority interaction. After installation, test real
DNS/TLS, authorized requests, denied TSO paths and application health.

## Install, check and remove

1. Generate/bootstrap with a pinned SDK commit containing `alb-bindings`, and
   finish the normal preparation workflow. Final AWS spec-based `prep-charts`
   requires existing bindings or explicitly disabled HTTP ingress.
2. Run `scrollsdk setup alb` to check AWS resources before installation.
3. Install application workloads with the generated values. These values must
   render no managed ALB Ingresses. Configure security groups and NetworkPolicy.
4. Run `make install-alb-bindings`. It first runs
   `scrollsdk setup alb --require-services`, checks the exact Kubernetes target,
   controller CRD and installed ClusterIP Service ports, then installs bindings.
   `install-all` invokes this target when binding values exist. Install optional
   workloads selected by bindings (such as dstack or Blockscout) beforehand.
5. Run `scrollsdk test ingress`; existing mode checks bindings and AWS target
   health instead of expecting Kubernetes Ingress objects. Then test real
   HTTPS application routes. This check does not replace endpoint acceptance.
6. `make delete-alb-bindings` removes bindings and deregisters targets. `delete-all`
   also removes the binding release. ALBs, listeners, rules and target groups
   remain. Keep the AWS Load Balancer Controller running for finalizer cleanup.

Before the chart is published, use a reviewed local checkout:

```bash
make install-alb-bindings ALB_BINDINGS_CHART=/path/to/scroll-sdk/charts/alb-bindings
```

Uninstalling one application does not uninstall the separate binding release.
For a deliberate binding removal, first disable its ingress and remove its
`existingAlbBinding` marker in operator values, remove its spec binding, then
regenerate and upgrade the binding release. The CLI refuses a stale marker
whose binding was removed accidentally. Regeneration alone does not modify
already installed resources.

The expected lifecycle test on a disposable deployment is: install, observe
healthy registered Pod targets, uninstall the binding/application releases,
confirm the ALB/listener/TG ARNs are unchanged and targets are deregistered,
then reinstall and verify new Pod targets become healthy. Offline render tests
establish the Helm ownership boundary; they do not claim this live AWS test ran.

References: [AWS lifecycle pattern](https://aws.amazon.com/blogs/containers/patterns-for-targetgroupbinding-with-aws-load-balancer-controller/),
[TargetGroupBinding](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/targetgroupbinding/targetgroupbinding/).
