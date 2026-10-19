# Shared public ALB

This guide describes a reference deployment pattern. Public RPC, Portal
(`frontends`) and Blockscout can share one AWS Load Balancer
Controller IngressGroup. Helm owns the hosts and paths; the controller creates
and reconciles the ALB listener rules and target groups. In this pattern, TSO and
Proof Coordinator use separate dedicated ALBs; do not add them to this group. See
[external ALB bindings](existing-alb.md) for those services.

Use Blockscout chart **0.1.13-dogeos** or later and the matching CLI sharedAlb
support. The example Makefile pins this chart version. Publish the chart before
using the generated Makefile against the OCI registry; a local source change
alone does not publish it.

## Operator responsibilities

- AWS operator: install/configure the AWS Load Balancer Controller and its IAM
  permissions; provide correctly tagged public subnets and pod reachability;
  issue an ACM certificate in the cluster region covering the public hosts.
  Keep only trusted releases/namespaces able to join this IngressGroup. Members
  share listener rules and can otherwise affect each other's traffic.
- Cloudflare operator: create the ACM validation records, then point
  `*.example.com` to the shared ALB's DNS name after initial reconciliation.
  This example uses DNS-only CNAME records. A wildcard covers one
  subdomain level, not the apex or deeper names. Explicit DNS records take
  precedence over the wildcard.
- Release operator: choose one group name and certificate ARN for all selected
  public Ingresses, set hosts in production values, and install the releases.
  Subsequent host/path edits within the certificate and DNS wildcard coverage
  require only a Helm upgrade. Do not manually edit controller-owned ALB rules.

## Production values

For Portal and public RPC, add the following annotations to `ingress.main`.
Use `ingressClassName: alb` and `enabled: true`. Retain complete `hosts` lists,
including the nested `paths` and any custom service routes: Helm replaces lists.
For a separately exposed RPC WebSocket hostname, apply the same annotations to
`ingress.websocket` and retain its WebSocket service port.

```yaml
ingress:
  main:
    enabled: true
    ingressClassName: alb
    annotations:
      alb.ingress.kubernetes.io/group.name: public-example
      alb.ingress.kubernetes.io/group.order: "100"
      alb.ingress.kubernetes.io/scheme: internet-facing
      alb.ingress.kubernetes.io/target-type: ip
      alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
      alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000
      alb.ingress.kubernetes.io/ssl-policy: ELBSecurityPolicy-TLS13-1-2-2021-06
      alb.ingress.kubernetes.io/healthcheck-path: /
      alb.ingress.kubernetes.io/success-codes: "200"
    hosts:
      - host: portal.example.com
        paths:
          - path: /
            pathType: Prefix
```

For RPC, use `rpc.example.com` and `success-codes: "200-499"`. This GET probe
checks reachability; verify JSON-RPC semantics separately with `eth_chainId` and
`eth_blockNumber`. HTTPS terminates at the ALB; no Kubernetes TLS Secret is
needed. The example exposes only listener 443, without an HTTP listener.

For Blockscout, start with [production values](values/blockscout-production.yaml):

1. Set both `blockscout-stack.blockscout.ingress.enabled` and
   `blockscout-stack.frontend.ingress.enabled` to `true`.
2. Set both `hostname` values to `explorer.example.com`; use `className: alb`.
3. Set the same group name, certificate and common ALB annotations as above.
   Keep API `group.order: "10"`, `healthcheck-path: /api/health/readiness`;
   frontend `group.order: "100"`, `healthcheck-path: /api/healthz`.
4. Remove `NEXT_PUBLIC_API_HOST` and `NEXT_PUBLIC_APP_HOST` from `frontend.env`:
   the enabled upstream Ingress templates emit these from the hostnames. Use
   HTTPS for both API/APP protocols and WSS for the API WebSocket protocol.
   Put chain/currency settings in `config.network`, not duplicate `COIN`,
   `COIN_NAME` or `NEXT_PUBLIC_NETWORK_*` environment entries.
5. Keep `config.prometheus.ingressWhitelist.enabled: false`: its additional
   Ingress is NGINX-specific. Keep credentials in `blockscout-secret-env`, with
   a working application `DATABASE_URL` and database TLS as required by RDS.
   This configuration does not create/reset a database or its password.
6. Do not set `paths` for either Blockscout Ingress unless intentionally
   replacing the **complete** upstream route list. Do not leave null annotation
   values or external `targetGroupBindings` on these shared releases.

The default backend routes include `/api`, `/socket`, `/public-metrics` and
exact authentication endpoints; the frontend has `/` as a catch-all. Thus browser
pages and static assets do not each need an Ingress path. The backend routes run
before the frontend catch-all. These defaults intentionally expose
`/public-metrics`; disabling the extra metrics Ingress does not remove that
backend route. To exclude it, supply a complete audited backend `paths` list
retaining `/socket` and the required API/auth routes.

Health probes contact the target directly. A public request to frontend
`/api/healthz` is routed to the API by the `/api` prefix and is not a valid test of
frontend target health.

## Verification

After Helm reconciliation, check that all selected Ingresses report one ALB,
that the HTTPS listener uses the intended certificate, and that all target
groups are healthy. Verify Portal root and a nested page, JSON-RPC POST,
Blockscout block/statistics APIs, a block detail page and a Phoenix heartbeat on
`wss://explorer.example.com/socket/v2/websocket?vsn=2.0.0`. Check indexer height
against the chain. A healthy ALB does not prove bridge operations or fresh block
production.
