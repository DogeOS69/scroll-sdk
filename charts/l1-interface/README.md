# l1-interface

![Version: 0.0.12](https://img.shields.io/badge/Version-0.0.12-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.0.1](https://img.shields.io/badge/AppVersion-0.0.1-informational?style=flat-square)

A Helm chart for the DogeOS L1 interface

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
| command[0] | string | `"/usr/local/bin/l1_interface"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_API_BIND_ADDRESS | string | `"0.0.0.0:8545"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_BEACON_API_LISTEN_ADDRESS | string | `"0.0.0.0:5052"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_DATABASE_URL | string | `"sqlite:///data/l1-interface.sqlite"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_GENESIS_JSON_PATH | string | `"/app/genesis/genesis.json"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_HEALTH_LISTEN_ADDRESS | string | `"0.0.0.0:9090"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_SEQUENCER_GENESIS_MODE | string | `"true"` |  |
| configMaps.env.enabled | bool | `true` |  |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `true` |  |
| defaultProbes.spec.httpGet.path | string | `"/health"` |  |
| defaultProbes.spec.httpGet.port | string | `"http"` |  |
| envFrom[0].secretRef.name | string | `"l1-interface-secret-env"` |  |
| envFrom[1].configMapRef.name | string | `"l1-interface-env"` |  |
| global.fullnameOverride | string | `"l1-interface"` |  |
| global.nameOverride | string | `"l1-interface"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/l1-interface"` |  |
| image.tag | string | `"090425-01"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.enabled | bool | `true` |  |
| persistence.data.mountPath | string | `"/data"` |  |
| persistence.data.size | string | `"1Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| persistence.genesis.enabled | bool | `true` |  |
| persistence.genesis.mountPath | string | `"/app/genesis/"` |  |
| persistence.genesis.name | string | `"genesis-config"` |  |
| persistence.genesis.readOnly | bool | `true` |  |
| persistence.genesis.type | string | `"configMap"` |  |
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
| resources.limits.cpu | string | `"500m"` |  |
| resources.limits.memory | string | `"1Gi"` |  |
| resources.requests.cpu | string | `"200m"` |  |
| resources.requests.memory | string | `"256Mi"` |  |
| service.main.enabled | bool | `true` |  |
| service.main.ports.admin.enabled | bool | `true` |  |
| service.main.ports.admin.port | int | `9091` |  |
| service.main.ports.admin.protocol | string | `"TCP"` |  |
| service.main.ports.admin.targetPort | int | `9091` |  |
| service.main.ports.beacon.enabled | bool | `true` |  |
| service.main.ports.beacon.port | int | `5052` |  |
| service.main.ports.beacon.protocol | string | `"TCP"` |  |
| service.main.ports.beacon.targetPort | int | `5052` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `9090` |  |
| service.main.ports.http.protocol | string | `"TCP"` |  |
| service.main.ports.http.targetPort | int | `9090` |  |
| service.main.ports.jsonrpc.enabled | bool | `true` |  |
| service.main.ports.jsonrpc.port | int | `8545` |  |
| service.main.ports.jsonrpc.protocol | string | `"TCP"` |  |
| service.main.ports.jsonrpc.targetPort | int | `8545` |  |
| serviceMonitor.main.enabled | bool | `true` |  |
| serviceMonitor.main.endpoints[0].interval | string | `"30s"` |  |
| serviceMonitor.main.endpoints[0].path | string | `"/api/v1/metrics"` |  |
| serviceMonitor.main.endpoints[0].port | string | `"http"` |  |
| serviceMonitor.main.endpoints[0].scheme | string | `"http"` |  |
| serviceMonitor.main.endpoints[0].scrapeTimeout | string | `"10s"` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
