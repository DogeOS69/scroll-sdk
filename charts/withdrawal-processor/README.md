# withdrawal-processor

![Version: 0.1.17](https://img.shields.io/badge/Version-0.1.17-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

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

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| env[0].name | string | `"DOGEOS_WITHDRAWAL_NETWORK_STR"` |  |
| env[0].value | string | `"testnet"` |  |
| env[10].name | string | `"DOGEOS_WITHDRAWAL_DEBUG_SKIP_BROADCAST"` |  |
| env[10].value | string | `"false"` |  |
| env[11].name | string | `"DOGEOS_WITHDRAWAL_DOGECOIN_INDEXER__START_HEIGHT"` |  |
| env[11].value | string | `"4000000"` |  |
| env[12].name | string | `"DOGEOS_WITHDRAWAL_DOGECOIN_INDEXER__CONFIRMATIONS"` |  |
| env[12].value | string | `"1"` |  |
| env[13].name | string | `"DOGEOS_WITHDRAWAL_DOGECOIN_INDEXER__POLL_INTERVAL_MS"` |  |
| env[13].value | string | `"10000"` |  |
| env[14].name | string | `"DOGEOS_WITHDRAWAL_DOGEOS_INDEXER__RPC_URL"` |  |
| env[14].value | string | `"https://sepolia-rpc.scroll.io/"` |  |
| env[15].name | string | `"DOGEOS_WITHDRAWAL_DOGEOS_INDEXER__START_BLOCK"` |  |
| env[15].value | string | `"9416118"` |  |
| env[16].name | string | `"DOGEOS_WITHDRAWAL_DOGEOS_INDEXER__CONFIRMATIONS"` |  |
| env[16].value | string | `"10"` |  |
| env[17].name | string | `"DOGEOS_WITHDRAWAL_DOGEOS_INDEXER__POLL_INTERVAL_MS"` |  |
| env[17].value | string | `"5000"` |  |
| env[18].name | string | `"DOGEOS_WITHDRAWAL_DOGEOS_INDEXER__MESSENGER_ADDRESS"` |  |
| env[18].value | string | `"0xBa50f5340FB9F3Bd074bD638c9BE13eCB36E603d"` |  |
| env[19].name | string | `"DOGEOS_WITHDRAWAL_DOGEOS_INDEXER__MESSAGE_QUEUE_ADDRESS"` |  |
| env[19].value | string | `"0x5300000000000000000000000000000000000000"` |  |
| env[1].name | string | `"DOGEOS_WITHDRAWAL_DATABASE_URL"` |  |
| env[1].value | string | `"sqlite:///app/data/withdrawal_processor.db"` |  |
| env[20].name | string | `"DOGEOS_WITHDRAWAL_DOGEOS_INDEXER__LOG_QUERY_BATCH_SIZE"` |  |
| env[20].value | string | `"10000"` |  |
| env[21].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__DA_RPC_URL"` |  |
| env[21].value | string | `"http://celestia-testnet-mocha:26658"` |  |
| env[22].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__DA_NAMESPACE"` |  |
| env[22].value | string | `"D06305735700"` |  |
| env[23].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__START_BLOCK"` |  |
| env[23].value | string | `"5965461"` |  |
| env[24].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__CONFIRMATIONS"` |  |
| env[24].value | string | `"3"` |  |
| env[25].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__POLL_INTERVAL_MS"` |  |
| env[25].value | string | `"15000"` |  |
| env[26].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__SIGNER_ADDRESS"` |  |
| env[26].value | string | `"celestia1n4m4rxllc55kaf2t7hzl9vuuzjtszakww8xcvn"` |  |
| env[27].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__GENESIS_BLOB_COMMITMENT"` |  |
| env[27].value | string | `"XWcGNcRS7gHrv3sfEqQY6oJpm8V1PT7vH2RfwYHv830="` |  |
| env[28].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__FETCH_AND_DECODE_BLOBS"` |  |
| env[28].value | string | `"true"` |  |
| env[29].name | string | `"DOGEOS_WITHDRAWAL_CELESTIA_INDEXER__BLOB_GET_ALL_FALLBACK_URL"` |  |
| env[29].value | string | `""` |  |
| env[2].name | string | `"DOGEOS_WITHDRAWAL_API_PORT"` |  |
| env[2].value | string | `"3000"` |  |
| env[30].name | string | `"DOGEOS_WITHDRAWAL_UTXO_MANAGER__HIGH_THRESH_SATS"` |  |
| env[30].value | string | `"1000000000"` |  |
| env[31].name | string | `"DOGEOS_WITHDRAWAL_UTXO_MANAGER__BRIDGE_MIN_CONFIRMATIONS"` |  |
| env[31].value | string | `"10"` |  |
| env[32].name | string | `"DOGEOS_WITHDRAWAL_GENESIS_SEQUENCER_VOUT"` |  |
| env[32].value | string | `"0"` |  |
| env[33].name | string | `"DOGEOS_WITHDRAWAL_GENESIS_SEQUENCER_TXID"` |  |
| env[33].value | string | `"0x0000000000000000000000000000000000000000000000000000000000000000"` |  |
| env[3].name | string | `"DOGEOS_WITHDRAWAL_DOGECOIN_RPC_URL"` |  |
| env[3].value | string | `"https://testnet.doge.xyz"` |  |
| env[4].name | string | `"DOGEOS_WITHDRAWAL_TSO_URL"` |  |
| env[4].value | string | `"http://127.0.0.1:3001"` |  |
| env[5].name | string | `"DOGEOS_WITHDRAWAL_BRIDGE_ADDRESS"` |  |
| env[5].value | string | `"2NFNonsBJC8ba8z9Xg7uZFboJ5mTrTzZMFQ"` |  |
| env[6].name | string | `"DOGEOS_WITHDRAWAL_BRIDGE_SCRIPT_HEX"` |  |
| env[6].value | string | `"63512102e30c3b1c8f3eb848ecf30b5cb6ad4e79ed597f466616e00100d16d098e4f565651af522102a47661bca3a89f9ac7ee2a741ac8634ff2199ffb33699455d10f7bf8c10750bd210209d3f1f5ca8576897d1590d4393c74c7cdfa06c6c2870dfc2aa503d5e8287bbf210260441f93ba89660e3ea7048e8b18d9681e8e46ed5c4656121b65ff81388f4a0a53af52210322bd1125af285ee62b405a2b4a8ad77ae4240b6319ee12c4f3e2365717f6f0702102dca26da747dc83a4d55012a48dc08d28affe12584bc940d0adeed634c527f6c22102160ecf32a1928a761d39c29d35534ff272221b58e9af23b29d28ec2107d89bbe53ae6702100eb175522102464328dc87e7424975d3042fd5469f6623dc1d3b46fe14f9caeb8d67481c0383210389379affeb45dff7a77ccd9afc98e9d359921c5803f5344f6fbc8c248b619a8d21039abe97bd966b9195f6034d309c395cd76836bd896524c69e85b63b81cd28a37d53ae68"` |  |
| env[7].name | string | `"DOGEOS_WITHDRAWAL_MAX_WITHDRAWAL_OUTPUTS_PER_TX"` |  |
| env[7].value | string | `"85"` |  |
| env[8].name | string | `"DOGEOS_WITHDRAWAL_FEE_RATE_SAT_PER_KVB"` |  |
| env[8].value | string | `"1000000"` |  |
| env[9].name | string | `"DOGEOS_WITHDRAWAL_COORDINATOR_POLL_INTERVAL_SECS"` |  |
| env[9].value | string | `"10"` |  |
| global.fullnameOverride | string | `"withdrawal-processor"` |  |
| global.nameOverride | string | `"withdrawal-processor"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"dogeos69/withdrawal-processor"` |  |
| image.tag | string | `"110325-00"` |  |
| persistence.data.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.data.annotations.placeholder | string | `"annotation"` |  |
| persistence.data.enabled | bool | `false` |  |
| persistence.data.mountPath | string | `"/app/data"` |  |
| persistence.data.name | string | `"withdrawal-processor-data-pvc"` |  |
| persistence.data.retain | bool | `true` |  |
| persistence.data.size | string | `"1Gi"` |  |
| persistence.data.type | string | `"pvc"` |  |
| persistence.tso-signers-config.enabled | bool | `true` |  |
| persistence.tso-signers-config.mountPath | string | `"/app/config/signers.toml"` |  |
| persistence.tso-signers-config.name | string | `"{{ include \"withdrawal-processor.fullname\" . }}-tso-signers"` |  |
| persistence.tso-signers-config.readOnly | bool | `true` |  |
| persistence.tso-signers-config.subPath | string | `"signers.toml"` |  |
| persistence.tso-signers-config.type | string | `"configMap"` |  |
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
| service.main.annotations.placeholder | string | `"annotation"` |  |
| service.main.enabled | bool | `true` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `3000` |  |
| serviceMonitor.main.enabled | bool | `false` |  |
| tsoSigners | list | `[]` |  |

