# withdrawal-processor

![Version: 0.1.22](https://img.shields.io/badge/Version-0.1.22-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

A Helm chart for the DOGEOS Withdrawal Processor

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

## glibc malloc arenas

The chart injects `MALLOC_ARENA_MAX` from the container's `limits.cpu` through
the Downward API at container startup. The value rounds up to whole CPUs:
`500m` gives 1 arena and `1500m` gives 2. This limits allocator memory retention;
it does not set the application's worker thread count or guarantee an RSS limit.

An explicit `MALLOC_ARENA_MAX` in `env` takes precedence. Both supported env
formats work:

```yaml
env:
  MALLOC_ARENA_MAX: "2"
```

```yaml
env:
  - name: MALLOC_ARENA_MAX
    value: "2"
```

Keep a CPU limit when relying on automatic arena sizing. If the container has
no CPU limit, Kubernetes exposes the node's allocatable CPU count instead;
set an explicit arena limit if that behavior is unsuitable for the workload.
In-place CPU resizing does not update environment variables in an already
running container. Restart the container for the arena limit to reflect the
new CPU limit. See the [Kubernetes Downward API documentation](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/#information-available-via-resourcefieldref).

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| networkPolicy.allowFrom.monitoring | list | `[]` | Peers allowed to scrape /metrics (shared port) |
| networkPolicy.allowFrom.operators | list | `[]` | Peers allowed to call the rotation routes |
| networkPolicy.allowFrom.proofCoordinator | list | `[]` | Proof-coordinator pods; opens proofWorkPort when non-empty |
| networkPolicy.allowFrom.tso | list | `[]` | tso-service pods (required when enabled) |
| networkPolicy.apiPort | int | `3000` | API port |
| networkPolicy.enabled | bool | `false` | Render an ingress NetworkPolicy for the unauthenticated API port |
| networkPolicy.proofWorkPort | int | `9300` | Proof-work listener port |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| global.fullnameOverride | string | `"withdrawal-processor"` |  |
| global.nameOverride | string | `"withdrawal-processor"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/withdrawal-processor"` |  |
| image.tag | string | `"110325-00"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.annotations | object | `{}` |  |
| persistence.data.enabled | bool | `true` |  |
| persistence.data.mountPath | string | `"/app/data"` |  |
| persistence.data.name | string | `"withdrawal-processor-data-pvc"` |  |
| persistence.data.retain | bool | `true` |  |
| persistence.data.size | string | `"1Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| probes.liveness.custom | bool | `true` |  |
| probes.liveness.enabled | bool | `true` |  |
| probes.liveness.spec.failureThreshold | int | `3` |  |
| probes.liveness.spec.httpGet.path | string | `"/healthz/live"` |  |
| probes.liveness.spec.httpGet.port | string | `"http"` |  |
| probes.liveness.spec.periodSeconds | int | `15` |  |
| probes.liveness.spec.timeoutSeconds | int | `2` |  |
| probes.readiness.custom | bool | `true` |  |
| probes.readiness.enabled | bool | `true` |  |
| probes.readiness.spec.failureThreshold | int | `3` |  |
| probes.readiness.spec.httpGet.path | string | `"/healthz/ready"` |  |
| probes.readiness.spec.httpGet.port | string | `"http"` |  |
| probes.readiness.spec.periodSeconds | int | `10` |  |
| probes.readiness.spec.timeoutSeconds | int | `2` |  |
| probes.startup.custom | bool | `true` |  |
| probes.startup.enabled | bool | `true` |  |
| probes.startup.spec.failureThreshold | int | `60` |  |
| probes.startup.spec.httpGet.path | string | `"/healthz/live"` |  |
| probes.startup.spec.httpGet.port | string | `"http"` |  |
| probes.startup.spec.periodSeconds | int | `10` |  |
| probes.startup.spec.timeoutSeconds | int | `2` |  |
| resources.limits.cpu | string | `"500m"` |  |
| resources.limits.memory | string | `"512Mi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"128Mi"` |  |
| service.main.annotations | object | `{}` |  |
| service.main.enabled | bool | `true` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `3000` |  |
| serviceMonitor.main.enabled | bool | `false` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
