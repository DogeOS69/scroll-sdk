# proof-coordinator

![Version: 0.3.2](https://img.shields.io/badge/Version-0.3.2-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

A Helm chart for the DogeOS proof-coordinator service

**Homepage:** <https://github.com/DogeOS69/dogeos-core>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| DogeOS69 | <support@dogeos.com> |  |

## Source Code

* <https://github.com/DogeOS69/dogeos-core/tree/develop/crates/proof_coordinator>

## Requirements

Kubernetes: `>=1.22.0-0`

| Repository | Name | Version |
|------------|------|---------|
| oci://ghcr.io/dogeos69/scroll-sdk/helm | external-secrets-lib | 0.0.4 |
| oci://ghcr.io/scroll-tech/scroll-sdk/helm | common | 1.5.1 |

## Resource naming

Chart-owned StatefulSet, Service, ConfigMap, PVC, SecretStore, ExternalSecret,
and target Secret names derive from the Helm release fullname. Production
values use the logical ExternalSecret key `secrets`, rendered locally as
`<release-fullname>-secrets`; the remote secret key remains an explicit external
integration value. Leave `serviceAccount.name` empty for release-derived naming,
or set it explicitly when an EKS IRSA trust policy pins a stable
namespace/ServiceAccount OIDC subject.

## Application configuration

The chart treats `ProofCoordinator.toml` as an opaque application-owned file;
it does not duplicate or interpret the TOML schema. Supply production config
from its native file so Helm owns the ConfigMap and rolls the StatefulSet when
the content changes:

```bash
helm upgrade --install proof-coordinator ./charts/proof-coordinator \
  --values ./charts/proof-coordinator/values/production.yaml \
  --set-file proofCoordinator.config.content=./ProofCoordinator.toml
```

GitOps deployments may instead set
`proofCoordinator.config.existingConfigMap`. The two sources are mutually
exclusive. Use an immutable/content-hashed external name so configuration
changes update the pod template. The bundled TOML is only the default
local-development posture; production values require an explicit source.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| command[0] | string | `"sh"` |  |
| command[1] | string | `"-ec"` |  |
| command[2] | string | `"exec proof-coordinator --config /app/conf/ProofCoordinator.toml"` |  |
| configMaps.config.data | object | `{}` |  |
| configMaps.config.enabled | bool | `false` | Internal common-chart ConfigMap rendering is disabled so opaque TOML is never evaluated with `tpl`. |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `true` |  |
| defaultProbes.spec.failureThreshold | int | `3` |  |
| defaultProbes.spec.httpGet.path | string | `"/healthz"` |  |
| defaultProbes.spec.httpGet.port | string | `"prover"` |  |
| defaultProbes.spec.periodSeconds | int | `10` |  |
| defaultProbes.spec.timeoutSeconds | int | `2` |  |
| env | list | `[]` |  |
| envFrom | list | `[]` |  |
| externalSecrets | object | `{}` |  |
| global.fullnameOverride | string | `""` | Optional advanced override; ordinary resource names derive from the Helm release. |
| global.nameOverride | string | `""` | Optional advanced override; ordinary resource names derive from the Helm release. |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/proof-coordinator"` |  |
| image.tag | string | `"latest"` |  |
| ingress.main.enabled | bool | `false` |  |
| initContainers.prepare-proof-data-directories.args[0] | string | `"mkdir -p '/app/data/proof-artifacts' '/app/data/proof-artifacts/runtime/coordinator-staging' '/app/data/proof-artifacts/runtime/bridge-prepared-bundles' '/app/data/proof-artifacts/runtime/scroll-batch-materializer-output' '/app/data/proof-artifacts/runtime/scroll-chunk-sidecar-scratch' '/app/data/proof-artifacts/runtime/scroll-batch-subprocess-scratch' '/app/data/proof-artifacts/runtime/scroll-batch-da-cache/blobs' '/app/data/proof-artifacts/runtime/bridge-da/blobs'"` |  |
| initContainers.prepare-proof-data-directories.command[0] | string | `"/bin/sh"` |  |
| initContainers.prepare-proof-data-directories.command[1] | string | `"-ec"` |  |
| initContainers.prepare-proof-data-directories.image | string | `"busybox:1.36.1"` |  |
| initContainers.prepare-proof-data-directories.volumeMounts[0].mountPath | string | `"/app/data"` |  |
| initContainers.prepare-proof-data-directories.volumeMounts[0].name | string | `"data"` |  |
| persistence.config.enabled | bool | `true` |  |
| persistence.config.mountPath | string | `"/app/conf/"` |  |
| persistence.config.type | string | `"configMap"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.enabled | bool | `true` |  |
| persistence.data.mountPath | string | `"/app/data"` |  |
| persistence.data.retain | bool | `true` |  |
| persistence.data.size | string | `"10Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| persistence.secrets.enabled | bool | `false` |  |
| persistence.secrets.mountPath | string | `"/run/secrets"` |  |
| persistence.secrets.name | string | `""` | Optional existing/stable Secret name; empty derives `<release-fullname>-secrets`. |
| persistence.secrets.readOnly | bool | `true` |  |
| persistence.secrets.type | string | `"secret"` |  |
| persistence.tmp.enabled | bool | `true` |  |
| persistence.tmp.mountPath | string | `"/tmp"` |  |
| persistence.tmp.sizeLimit | string | `"1Gi"` |  |
| persistence.tmp.type | string | `"emptyDir"` |  |
| podSecurityContext.fsGroup | int | `65532` |  |
| podSecurityContext.fsGroupChangePolicy | string | `"OnRootMismatch"` |  |
| podSecurityContext.runAsGroup | int | `65532` |  |
| podSecurityContext.runAsNonRoot | bool | `true` |  |
| podSecurityContext.runAsUser | int | `65532` |  |
| podSecurityContext.seccompProfile.type | string | `"RuntimeDefault"` |  |
| probes.liveness.<<.custom | bool | `true` |  |
| probes.liveness.<<.enabled | bool | `true` |  |
| probes.liveness.<<.spec.failureThreshold | int | `3` |  |
| probes.liveness.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.liveness.<<.spec.httpGet.port | string | `"prover"` |  |
| probes.liveness.<<.spec.periodSeconds | int | `10` |  |
| probes.liveness.<<.spec.timeoutSeconds | int | `2` |  |
| probes.readiness.custom | bool | `true` |  |
| probes.readiness.enabled | bool | `true` |  |
| probes.readiness.spec.failureThreshold | int | `3` |  |
| probes.readiness.spec.httpGet.path | string | `"/readyz"` |  |
| probes.readiness.spec.httpGet.port | string | `"prover"` |  |
| probes.readiness.spec.periodSeconds | int | `10` |  |
| probes.readiness.spec.timeoutSeconds | int | `2` |  |
| probes.startup.<<.custom | bool | `true` |  |
| probes.startup.<<.enabled | bool | `true` |  |
| probes.startup.<<.spec.failureThreshold | int | `3` |  |
| probes.startup.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.startup.<<.spec.httpGet.port | string | `"prover"` |  |
| probes.startup.<<.spec.periodSeconds | int | `10` |  |
| probes.startup.<<.spec.timeoutSeconds | int | `2` |  |
| probes.startup.spec.failureThreshold | int | `24` |  |
| probes.startup.spec.httpGet.path | string | `"/healthz"` |  |
| probes.startup.spec.httpGet.port | string | `"prover"` |  |
| probes.startup.spec.periodSeconds | int | `5` |  |
| probes.startup.spec.timeoutSeconds | int | `2` |  |
| proofCoordinator.config.content | string | `""` | Opaque TOML content; normally supplied with `--set-file`. |
| proofCoordinator.config.existingConfigMap | string | `""` | Existing ConfigMap containing the configured key. Mutually exclusive with content. |
| proofCoordinator.config.key | string | `"ProofCoordinator.toml"` | ConfigMap key and mounted filename. |
| proofCoordinator.config.required | bool | `false` | Require an explicit content or existingConfigMap source. Production sets this true. |
| resources.limits.cpu | string | `"500m"` |  |
| resources.limits.memory | string | `"1Gi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"256Mi"` |  |
| securityContext.allowPrivilegeEscalation | bool | `false` |  |
| securityContext.capabilities.drop[0] | string | `"ALL"` |  |
| securityContext.readOnlyRootFilesystem | bool | `true` |  |
| service.main.enabled | bool | `false` |  |
| service.main.ports.prover.enabled | bool | `true` |  |
| service.main.ports.prover.port | int | `7788` |  |
| service.main.ports.prover.primary | bool | `true` |  |
| service.main.ports.prover.protocol | string | `"TCP"` |  |
| service.main.ports.prover.targetPort | int | `7788` |  |
| serviceAccount.annotations | object | `{}` |  |
| serviceAccount.create | bool | `true` |  |
| serviceAccount.name | string | `""` | Empty derives the release fullname; set explicitly for an IRSA-pinned workload identity. |
| serviceMonitor.main.enabled | bool | `false` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
