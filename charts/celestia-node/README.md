# celestia-node

![Version: 0.1.9](https://img.shields.io/badge/Version-0.1.9-informational?style=flat-square) ![AppVersion: v0.27.3-mocha](https://img.shields.io/badge/AppVersion-v0.27.3--mocha-informational?style=flat-square)

A Helm chart for deploying Celestia light node on Kubernetes

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| Celestia | <support@celestia.org> |  |

## Requirements

| Repository | Name | Version |
|------------|------|---------|
| oci://ghcr.io/dogeos69/scroll-sdk/helm | external-secrets-lib | 0.0.4 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| configToml | string | `"[Node]\nStartupTimeout = \"20s\"\nShutdownTimeout = \"20s\"\n\n[Core]\nIP = \"\"\nPort = \"9090\"\nTLSEnabled = false\nXTokenPath = \"\"\nAdditionalCoreEndpoints = []\n\n[State]\nDefaultKeyName = \"my_celes_key\"\nDefaultBackendName = \"test\"\nEstimatorAddress = \"\"\nEnableEstimatorTLS = false\n\n[P2P]\nListenAddresses = [\n  \"/ip4/0.0.0.0/udp/2121/quic-v1/webtransport\",\n  \"/ip6/::/udp/2121/quic-v1/webtransport\",\n  \"/ip4/0.0.0.0/udp/2121/quic-v1\",\n  \"/ip6/::/udp/2121/quic-v1\",\n  \"/ip4/0.0.0.0/udp/2121/webrtc-direct\",\n  \"/ip6/::/udp/2121/webrtc-direct\",\n  \"/ip4/0.0.0.0/tcp/2121\",\n  \"/ip6/::/tcp/2121\"\n]\nAnnounceAddresses = []\nNoAnnounceAddresses = [\n  \"/ip4/127.0.0.1/udp/2121/quic-v1/webtransport\",\n  \"/ip4/0.0.0.0/udp/2121/quic-v1/webtransport\",\n  \"/ip6/::/udp/2121/quic-v1/webtransport\",\n  \"/ip4/0.0.0.0/udp/2121/quic-v1\",\n  \"/ip4/127.0.0.1/udp/2121/quic-v1\",\n  \"/ip6/::/udp/2121/quic-v1\",\n  \"/ip4/0.0.0.0/udp/2121/webrtc-direct\",\n  \"/ip4/127.0.0.1/udp/2121/webrtc-direct\",\n  \"/ip6/::/udp/2121/webrtc-direct\",\n  \"/ip4/0.0.0.0/tcp/2121\",\n  \"/ip4/127.0.0.1/tcp/2121\",\n  \"/ip6/::/tcp/2121\"\n]\nMutualPeers = []\nPeerExchange = false\n\n[P2P.ConnManager]\nLow = 50\nHigh = 100\nGracePeriod = \"1m0s\"\n\n[RPC]\nAddress = \"localhost\"\nPort = \"26658\"\nSkipAuth = false\n\n[RPC.CORS]\nEnabled = false\nAllowedOrigins = []\nAllowedHeaders = []\nAllowedMethods = []\n\n[Share]\nBlockStoreCacheSize = 128\nUseShareExchange = true\nUseBitswap = true\n\n[Share.EDSStoreParams]\nRecentBlocksCacheSize = 10\n\n[Share.ShrexClient]\nReadTimeout = \"2m0s\"\nWriteTimeout = \"5s\"\n\n[Share.ShrexServer]\nReadTimeout = \"5s\"\nWriteTimeout = \"1m0s\"\nHandleRequestTimeout = \"1m0s\"\nConcurrencyLimit = 10\n\n[Share.PeerManagerParams]\nPoolValidationTimeout = \"2m0s\"\nPeerCooldown = \"3s\"\nGcInterval = \"30s\"\nEnableBlackListing = false\n\n[Share.LightAvailability]\nSampleAmount = 16\n\n[Share.Discovery]\nPeersLimit = 5\nAdvertiseInterval = \"1h0m0s\"\n\n[Header]\nTrustedPeers = []\n\n[Header.Store]\nStoreCacheSize = 512\nIndexCacheSize = 2048\nWriteBatchSize = 16\n\n[Header.Syncer]\nPruningWindow = \"169h0m0s\"\n# Set to a trusted hash to start syncing from a specific point. Leave empty to sync from genesis.\nSyncFromHash = \"\"\n# Set to a trusted height to start syncing from. Use 0 to disable.\nSyncFromHeight = 0\n\n[Header.Server]\nWriteDeadline = \"8s\"\nReadDeadline = \"1m0s\"\nRequestTimeout = \"10s\"\n\n[Header.Client]\nMaxHeadersPerRangeRequest = 64\nRequestTimeout = \"8s\"\n\n[DASer]\nSamplingRange = 100\nConcurrencyLimit = 16\nBackgroundStoreInterval = \"10m0s\"\nSampleTimeout = \"1m36s\"\nEnabled = true\n"` |  |
| core.grpc_port | int | `9090` |  |
| core.rpc_url | string | `"rpc-mocha.pops.one"` |  |
| image.pullPolicy | string | `"IfNotPresent"` |  |
| image.repository | string | `"ghcr.io/celestiaorg/celestia-node"` |  |
| image.tag | string | `"v0.27.3-mocha"` |  |
| ingress.annotations."cert-manager.io/cluster-issuer" | string | `"letsencrypt-prod"` |  |
| ingress.annotations."nginx.ingress.kubernetes.io/ssl-redirect" | string | `"true"` |  |
| ingress.className | string | `"nginx"` |  |
| ingress.enabled | bool | `true` |  |
| ingress.hosts[0].host | string | `"celestia.testnet.dogeos.com"` |  |
| ingress.hosts[0].paths[0].path | string | `"/"` |  |
| ingress.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| ingress.tls[0].hosts[0] | string | `"celestia.testnet.dogeos.com"` |  |
| ingress.tls[0].secretName | string | `"celestia-tls"` |  |
| mnemonic | string | `""` |  |
| network | string | `"mocha"` |  |
| node_type | string | `"light"` |  |
| resources.limits.cpu | string | `"1000m"` |  |
| resources.limits.memory | string | `"4Gi"` |  |
| resources.requests.cpu | string | `"500m"` |  |
| resources.requests.memory | string | `"2Gi"` |  |
| rpc.auth.skipAuth | bool | `true` |  |
| service.ports.p2p-tcp.enabled | bool | `true` |  |
| service.ports.p2p-tcp.port | int | `2121` |  |
| service.ports.p2p-tcp.protocol | string | `"TCP"` |  |
| service.ports.p2p-tcp.targetPort | int | `2121` |  |
| service.ports.p2p-udp.enabled | bool | `true` |  |
| service.ports.p2p-udp.port | int | `2121` |  |
| service.ports.p2p-udp.protocol | string | `"UDP"` |  |
| service.ports.p2p-udp.targetPort | int | `2121` |  |
| service.ports.rpc.enabled | bool | `true` |  |
| service.ports.rpc.port | int | `26658` |  |
| service.ports.rpc.protocol | string | `"TCP"` |  |
| service.ports.rpc.targetPort | int | `26658` |  |
| service.type | string | `"ClusterIP"` |  |
| storage.retainPvcOnUninstall | bool | `true` |  |
| storage.size | string | `"200Gi"` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
