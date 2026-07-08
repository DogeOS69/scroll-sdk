# proof-coordinator

![Version: 0.2.0](https://img.shields.io/badge/Version-0.2.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

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

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| command[0] | string | `"sh"` |  |
| command[1] | string | `"-ec"` |  |
| command[2] | string | `"mkdir -p /app/data/proof-artifacts && exec proof-coordinator --config /app/conf/ProofCoordinator.toml"` |  |
| configMaps.config.data."ProofCoordinator.toml" | string | `"proof_work_base_url = \"http://127.0.0.1:9300\"\ncoordinator_id = \"proof-coordinator\"\npoll_interval_ms = 1000\nlease_ttl_ms = 60000\n\n[artifact_store]\nkind = \"local_fs\"\nroot = \"/app/data/proof-artifacts\"\n\n[verifier]\nverifier_import_mode = \"dev_dummy\"\n"` |  |
| configMaps.config.enabled | bool | `true` |  |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `false` |  |
| defaultProbes.spec.failureThreshold | int | `3` |  |
| defaultProbes.spec.httpGet.path | string | `"/healthz"` |  |
| defaultProbes.spec.httpGet.port | string | `"http"` |  |
| defaultProbes.spec.periodSeconds | int | `10` |  |
| defaultProbes.spec.timeoutSeconds | int | `2` |  |
| env | list | `[]` |  |
| envFrom | list | `[]` |  |
| externalSecrets | object | `{}` |  |
| global.fullnameOverride | string | `"proof-coordinator"` |  |
| global.nameOverride | string | `"proof-coordinator"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/proof-coordinator"` |  |
| image.tag | string | `"latest"` |  |
| ingress.main.enabled | bool | `false` |  |
| persistence.config.enabled | bool | `true` |  |
| persistence.config.mountPath | string | `"/app/conf/"` |  |
| persistence.config.name | string | `"proof-coordinator-config"` |  |
| persistence.config.type | string | `"configMap"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.enabled | bool | `true` |  |
| persistence.data.mountPath | string | `"/app/data"` |  |
| persistence.data.name | string | `"proof-coordinator-data-pvc"` |  |
| persistence.data.retain | bool | `true` |  |
| persistence.data.size | string | `"10Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| persistence.secrets.enabled | bool | `false` |  |
| persistence.secrets.mountPath | string | `"/run/secrets"` |  |
| persistence.secrets.name | string | `"proof-coordinator-secrets"` |  |
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
| probes.liveness.<<.enabled | bool | `false` |  |
| probes.liveness.<<.spec.failureThreshold | int | `3` |  |
| probes.liveness.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.liveness.<<.spec.httpGet.port | string | `"http"` |  |
| probes.liveness.<<.spec.periodSeconds | int | `10` |  |
| probes.liveness.<<.spec.timeoutSeconds | int | `2` |  |
| probes.readiness.<<.custom | bool | `true` |  |
| probes.readiness.<<.enabled | bool | `false` |  |
| probes.readiness.<<.spec.failureThreshold | int | `3` |  |
| probes.readiness.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.readiness.<<.spec.httpGet.port | string | `"http"` |  |
| probes.readiness.<<.spec.periodSeconds | int | `10` |  |
| probes.readiness.<<.spec.timeoutSeconds | int | `2` |  |
| probes.startup.<<.custom | bool | `true` |  |
| probes.startup.<<.enabled | bool | `false` |  |
| probes.startup.<<.spec.failureThreshold | int | `3` |  |
| probes.startup.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.startup.<<.spec.httpGet.port | string | `"http"` |  |
| probes.startup.<<.spec.periodSeconds | int | `10` |  |
| probes.startup.<<.spec.timeoutSeconds | int | `2` |  |
| probes.startup.spec.failureThreshold | int | `24` |  |
| probes.startup.spec.httpGet.path | string | `"/healthz"` |  |
| probes.startup.spec.httpGet.port | string | `"http"` |  |
| probes.startup.spec.periodSeconds | int | `5` |  |
| probes.startup.spec.timeoutSeconds | int | `2` |  |
| resources.limits.cpu | string | `"500m"` |  |
| resources.limits.memory | string | `"1Gi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"256Mi"` |  |
| securityContext.allowPrivilegeEscalation | bool | `false` |  |
| securityContext.capabilities.drop[0] | string | `"ALL"` |  |
| securityContext.readOnlyRootFilesystem | bool | `true` |  |
| service.main.enabled | bool | `false` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `9400` |  |
| service.main.ports.http.protocol | string | `"TCP"` |  |
| serviceAccount.annotations | object | `{}` |  |
| serviceAccount.create | bool | `true` |  |
| serviceAccount.name | string | `"proof-coordinator"` |  |
| serviceMonitor.main.enabled | bool | `false` |  |

