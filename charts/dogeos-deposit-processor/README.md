# dogeos-deposit-processor

![Version: 0.1.4](https://img.shields.io/badge/Version-0.1.4-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

A Helm chart for the DogeOS Bridge deposit processor

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
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_ANVIL_RPC_URL | string | `"http://l1-devnet:8545"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_CONFIRMATIONS | string | `"60"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_DB_PATH | string | `"/data/deposits.db"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_DEPOSIT_DOGE_ADDRESS | string | `"DARn34TPXXQZgcVo5nZ7iqvJJRsm2PkjSC"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_DOGE_ACCESS_TYPE | string | `"blockbook"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_DOGE_RPC_URL | string | `"https://dogebook.nownodes.io"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_FAST_SYNC | string | `"true"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_GAS_LIMIT | string | `"500000"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_GENERATE_L1_MESSAGE_TX | string | `"true"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_L1_MESSENGER_ADDRESS | string | `"0xEd07bbda5D53AA599E693602E45c2d985026eD1c"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_MOAT_ADDRESS | string | `"0x0000000000000000000000000000000000000000"` |  |
| configMaps.env.data.DOGEOS_DEPOSIT_PROCESSOR_START_HEIGHT | string | `"5546370"` |  |
| configMaps.env.enabled | bool | `true` |  |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `true` |  |
| defaultProbes.spec.httpGet.path | string | `"/healthz"` |  |
| defaultProbes.spec.httpGet.port | string | `"http"` |  |
| envFrom[0].configMapRef.name | string | `"dogeos-deposit-processor-env"` |  |
| env[0].name | string | `"DOGEOS_DEPOSIT_PROCESSOR_LOG_LEVEL"` |  |
| env[0].value | string | `"debug"` |  |
| env[1].name | string | `"DOGEOS_DEPOSIT_PROCESSOR_NODE_ENV"` |  |
| env[1].value | string | `"development"` |  |
| env[2].name | string | `"DOGEOS_DEPOSIT_PROCESSOR_PORT"` |  |
| env[2].value | string | `"3000"` |  |
| env[3].name | string | `"DOGEOS_DEPOSIT_PROCESSOR_HOST"` |  |
| env[3].value | string | `"0.0.0.0"` |  |
| externalSecrets.dogeos-deposit-processor-secrets.data[0].remoteRef.key | string | `"dogeos/deposit-processor/nownodes"` |  |
| externalSecrets.dogeos-deposit-processor-secrets.data[0].remoteRef.property | string | `"api-key"` |  |
| externalSecrets.dogeos-deposit-processor-secrets.data[0].secretKey | string | `"nownodes-api-key"` |  |
| externalSecrets.dogeos-deposit-processor-secrets.provider | string | `"aws"` |  |
| externalSecrets.dogeos-deposit-processor-secrets.refreshInterval | string | `"2m"` |  |
| externalSecrets.dogeos-deposit-processor-secrets.serviceAccount | string | `"external-secrets"` |  |
| global.fullnameOverride | string | `"dogeos-deposit-processor"` |  |
| global.nameOverride | string | `"dogeos-deposit-processor"` |  |
| image.pullPolicy | string | `"IfNotPresent"` |  |
| image.repository | string | `"dogeos69/dogeos-deposit-processor"` |  |
| image.tag | string | `"latest"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.enabled | bool | `true` |  |
| persistence.data.mountPath | string | `"/data"` |  |
| persistence.data.size | string | `"1Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| probes.liveness.<<.custom | bool | `true` |  |
| probes.liveness.<<.enabled | bool | `true` |  |
| probes.liveness.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.liveness.<<.spec.httpGet.port | string | `"http"` |  |
| probes.readiness.<<.custom | bool | `true` |  |
| probes.readiness.<<.enabled | bool | `true` |  |
| probes.readiness.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.readiness.<<.spec.httpGet.port | string | `"http"` |  |
| probes.startup.<<.custom | bool | `true` |  |
| probes.startup.<<.enabled | bool | `true` |  |
| probes.startup.<<.spec.httpGet.path | string | `"/healthz"` |  |
| probes.startup.<<.spec.httpGet.port | string | `"http"` |  |
| resources.limits.cpu | string | `"500m"` |  |
| resources.limits.memory | string | `"512Mi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"128Mi"` |  |
| service.main.enabled | bool | `true` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `3000` |  |
| serviceMonitor.main.enabled | bool | `true` |  |
| serviceMonitor.main.endpoints[0].interval | string | `"1m"` |  |
| serviceMonitor.main.endpoints[0].path | string | `"/metrics"` |  |
| serviceMonitor.main.endpoints[0].port | string | `"http"` |  |
| serviceMonitor.main.endpoints[0].scrapeTimeout | string | `"10s"` |  |
| serviceMonitor.main.labels.release | string | `"scroll-sdk"` |  |
| serviceMonitor.main.serviceName | string | `"{{ include \"scroll.common.lib.chart.names.fullname\" $ }}"` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
