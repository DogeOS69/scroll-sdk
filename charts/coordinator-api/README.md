# coordinator-api

![Version: 0.1.5](https://img.shields.io/badge/Version-0.1.5-informational?style=flat-square) ![AppVersion: v0.1.0](https://img.shields.io/badge/AppVersion-v0.1.0-informational?style=flat-square)

coordinator-api helm charts

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| scroll-tech | <sebastien@scroll.io> |  |

## Requirements

Kubernetes: `>=1.22.0-0`

| Repository | Name | Version |
|------------|------|---------|
| oci://ghcr.io/dogeos69/scroll-sdk/helm | external-secrets-lib | 0.0.4 |
| oci://ghcr.io/scroll-tech/scroll-sdk/helm | common | 1.5.1 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| command[0] | string | `"bash"` |  |
| command[1] | string | `"-c"` |  |
| command[2] | string | `"coordinator_api --config /coordinator/conf/coordinator-config.json --genesis /app/genesis/genesis.json --http --http.addr '0.0.0.0' --http.port ${HTTP_PORT} --metrics --metrics.addr '0.0.0.0' --metrics.port ${METRICS_PORT} --log.debug"` |  |
| configMaps.download-params.data."download-params.sh" | string | `"#!/bin/bash\n\nset -ex\n\napt update\napt install wget libdigest-sha-perl -y\nOPENVM_URL=\"https://circuit-release.s3.us-west-2.amazonaws.com/scroll-zkvm/releases\"\nOPENVM_FILES=(\"verifier.bin\" \"root-verifier-vm-config\" \"root-verifier-committed-exe\" \"openVmVk.json\")\nOPENVM_VERSIONS=(\"0.4.3\" \"0.5.2\")\n\n# download files\ndownload_file_no_checksum() {\n  file=$1\n  url=$2\n  if [ ! -f $file ]; then\n    mkdir -p $(dirname $file)\n    echo \"Downloading $file...\"\n    wget --progress=dot:giga $url -O $file\n    echo \"Download completed $file\"\n  fi\n}\n\nmain(){\n  # download openvm-${VERSION} verifier\n  for v in \"${OPENVM_VERSIONS[@]}\";do\n    for f in \"${OPENVM_FILES[@]}\"; do\n      download_file_no_checksum \"/verifier/openvm-$v/$f\" \"$OPENVM_URL/$v/verifier/$f\"\n    done\n  done\n}\n\nmain\n"` |  |
| configMaps.download-params.enabled | bool | `true` |  |
| controller.replicas | int | `1` |  |
| controller.strategy | string | `"RollingUpdate"` |  |
| controller.type | string | `"statefulset"` |  |
| defaultProbes.custom | bool | `true` |  |
| defaultProbes.enabled | bool | `false` |  |
| defaultProbes.spec.httpGet.path | string | `"/"` |  |
| defaultProbes.spec.httpGet.port | int | `8090` |  |
| envFrom[0].configMapRef.name | string | `"coordinator-api-env"` |  |
| env[0].name | string | `"HTTP_PORT"` |  |
| env[0].value | int | `8080` |  |
| env[1].name | string | `"METRICS_PORT"` |  |
| env[1].value | int | `8090` |  |
| env[2].name | string | `"RUST_LOG"` |  |
| env[2].value | string | `"info"` |  |
| env[3].name | string | `"SCROLL_PROVER_ASSETS_DIR"` |  |
| env[3].value | string | `"/data/assets/"` |  |
| global.fullnameOverride | string | `"coordinator-api"` |  |
| global.nameOverride | string | `"coordinator-api"` |  |
| image.pullPolicy | string | `"IfNotPresent"` |  |
| image.repository | string | `"scrolltech/coordinator-api"` |  |
| image.tag | string | `"v4.7.9"` |  |
| ingress.main.annotations | object | `{}` |  |
| ingress.main.enabled | bool | `true` |  |
| ingress.main.hosts[0].host | string | `"coordinator-api.scrollsdk"` |  |
| ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| ingress.main.ingressClassName | string | `"nginx"` |  |
| ingress.main.labels | object | `{}` |  |
| ingress.main.primary | bool | `true` |  |
| initContainers.parameter-download.command[0] | string | `"sh"` |  |
| initContainers.parameter-download.command[1] | string | `"-c"` |  |
| initContainers.parameter-download.command[2] | string | `"/download-params.sh params"` |  |
| initContainers.parameter-download.image | string | `"ubuntu"` |  |
| initContainers.parameter-download.resources.limits.cpu | string | `"2"` |  |
| initContainers.parameter-download.resources.limits.memory | string | `"8Gi"` |  |
| initContainers.parameter-download.resources.requests.cpu | string | `"1"` |  |
| initContainers.parameter-download.resources.requests.memory | string | `"2Gi"` |  |
| initContainers.parameter-download.volumeMounts[0].mountPath | string | `"/verifier"` |  |
| initContainers.parameter-download.volumeMounts[0].name | string | `"verifier"` |  |
| initContainers.parameter-download.volumeMounts[1].mountPath | string | `"/download-params.sh"` |  |
| initContainers.parameter-download.volumeMounts[1].name | string | `"download-params"` |  |
| initContainers.parameter-download.volumeMounts[1].subPath | string | `"download-params.sh"` |  |
| persistence.app_name.enabled | bool | `true` |  |
| persistence.app_name.mountPath | string | `"/coordinator/conf/"` |  |
| persistence.app_name.name | string | `"coordinator-api-config"` |  |
| persistence.app_name.type | string | `"configMap"` |  |
| persistence.download-params.defaultMode | string | `"0777"` |  |
| persistence.download-params.enabled | bool | `true` |  |
| persistence.download-params.mountPath | string | `"/download-params.sh"` |  |
| persistence.download-params.name | string | `"coordinator-api-download-params"` |  |
| persistence.download-params.type | string | `"configMap"` |  |
| persistence.genesis.enabled | bool | `true` |  |
| persistence.genesis.mountPath | string | `"/app/genesis/"` |  |
| persistence.genesis.name | string | `"genesis-config"` |  |
| persistence.genesis.type | string | `"configMap"` |  |
| probes.liveness.<<.custom | bool | `true` |  |
| probes.liveness.<<.enabled | bool | `false` |  |
| probes.liveness.<<.spec.httpGet.path | string | `"/"` |  |
| probes.liveness.<<.spec.httpGet.port | int | `8090` |  |
| probes.readiness.<<.custom | bool | `true` |  |
| probes.readiness.<<.enabled | bool | `false` |  |
| probes.readiness.<<.spec.httpGet.path | string | `"/"` |  |
| probes.readiness.<<.spec.httpGet.port | int | `8090` |  |
| probes.startup.<<.custom | bool | `true` |  |
| probes.startup.<<.enabled | bool | `false` |  |
| probes.startup.<<.spec.httpGet.path | string | `"/"` |  |
| probes.startup.<<.spec.httpGet.port | int | `8090` |  |
| resources.limits.cpu | string | `"200m"` |  |
| resources.limits.memory | string | `"24Gi"` |  |
| resources.requests.cpu | string | `"50m"` |  |
| resources.requests.memory | string | `"20Gi"` |  |
| scrollConfig | string | `"{}\n"` |  |
| service.main.enabled | bool | `true` |  |
| service.main.ports.http.enabled | bool | `true` |  |
| service.main.ports.http.port | int | `80` |  |
| service.main.ports.http.targetPort | int | `8080` |  |
| service.main.ports.metrics.enabled | bool | `true` |  |
| service.main.ports.metrics.port | int | `8090` |  |
| service.main.ports.metrics.targetPort | int | `8090` |  |
| serviceMonitor.main.enabled | bool | `true` |  |
| serviceMonitor.main.endpoints[0].interval | string | `"1m"` |  |
| serviceMonitor.main.endpoints[0].port | string | `"metrics"` |  |
| serviceMonitor.main.endpoints[0].scrapeTimeout | string | `"10s"` |  |
| serviceMonitor.main.labels.release | string | `"scroll-sdk"` |  |
| serviceMonitor.main.serviceName | string | `"{{ include \"scroll.common.lib.chart.names.fullname\" $ }}"` |  |
| volumeClaimTemplates[0].accessMode | string | `"ReadWriteOnce"` |  |
| volumeClaimTemplates[0].mountPath | string | `"/verifier"` |  |
| volumeClaimTemplates[0].name | string | `"verifier"` |  |
| volumeClaimTemplates[0].size | string | `"100Gi"` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
