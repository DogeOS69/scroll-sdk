# cubesigner-signer

![Version: 0.1.9](https://img.shields.io/badge/Version-0.1.9-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.3.0-beta.2](https://img.shields.io/badge/AppVersion-0.3.0--beta.2-informational?style=flat-square)

A Helm chart for the DOGEOS CubeSigner Attestation Signer

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
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `true` |  |
| defaultProbes.spec.httpGet.path | string | `"/health"` |  |
| defaultProbes.spec.httpGet.port | string | `"http"` |  |
| env[0].name | string | `"DOGEOS_CUBESIGNER_SIGNER_PORT"` |  |
| env[0].value | string | `"3000"` |  |
| env[1].name | string | `"DOGEOS_CUBESIGNER_SIGNER_NETWORK"` |  |
| env[1].value | string | `"testnet"` |  |
| env[2].name | string | `"DOGEOS_CUBESIGNER_SIGNER_TSO_URL"` |  |
| env[2].value | string | `"http://dogeos-tso:3000"` |  |
| env[3].name | string | `"DOGEOS_CUBESIGNER_SIGNER_PROTOCOL_CONTEXT_JSON"` |  |
| env[3].value | string | `"/app/protocol_context.json"` |  |
| env[4].name | string | `"DOGEOS_CUBESIGNER_SIGNER_SIGNATURE_DELAY"` |  |
| env[4].value | string | `"1"` |  |
| env[5].name | string | `"DOGEOS_CUBESIGNER_SIGNER_POLL_INTERVAL"` |  |
| env[5].value | string | `"5000"` |  |
| env[6].name | string | `"DOGEOS_CUBESIGNER_SIGNER_CS_KEY_ID"` |  |
| env[6].value | string | `""` |  |
| env[7].name | string | `"DOGEOS_CUBESIGNER_SIGNER_CS_SESSION_PATH"` |  |
| env[7].value | string | `"/etc/cubesigner/session.json"` |  |
| env[8].name | string | `"DOGEOS_CUBESIGNER_SIGNER_BODY_LIMIT"` |  |
| env[8].value | string | `"5mb"` |  |
| global.fullnameOverride | string | `"cubesigner-signer"` |  |
| global.nameOverride | string | `"cubesigner-signer"` |  |
| image.pullPolicy | string | `"IfNotPresent"` |  |
| image.repository | string | `"dogeos69/cubesigner-signer"` |  |
| image.tag | string | `"v0.3.0-beta.2"` |  |
| persistence.protocol-context.enabled | bool | `true` |  |
| persistence.protocol-context.mountPath | string | `"/app/protocol_context.json"` |  |
| persistence.protocol-context.name | string | `"protocol-context-config"` |  |
| persistence.protocol-context.readOnly | bool | `true` |  |
| persistence.protocol-context.subPath | string | `"protocol_context.json"` |  |
| persistence.protocol-context.type | string | `"configMap"` |  |
| persistence.session.enabled | bool | `true` |  |
| persistence.session.mountPath | string | `"/etc/cubesigner"` |  |
| persistence.session.name | string | `"cubesigner-session-secret-vol"` |  |
| persistence.session.readOnly | bool | `true` |  |
| persistence.session.secretName | string | `"cubesigner-default-session-secret"` |  |
| persistence.session.type | string | `"secret"` |  |
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
| serviceMonitor.main.enabled | bool | `true` |  |
| serviceMonitor.main.endpoints[0].interval | string | `"10s"` |  |
| serviceMonitor.main.endpoints[0].port | string | `"http"` |  |
| serviceMonitor.main.endpoints[0].scrapeTimeout | string | `"5s"` |  |
| serviceMonitor.main.labels.release | string | `"scroll-sdk"` |  |
| serviceMonitor.main.serviceName | string | `"{{ include \"scroll.common.lib.chart.names.fullname\" $ }}"` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
