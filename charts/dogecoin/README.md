# dogecoin

![Version: 0.1.13](https://img.shields.io/badge/Version-0.1.13-informational?style=flat-square)  ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square)  ![AppVersion: 1.14.9](https://img.shields.io/badge/AppVersion-1.14.9-informational?style=flat-square)
Deploy a Dogecoin FullNode in Kubernetes

## Single-node lifecycle and storage

This chart runs one Dogecoin process against one writable datadir PVC.
`replicaCount` must be `1`. Updates use `Recreate`: the Deployment waits for
old Pods to terminate before creating a new revision. This deliberately causes
an RPC interruption during updates. Manual Pod deletion is still managed by a
ReplicaSet; `Recreate` does not guarantee exclusion for every deletion/failure
scenario. Do not force-delete a Pod to bypass a stuck shutdown or volume detach.
`ReadWriteOnce` is node-scoped, not a single-Pod lock. Multiple nodes require
separate releases and separate PVCs; do not scale this Deployment or share its PVC.

PVC naming (`<release-name>-data`), `storage.existingClaim`, retention annotations
and operator-configured storage capacity are unchanged. No PVC migration is needed.

`preStop` asks `dogecoin-cli stop` to shut down gracefully, with a bounded RPC call.
The Pod has a configurable `terminationGracePeriodSeconds` (default `300` seconds)
to finish stopping and flush its data. This is a starting allowance, not a measured
mainnet guarantee: increase it if observed shutdowns need longer.

ConfigMap changes and chart-managed RPC Secret changes update the Pod checksum
and trigger a `Recreate` rollout. ExternalSecret **specification** changes also
trigger a rollout. Rotation of the remote secret value alone is not visible to
Helm: after the Kubernetes Secret has refreshed, use a controlled
`kubectl rollout restart deployment/<name>` to reload the copied runtime config.

## Adaptive health probes

All networks use the same fast-success, generous-timeout defaults. Network size
does not create an artificial startup delay. A healthy regtest node can become
ready within the first few probe cycles; a slow node gets the startup allowance.

| Probe | Check | Interval / timeout | Failure budget | Meaning |
| --- | --- | --- | --- | --- |
| startup | Local authenticated `getblockchaininfo` | 5s / 5s | 720 failures, about 1 hour | Wait for RPC warmup / loading to finish; liveness/readiness stay gated until success. |
| readiness | Local authenticated `getblockchaininfo` | 5s / 5s | 3 failures | Remove an unresponsive RPC endpoint from the Service without restarting it. |
| liveness | RPC TCP socket | 30s / 5s | 6 failures | Restart after sustained socket failure following successful startup. |

All `initialDelaySeconds` values default to `0`. Startup stops gating as soon as
its first check succeeds; the one-hour budget is **not a fixed waiting period**.
RPC credentials are read from `/tmp/dogecoin.conf`, not placed in probe arguments.
The loopback RPC port follows `service.rpcPort` for mainnet, testnet and regtest.

Ready means RPC is usable; it does **not** mean initial block download is complete
or that the chain tip is fresh. Sync status belongs in monitoring. Probes must
not restart a healthy node for normal IBD, missing peers or regtest's idle chain.
TCP liveness deliberately does not detect an RPC handler deadlock while its
socket remains open; readiness will remove it from service for investigation.

For slow disks, large chainstate loads or reindexing, increase the startup budget:

```yaml
terminationGracePeriodSeconds: 900
probes:
  startup:
    periodSeconds: 5
    failureThreshold: 2160  # About 3 hours; successful startup still finishes early.
```

All timing fields under `probes.startup`, `probes.readiness` and
`probes.liveness` are configurable; the chart owns probe commands and their
semantics. Budget for slow startup separately from Helm's `--wait --timeout`.

The default network is testnet. `values-mainnet.yaml` selects mainnet;
`values-regtest.yaml` selects regtest and its RPC/P2P ports without changing
storage settings. In SDK deployments, `prep-charts` selects the network and
ports from Dogecoin config and preserves operator storage/probe settings.

## Validation

```bash
helm lint --strict charts/dogecoin
python3 -m unittest discover -s charts/dogecoin/tests -p 'test_*.py' -v
# Optional local Docker smoke test; isolated regtest, no Kubernetes or host ports:
python3 charts/dogecoin/tests/smoke_regtest.py
```

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| Dogecoin | <support@dogecoin.org> |  |
## Requirements

| Repository | Name | Version |
|------------|------|---------|
| oci://ghcr.io/dogeos69/scroll-sdk/helm | external-secrets-lib | 0.0.4 |
## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` |  |
| dogecoinConf.disablewallet | int | `1` |  |
| dogecoinConf.listen | int | `0` |  |
| dogecoinConf.printtoconsole | int | `1` |  |
| dogecoinConf.regtest | int | `0` |  |
| dogecoinConf.rpcallowip[0] | string | `"192.168.0.0/16"` |  |
| dogecoinConf.rpcallowip[1] | string | `"10.100.0.0/16"` |  |
| dogecoinConf.rpcbind | string | `"0.0.0.0"` |  |
| dogecoinConf.rpcuser | string | `"user"` |  |
| dogecoinConf.server | int | `1` |  |
| dogecoinConf.testnet | int | `1` |  |
| dogecoinConf.zmqpubhashblock | string | `"tcp://0.0.0.0:28335"` |  |
| dogecoinConf.zmqpubhashtx | string | `"tcp://0.0.0.0:28334"` |  |
| dogecoinConf.zmqpubrawblock | string | `"tcp://0.0.0.0:28332"` |  |
| dogecoinConf.zmqpubrawtx | string | `"tcp://0.0.0.0:28333"` |  |
| externalSecrets | object | `{}` |  |
| fullnameOverride | string | `"dogecoin"` |  |
| image.pullPolicy | string | `"Always"` |  |
| image.repository | string | `"docker.io/dogeos69/dogecoin"` |  |
| ingress.annotations."nginx.ingress.kubernetes.io/backend-protocol" | string | `"TCP"` |  |
| ingress.className | string | `"nginx"` |  |
| ingress.enabled | bool | `false` |  |
| ingress.hosts[0].host | string | `"dogecoin.example.com"` |  |
| ingress.hosts[0].paths[0].path | string | `"/"` |  |
| ingress.hosts[0].paths[0].pathType | string | `"Prefix"` |  |
| ingress.tls[0].hosts[0] | string | `"dogecoin.example.com"` |  |
| ingress.tls[0].secretName | string | `"dogecoin-tls"` |  |
| nameOverride | string | `"dogecoin"` |  |
| nodeSelector | object | `{}` |  |
| probes.liveness.failureThreshold | int | `6` |  |
| probes.liveness.initialDelaySeconds | int | `0` |  |
| probes.liveness.periodSeconds | int | `30` |  |
| probes.liveness.timeoutSeconds | int | `5` |  |
| probes.readiness.failureThreshold | int | `3` |  |
| probes.readiness.initialDelaySeconds | int | `0` |  |
| probes.readiness.periodSeconds | int | `5` |  |
| probes.readiness.timeoutSeconds | int | `5` |  |
| probes.startup.failureThreshold | int | `720` |  |
| probes.startup.initialDelaySeconds | int | `0` |  |
| probes.startup.periodSeconds | int | `5` |  |
| probes.startup.timeoutSeconds | int | `5` |  |
| replicaCount | int | `1` |  |
| rpcPassword.secretKey | string | `"password"` |  |
| rpcPassword.value | string | `"password"` |  |
| service.port | int | `44556` |  |
| service.rpcPort | int | `44555` |  |
| service.type | string | `"ClusterIP"` |  |
| service.zmqHashBlockPort | int | `28335` |  |
| service.zmqHashTxPort | int | `28334` |  |
| service.zmqRawBlockPort | int | `28332` |  |
| service.zmqRawTxPort | int | `28333` |  |
| storage.existingClaim | string | `""` |  |
| storage.retainPvcOnUninstall | bool | `true` |  |
| storage.size | string | `"50Gi"` |  |
| storage.storageClassName | string | `""` |  |
| terminationGracePeriodSeconds | int | `300` |  |
| tolerations | list | `[]` |  |
