# tso-service

![Version: 0.1.5](https://img.shields.io/badge/Version-0.1.5-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

A Helm chart for the DOGEOS TSO Service

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| DogeOS69 | <support@dogeos.com> |  |

## Requirements

Kubernetes: `>=1.22.0-0`

| Repository | Name | Version |
|------------|------|---------|
| oci://ghcr.io/dogeos69/scroll-sdk/helm | external-secrets-lib | 0.0.4 |
| oci://ghcr.io/scroll-tech/scroll-sdk/helm | common | 1.5.1 |

## Public edge

The Ingress routes only `/health` and the transport-signed `/signer/*` routes;
every other TSO route stays in-cluster. With `networkPolicy.enabled`,
`allowFrom.edge` admits the Ingress source (the ALB subnets for
`ingressClassName: alb` with target-type ip, or the ingress-nginx pods) to the
whole API port: a NetworkPolicy works at L4, so the path restriction is
enforced only by the Ingress/ALB rules, not by the policy.

With `ingressClassName: alb` the TSO gets its own ALB (no
`alb.ingress.kubernetes.io/group.name`), separate from the proof coordinator's.
Separation is for independent configuration and change scope, per-ALB
security-group source rules (`alb.ingress.kubernetes.io/inbound-cidrs`,
optional and unset by default) and per-ALB idle timeouts. It is not for rate
limiting: a WAF rule can be scoped by host. The TSO's security is the signed
signer requests, not a source allowlist, since operators may have no static IPs.

If a WAF web ACL is attached (`alb.ingress.kubernetes.io/wafv2-acl-arn`), use a
per-IP rate-based rule and set body oversize handling to **continue**: WAF
inspects only the first 8 KiB of a body, and signature callbacks are megabytes,
so a match or block action on oversize bodies would reject legitimate signers.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| networkPolicy.allowFrom.edge | list | `[]` | Public Ingress sources: ALB subnets (ipBlock) or ingress-nginx pods |
| networkPolicy.allowFrom.monitoring | list | `[]` | Peers allowed to scrape /metrics (shared port) |
| networkPolicy.allowFrom.operators | list | `[]` | Optional operator peers |
| networkPolicy.allowFrom.signers | list | `[]` | Signer pods posting callbacks (required when enabled) |
| networkPolicy.allowFrom.withdrawalProcessor | list | `[]` | Withdrawal-processor pods (required when enabled) |
| networkPolicy.enabled | bool | `false` | Render an ingress NetworkPolicy for the unauthenticated API port |
| networkPolicy.port | int | `3000` | API port |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `true` |  |
| defaultProbes.spec.httpGet.path | string | `"/health"` |  |
| defaultProbes.spec.httpGet.port | string | `"http"` |  |
| global.fullnameOverride | string | `"tso-service"` |  |
| global.nameOverride | string | `"tso-service"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/tso-service"` |  |
| image.tag | string | `"110625-00"` |  |
| ingress.main.annotations | object | `{}` |  |
| ingress.main.enabled | bool | `true` |  |
| ingress.main.hosts[0].host | string | `"tso.scrollsdk"` |  |
| ingress.main.hosts[0].paths[0].path | string | `"/health"` |  |
| ingress.main.hosts[0].paths[0].pathType | string | `"Exact"` |  |
| ingress.main.hosts[0].paths[1].path | string | `"/signer"` | Transport-signed signer routes (poll, submit, reject) |
| ingress.main.hosts[0].paths[1].pathType | string | `"Prefix"` |  |
| ingress.main.ingressClassName | string | `"nginx"` |  |
| ingress.main.labels | object | `{}` |  |
| ingress.main.primary | bool | `true` |  |
| probes.liveness.<<.custom | bool | `true` |  |
| probes.liveness.<<.enabled | bool | `true` |  |
| probes.liveness.<<.spec.httpGet.path | string | `"/health"` |  |
| probes.liveness.<<.spec.httpGet.port | string | `"http"` |  |
| probes.readiness.<<.custom | bool | `true` |  |
| probes.readiness.<<.enabled | bool | `true` |  |
| probes.readiness.<<.spec.httpGet.path | string | `"/health"` |  |
| probes.readiness.<<.spec.httpGet.port | string | `"http"` |  |
| probes.startup.<<.custom | bool | `true` |  |
| probes.startup.<<.enabled | bool | `true` |  |
| probes.startup.<<.spec.httpGet.path | string | `"/health"` |  |
| probes.startup.<<.spec.httpGet.port | string | `"http"` |  |
| probes.startup.spec.failureThreshold | int | `12` |  |
| probes.startup.spec.httpGet.path | string | `"/health"` |  |
| probes.startup.spec.httpGet.port | string | `"http"` |  |
| probes.startup.spec.initialDelaySeconds | int | `10` |  |
| probes.startup.spec.periodSeconds | int | `5` |  |
| resources.limits.cpu | string | `"500m"` |  |
| resources.limits.memory | string | `"512Mi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"128Mi"` |  |
| service.main.enabled | bool | `true` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `3000` |  |
| serviceMonitor.main.enabled | bool | `false` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)

Beta.6 serves `/metrics` on the API listener. No separate metrics port or
metrics environment override is configured by this chart. Monitoring peers
therefore have access to the other routes on that port. The dedicated listener
in dogeos-core #1406 is not part of beta.6. Production values and examples
leave the policy disabled until the deployment supplies all required peers;
configure Prometheus namespace/pod selectors and any ingress proxy sources
before enabling it, then verify callbacks and scrapes on an enforcing CNI.
