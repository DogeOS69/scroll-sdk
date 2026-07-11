# attestation-signer

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.3.0](https://img.shields.io/badge/AppVersion-0.3.0-informational?style=flat-square)

A Helm chart for the DogeOS Correctness Attestation signer

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

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| args[0] | string | `"-c"` |  |
| args[1] | string | `"/etc/dogeos/attestation-signer.toml"` |  |
| configMaps.config.data."attestation-signer.toml" | string | `"[service]\nport = 4040\nnetwork = \"testnet\"\n\n[policy]\nmode = \"production_enforce\"\n\n[signer]\nbackend = \"aws_kms\"\n\n[tso]\nurl = \"http://tso-service:3000\"\ncallback_phase = \"attestation\"\n\n[database]\npath = \"/app/data/attestation-signer.sqlite\"\n"` |  |
| configMaps.config.enabled | bool | `true` |  |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `true` |  |
| defaultProbes.spec.httpGet.path | string | `"/health"` |  |
| defaultProbes.spec.httpGet.port | string | `"http"` |  |
| externalSecrets | object | `{}` |  |
| global.fullnameOverride | string | `"attestation-signer"` |  |
| global.nameOverride | string | `"attestation-signer"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/attestation-signer"` |  |
| image.tag | string | `"latest"` |  |
| ingress.main.enabled | bool | `false` |  |
| persistence.config.enabled | bool | `true` |  |
| persistence.config.mountPath | string | `"/etc/dogeos/"` |  |
| persistence.config.name | string | `"attestation-signer-config"` |  |
| persistence.config.readOnly | bool | `true` |  |
| persistence.config.type | string | `"configMap"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.enabled | bool | `true` |  |
| persistence.data.mountPath | string | `"/app/data"` |  |
| persistence.data.name | string | `"attestation-signer-data-pvc"` |  |
| persistence.data.retain | bool | `true` |  |
| persistence.data.size | string | `"1Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| probes.liveness.<<.custom | bool | `true` |  |
| probes.liveness.<<.enabled | bool | `true` |  |
| probes.liveness.<<.spec.httpGet.path | string | `"/health"` |  |
| probes.liveness.<<.spec.httpGet.port | string | `"http"` |  |
| probes.readiness.custom | bool | `true` |  |
| probes.readiness.enabled | bool | `true` |  |
| probes.readiness.spec.failureThreshold | int | `3` |  |
| probes.readiness.spec.httpGet.path | string | `"/ready"` |  |
| probes.readiness.spec.httpGet.port | string | `"http"` |  |
| probes.readiness.spec.periodSeconds | int | `10` |  |
| probes.readiness.spec.timeoutSeconds | int | `2` |  |
| probes.startup.custom | bool | `true` |  |
| probes.startup.enabled | bool | `true` |  |
| probes.startup.spec.failureThreshold | int | `24` |  |
| probes.startup.spec.httpGet.path | string | `"/ready"` |  |
| probes.startup.spec.httpGet.port | string | `"http"` |  |
| probes.startup.spec.initialDelaySeconds | int | `10` |  |
| probes.startup.spec.periodSeconds | int | `5` |  |
| probes.startup.spec.timeoutSeconds | int | `2` |  |
| resources.limits.cpu | string | `"500m"` |  |
| resources.limits.memory | string | `"512Mi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"128Mi"` |  |
| service.main.enabled | bool | `true` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `4040` |  |
| service.main.ports.http.protocol | string | `"TCP"` |  |
| serviceMonitor.main.enabled | bool | `true` |  |

