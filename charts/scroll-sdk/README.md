# scroll-sdk

![Version: 0.1.7-dogeos](https://img.shields.io/badge/Version-0.1.7--dogeos-informational?style=flat-square) ![AppVersion: v0.1.0](https://img.shields.io/badge/AppVersion-v0.1.0-informational?style=flat-square)

scroll helm charts to deploy scroll sdk

**Homepage:** <https://github.com/scroll-tech/scroll-sdk>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| scroll-tech | <sebastien@scroll.io> |  |

## Requirements

Kubernetes: `>=1.22.0-0`

| Repository | Name | Version |
|------------|------|---------|
| oci://ghcr.io/dogeos69/scroll-sdk/helm | blockscout | 0.1.4-dogeos |
| oci://ghcr.io/dogeos69/scroll-sdk/helm | contracts | 0.1.5-dogeos |
| oci://ghcr.io/dogeos69/scroll-sdk/helm | l2-bootnode | 0.1.3-dogeos |
| oci://ghcr.io/dogeos69/scroll-sdk/helm | l2-rpc | 0.1.3-dogeos |
| oci://ghcr.io/dogeos69/scroll-sdk/helm | l2-sequencer | 0.1.3-dogeos |
| oci://ghcr.io/scroll-tech/scroll-sdk/helm | l1-devnet | 0.1.3 |
| oci://ghcr.io/scroll-tech/scroll-sdk/helm | scroll-common | 0.1.0 |
| oci://ghcr.io/scroll-tech/scroll-sdk/helm | scroll-monitor | 0.1.0 |
| oci://registry-1.docker.io/bitnamicharts | postgresql | 15.5.0 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| admin-system-backend.enabled | bool | `false` |  |
| admin-system-cron.enabled | bool | `false` |  |
| admin-system-dashboard.enabled | bool | `false` |  |
| admin-system-dashboard.ingress.main.enabled | bool | `true` |  |
| admin-system-dashboard.ingress.main.hosts[0].host | string | `"admin-system-dashboard.scrollsdk"` |  |
| admin-system-dashboard.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| admin-system-dashboard.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| balance-checker.enabled | bool | `false` |  |
| blockscout-sc-verifier.enabled | bool | `false` |  |
| blockscout.blockscout-stack.frontend.replicaCount | int | `1` |  |
| blockscout.enabled | bool | `true` |  |
| bridge-history-api.enabled | bool | `false` |  |
| bridge-history-api.ingress.main.annotations | object | `{}` |  |
| bridge-history-api.ingress.main.enabled | bool | `true` |  |
| bridge-history-api.ingress.main.hosts[0].host | string | `"bridge-history-api.scrollsdk"` |  |
| bridge-history-api.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| bridge-history-api.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| bridge-history-api.ingress.main.ingressClassName | string | `"nginx"` |  |
| bridge-history-api.ingress.main.labels | object | `{}` |  |
| bridge-history-api.ingress.main.primary | bool | `true` |  |
| bridge-history-fetcher.enabled | bool | `false` |  |
| chain-monitor.enabled | bool | `false` |  |
| contracts.enabled | bool | `true` |  |
| coordinator-api.enabled | bool | `false` |  |
| coordinator-cron.enabled | bool | `false` |  |
| db.bridge_history_password | string | `"test1234"` |  |
| db.chain_monitor_password | string | `"test1234"` |  |
| db.gas_oracle_password | string | `"test1234"` |  |
| db.pg_host | string | `"postgresql"` |  |
| db.pg_password | string | `"qwerty12345"` |  |
| db.pg_port | string | `"5432"` |  |
| db.pg_user | string | `"postgres"` |  |
| db.rollup_node_password | string | `"test1234"` |  |
| db.rpc_gateway_password | string | `"test1234"` |  |
| frontends.enabled | bool | `false` |  |
| frontends.ingress.main.enabled | bool | `true` |  |
| frontends.ingress.main.hosts[0].host | string | `"frontends.scrollsdk"` |  |
| frontends.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| frontends.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| gas-oracle.enabled | bool | `false` |  |
| l1-devnet.enabled | bool | `true` |  |
| l1-devnet.ingress.main.enabled | bool | `true` |  |
| l1-devnet.ingress.main.hosts[0].host | string | `"l1-devnet.scrollsdk"` |  |
| l1-devnet.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| l1-devnet.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| l1-explorer.blockscout-stack.frontend.replicaCount | int | `1` |  |
| l1-explorer.enabled | bool | `false` |  |
| l1-explorer.ingress.main.enabled | bool | `true` |  |
| l1-explorer.ingress.main.hosts[0].host | string | `"l1-explorer.scrollsdk"` |  |
| l1-explorer.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| l1-explorer.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| l1-explorer.ingress.main.ingressClassName | string | `"nginx"` |  |
| l2-bootnode.enabled | bool | `true` |  |
| l2-rpc.enabled | bool | `true` |  |
| l2-rpc.ingress.main.enabled | bool | `true` |  |
| l2-rpc.ingress.main.hosts[0].host | string | `"l2-rpc.scrollsdk"` |  |
| l2-rpc.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| l2-rpc.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| l2-rpc.ingress.main.ingressClassName | string | `"nginx"` |  |
| l2-sequencer.enabled | bool | `true` |  |
| postgresql.auth.enablePostgresUser | bool | `true` |  |
| postgresql.auth.postgresPassword | string | `"qwerty12345"` |  |
| postgresql.enabled | bool | `true` |  |
| postgresql.fullnameOverride | string | `"postgresql"` |  |
| postgresql.nameOverride | string | `"postgresql"` |  |
| postgresql.primary.extendedConfiguration | string | `"max_connections = 400\n"` |  |
| postgresql.primary.livenessProbe.enabled | bool | `false` |  |
| postgresql.primary.persistentVolumeClaimRetentionPolicy.enabled | bool | `true` |  |
| postgresql.primary.persistentVolumeClaimRetentionPolicy.whenDeleted | string | `"Delete"` |  |
| postgresql.primary.persistentVolumeClaimRetentionPolicy.whenScaled | string | `"Delete"` |  |
| postgresql.primary.readinessProbe.enabled | bool | `false` |  |
| postgresql.primary.resources.limits.cpu | int | `3` |  |
| postgresql.primary.resources.limits.memory | string | `"1024Mi"` |  |
| postgresql.primary.resources.requests.cpu | int | `1` |  |
| postgresql.primary.resources.requests.memory | string | `"512Mi"` |  |
| postgresql.primary.startupProbe.enabled | bool | `false` |  |
| postgresql.tls.autoGenerated | bool | `true` |  |
| postgresql.tls.enabled | bool | `true` |  |
| postgresql.volumePermissions.enabled | bool | `true` |  |
| rollup-explorer-backend.enabled | bool | `false` |  |
| rollup-explorer-backend.ingress.main.annotations | object | `{}` |  |
| rollup-explorer-backend.ingress.main.enabled | bool | `true` |  |
| rollup-explorer-backend.ingress.main.hosts[0].host | string | `"rollup-explorer-backend.scrollsdk"` |  |
| rollup-explorer-backend.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| rollup-explorer-backend.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| rollup-explorer-backend.ingress.main.ingressClassName | string | `"nginx"` |  |
| rollup-explorer-backend.ingress.main.labels | object | `{}` |  |
| rollup-explorer-backend.ingress.main.primary | bool | `true` |  |
| rollup-node.enabled | bool | `false` |  |
| rpc-gateway.enabled | bool | `false` |  |
| rpc-gateway.ingress.main.enabled | bool | `true` |  |
| rpc-gateway.ingress.main.hosts[0].host | string | `"l2-rpc-gateway.scrollsdk"` |  |
| rpc-gateway.ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| rpc-gateway.ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| rpc-gateway.ingress.main.ingressClassName | string | `"nginx"` |  |
| scroll-common.enabled | bool | `true` |  |
| scroll-monitor.enabled | bool | `true` |  |
| scroll-monitor.grafana.enabled | bool | `true` |  |
| scroll-monitor.grafana.ingress.enabled | bool | `true` |  |
| scroll-monitor.grafana.ingress.hosts[0] | string | `"grafana.scrollsdk"` |  |
| scroll-monitor.grafana.ingress.ingressClassName | string | `"nginx"` |  |
| scroll-monitor.kube-prometheus-stack.alertmanager.enabled | bool | `false` |  |
| scroll-monitor.kube-prometheus-stack.enabled | bool | `true` |  |
| scroll-monitor.loki.enabled | bool | `false` |  |
| scroll-monitor.promtail.enabled | bool | `true` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
