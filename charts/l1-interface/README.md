# l1-interface

![Version: 0.0.20](https://img.shields.io/badge/Version-0.0.20-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: v0.1.0](https://img.shields.io/badge/AppVersion-v0.1.0-informational?style=flat-square)

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
| configMaps.env.data.DOGEOS_L1_INTERFACE_REPLAY_READ__ENABLED | string | `"true"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_REPLAY_READ__PROTOCOL_CONTEXT_JSON | string | `"/app/protocol_context.json"` |  |
| configMaps.env.data.DOGEOS_L1_INTERFACE_REPLAY_READ__SQLITE_PATH | string | `"/data/replay.sqlite"` |  |
| configMaps.env.enabled | bool | `true` |  |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| envFrom[0].secretRef.name | string | `"l1-interface-secret-env"` |  |
| envFrom[1].configMapRef.name | string | `"l1-interface-env"` |  |
| global.fullnameOverride | string | `"l1-interface"` |  |
| global.nameOverride | string | `"l1-interface"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/l1-interface"` |  |
| image.tag | string | `"110625-00"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.enabled | bool | `true` |  |
| persistence.data.mountPath | string | `"/data"` |  |
| persistence.data.retain | bool | `true` |  |
| persistence.data.size | string | `"1Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| persistence.genesis.enabled | bool | `true` |  |
| persistence.genesis.mountPath | string | `"/app/genesis/"` |  |
| persistence.genesis.name | string | `"genesis-config"` |  |
| persistence.genesis.readOnly | bool | `true` |  |
| persistence.genesis.type | string | `"configMap"` |  |
| persistence.protocol-context.enabled | bool | `true` |  |
| persistence.protocol-context.mountPath | string | `"/app/protocol_context.json"` |  |
| persistence.protocol-context.name | string | `"protocol-context-config"` |  |
| persistence.protocol-context.readOnly | bool | `true` |  |
| persistence.protocol-context.subPath | string | `"protocol_context.json"` |  |
| persistence.protocol-context.type | string | `"configMap"` |  |
| probes.liveness.custom | bool | `true` |  |
| probes.liveness.enabled | bool | `true` |  |
| probes.liveness.spec.failureThreshold | int | `3` |  |
| probes.liveness.spec.httpGet.path | string | `"/api/v1/health/live"` |  |
| probes.liveness.spec.httpGet.port | string | `"http"` |  |
| probes.liveness.spec.periodSeconds | int | `10` |  |
| probes.liveness.spec.timeoutSeconds | int | `2` |  |
| probes.readiness.custom | bool | `true` |  |
| probes.readiness.enabled | bool | `true` |  |
| probes.readiness.spec.failureThreshold | int | `3` |  |
| probes.readiness.spec.httpGet.path | string | `"/health"` |  |
| probes.readiness.spec.httpGet.port | string | `"http"` |  |
| probes.readiness.spec.periodSeconds | int | `10` |  |
| probes.readiness.spec.timeoutSeconds | int | `2` |  |
| probes.startup.custom | bool | `true` |  |
| probes.startup.enabled | bool | `true` |  |
| probes.startup.spec.failureThreshold | int | `60` |  |
| probes.startup.spec.httpGet.path | string | `"/health"` |  |
| probes.startup.spec.httpGet.port | string | `"http"` |  |
| probes.startup.spec.initialDelaySeconds | int | `10` |  |
| probes.startup.spec.periodSeconds | int | `10` |  |
| probes.startup.spec.timeoutSeconds | int | `3` |  |
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
| serviceMonitor.main.endpoints[0].interval | string | `"10s"` |  |
| serviceMonitor.main.endpoints[0].path | string | `"/api/v1/metrics"` |  |
| serviceMonitor.main.endpoints[0].port | string | `"http"` |  |
| serviceMonitor.main.endpoints[0].scheme | string | `"http"` |  |
| serviceMonitor.main.endpoints[0].scrapeTimeout | string | `"5s"` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
