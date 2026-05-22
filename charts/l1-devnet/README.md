# l1-devnet

![Version: 0.1.5-dogeos](https://img.shields.io/badge/Version-0.1.5--dogeos-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: latest](https://img.shields.io/badge/AppVersion-latest-informational?style=flat-square)

Private Ethereum PoS devnet with JSON-RPC + Beacon API

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| scroll-tech | <sebastien@scroll.io> |  |

## Requirements

Kubernetes: `>=1.22.0-0`

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| fullnameOverride | string | `""` |  |
| genesis.storage | string | `"2Gi"` |  |
| geth.resources.limits.cpu | string | `"2"` |  |
| geth.resources.limits.memory | string | `"4Gi"` |  |
| geth.resources.requests.cpu | string | `"500m"` |  |
| geth.resources.requests.memory | string | `"1Gi"` |  |
| geth.storage | string | `"20Gi"` |  |
| geth.verbosity | int | `3` |  |
| global.fullnameOverride | string | `"l1-devnet"` |  |
| global.nameOverride | string | `"l1-devnet"` |  |
| images.genesisGenerator.repository | string | `"ethpandaops/ethereum-genesis-generator"` |  |
| images.genesisGenerator.tag | string | `"3.4.1"` |  |
| images.geth.repository | string | `"ethereum/client-go"` |  |
| images.geth.tag | string | `"v1.14.13"` |  |
| images.lighthouse.repository | string | `"sigp/lighthouse"` |  |
| images.lighthouse.tag | string | `"latest"` |  |
| ingress.main.annotations | object | `{}` |  |
| ingress.main.enabled | bool | `true` |  |
| ingress.main.hosts[0].host | string | `"l1-devnet.scrollsdk"` |  |
| ingress.main.hosts[0].paths[0].path | string | `"/"` |  |
| ingress.main.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| ingress.main.ingressClassName | string | `"nginx"` |  |
| ingress.main.labels | object | `{}` |  |
| ingress.main.primary | bool | `true` |  |
| jwtSecret | string | `"0xd4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3"` |  |
| lighthouse.debugLevel | string | `"info"` |  |
| lighthouse.resources.limits.cpu | string | `"2"` |  |
| lighthouse.resources.limits.memory | string | `"4Gi"` |  |
| lighthouse.resources.requests.cpu | string | `"500m"` |  |
| lighthouse.resources.requests.memory | string | `"1Gi"` |  |
| lighthouse.storage | string | `"20Gi"` |  |
| mnemonic | string | `"giant issue aisle success illegal bike spike question tent bar rely arctic volcano long crawl hungry vocal artwork sniff fantasy very lucky have athlete"` |  |
| nameOverride | string | `""` |  |
| network.chainId | int | `32382` |  |
| network.churnLimitQuotient | int | `65536` |  |
| network.custodyRequirement | int | `4` |  |
| network.dataColumnSidecarSubnetCount | int | `128` |  |
| network.depositContractAddress | string | `"0x4242424242424242424242424242424242424242"` |  |
| network.eip7594ForkEpoch | int | `999999` |  |
| network.ejectionBalance | string | `"16000000000"` |  |
| network.electraForkEpoch | int | `999999` |  |
| network.eth1FollowDistance | int | `16` |  |
| network.forkVersions.altair | string | `"0x20000038"` |  |
| network.forkVersions.bellatrix | string | `"0x30000038"` |  |
| network.forkVersions.capella | string | `"0x40000038"` |  |
| network.forkVersions.deneb | string | `"0x50000038"` |  |
| network.forkVersions.eip7594 | string | `"0x70000038"` |  |
| network.forkVersions.electra | string | `"0x60000038"` |  |
| network.forkVersions.fulu | string | `"0x70000038"` |  |
| network.forkVersions.genesis | string | `"0x10000038"` |  |
| network.fuluForkEpoch | int | `999999` |  |
| network.genesisDelay | string | `"10"` |  |
| network.genesisGasLimit | string | `"25000000"` |  |
| network.genesisTimestamp | string | `""` |  |
| network.maxBlobsPerBlock | int | `6` |  |
| network.maxPerEpochActivationChurnLimit | int | `8` |  |
| network.minValidatorWithdrawabilityDelay | int | `2` |  |
| network.networkId | int | `32382` |  |
| network.samplesPerSlot | int | `8` |  |
| network.secondsPerSlot | int | `4` |  |
| network.shardCommitteePeriod | int | `2` |  |
| prefundedAddress | string | `"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"` |  |
| prefundedBalanceEth | string | `"10000"` |  |
| prefundedPrivateKey | string | `"0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"` |  |
| service.main.enabled | bool | `true` |  |
| service.main.type | string | `"ClusterIP"` |  |
| storageClass | string | `"local-path"` |  |
| validator.debugLevel | string | `"info"` |  |
| validator.resources.limits.cpu | string | `"1"` |  |
| validator.resources.limits.memory | string | `"2Gi"` |  |
| validator.resources.requests.cpu | string | `"250m"` |  |
| validator.resources.requests.memory | string | `"512Mi"` |  |
| validatorCount | int | `64` |  |

