# Use existing ALBs without tying their lifetime to Helm

Use the paired scroll-sdk-cli release with `infrastructure.aws.alb.mode: existing`.
Provision the ALBs, HTTPS 443 listeners, ACM certificates, listener rules and
HTTP/IP target groups independently, before installing application bindings.
Neither CLI generation nor application charts create these AWS resources.
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
ingress of the supported applications below, or explicitly set its `enabled: false` in operator values. CLI generation
fails if a supported application has an enabled ingress without a binding. In particular, public HTTP RPC and
WebSocket RPC have separate binding keys and target groups. Give them distinct
hostnames (or explicitly configure distinct paths); identical host/path rules
cannot route to two unrelated target groups.

Supported binding keys:

| Binding | Values ingress |
| --- | --- |
| `tso-service`, `proof-coordinator`, `frontends` | `ingress.main` of the corresponding production file |
| `l2-reth-rpc-public` | `l2-reth-rpc-public-production.yaml` / `ingress.main` |
| `l2-reth-rpc-public-ws` | Same file / `ingress.websocket` |
| `blockscout-api` | `blockscout-production.yaml` / `blockscout-stack.blockscout.ingress` |
| `blockscout-frontend` | Same file / `blockscout-stack.frontend.ingress` |

Hosts and paths remain in existing generated/operator values. CLI sets
`enabled: false` and `existingAlbBinding` on each selected ingress, retaining its
route metadata for verification. Regeneration keeps it disabled, even if a chart
preparation helper would normally enable the public endpoint. Do not delete the
marker manually or enable legacy Ingresses alongside bindings.

CLI writes `targetGroupBindings` into each application's production values.
The application chart owns these bindings in the same Helm release as its
Services and workloads. Blockscout bindings belong to the existing `blockscout`
parent chart. No separate chart or release is required.

This workflow covers only the five charts listed above. It does not modify or
restrict the ingress configuration of other charts.

For example, the generated TSO values contain:

```yaml
ingress:
  main:
    enabled: false
    existingAlbBinding: tso-service
    # Retain the generated hosts/paths here for CLI verification.
targetGroupBindings:
  tso-service:
    targetGroupARN: REPLACE_WITH_EXISTING_HTTP_IP_TARGET_GROUP_ARN
    targetType: ip
    serviceRef:
      name: tso-service
      port: 3000
```

Charts reject enabled application Ingresses alongside nonempty bindings,
including additional ingress entries and Blockscout component ingresses.
Binding names retain the release name; names exceeding 63 characters are
shortened with a hash so releases sharing a long prefix remain distinct.
Direct Helm users must supply the same values and validate the external routing
policy; the CLI preflight is not automatically run by Helm.

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
  For overlapping selected routes, place narrower paths first: Blockscout
  `/api` and `/api/*` must have higher priority than the frontend `/*` rule.
- TSO and Proof Coordinator retain their existing separate-ALB requirement.
  Coordinator idle timeout must be at least 120 seconds. Other services may
  share an externally managed ALB with separate target groups and routing rules.
- Target groups must be HTTP/IP, with HTTP health checks on `traffic-port`,
  the health path and success codes from application values. Configure the
  listener default action separately (for example, a fixed 404).
- Restrict ALB/backend security groups and configure Pod routing/NetworkPolicy.
  The binding templates do not manage security groups. TSO still requires edge
  NetworkPolicy peers even though its Kubernetes Ingress is disabled. Disable
  `preparation.tsoAlbEdge`; set edge CIDRs to the chosen ALB subnets explicitly.
- Target groups are exclusive to one binding. Do not mix manually registered
  targets, other clusters or other TargetGroupBindings in the same group.

`scrollsdk setup alb` uses read-only AWS Describe operations. Its checks verify
resource references and selected route policy, not end-to-end connectivity or
every possible listener-rule priority interaction. After installation, test real
DNS/TLS, authorized requests, denied TSO paths and application health.

## Install, check and remove

1. Generate/bootstrap with a pinned SDK commit containing the application
   `templates/targetgroupbindings.yaml` files, and finish normal preparation.
   Final AWS spec-based `prep-charts` requires existing bindings or explicitly
   disabled HTTP ingress for the supported applications. Use the matching chart versions in the SDK Makefile;
   older chart versions do not render these bindings.
2. Install AWS Load Balancer Controller and its TargetGroupBinding CRD separately.
   Run `scrollsdk setup alb` to check AWS resources before installing workloads.
3. Install applications with their generated values using the normal targets,
   such as `make install-tso`. Each release installs its own bindings and Services.
   Configure security groups and NetworkPolicy before checking target health.
4. Run `scrollsdk setup alb --require-services` to verify the explicit Kubernetes
   context, installed CRD and ClusterIP Service ports. Then run
   `scrollsdk test ingress` to verify live bindings and healthy targets against
   current Service EndpointSlices, and test real HTTPS routes. The runtime check
   needs read access to bindings, Services and EndpointSlices and should be rerun
   after any rollout and target draining finish.
5. Uninstall applications with their normal targets, such as `make delete-tso`.
   Helm also removes their bindings; the controller deregisters the targets.
   External ALBs, listeners, rules and target groups remain. Keep the controller
   running until binding finalizers complete.

For an intentional binding removal without uninstalling the application, disable
its ingress and remove its `existingAlbBinding` marker and `targetGroupBindings`
entry in operator values, remove its spec binding, then regenerate and upgrade
that application release. The CLI rejects stale bindings or markers. Regeneration
alone does not modify installed resources.

The expected lifecycle test on a disposable deployment is: install, observe
healthy registered Pod targets, uninstall the application release, confirm the
ALB/listener/TG ARNs are unchanged and targets are deregistered, then reinstall
and verify new targets become healthy. Offline tests render all supported
application charts and check their bindings and Services belong to the same
release; they do not claim this live AWS test ran.
