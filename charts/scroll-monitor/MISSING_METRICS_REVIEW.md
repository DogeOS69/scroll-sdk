# Testnet missing-metric alert investigation

Read-only observation on 2026-09-10, Grafana/Prometheus snapshot around 13:58 UTC, of
`arn:aws:eks:us-west-2:074120976575:cluster/dogeos-testnet-cluster`, namespace
`default`. Kubernetes GETs, local port forwards, Grafana GET APIs, Prometheus
queries, a direct GET of TSO `/metrics`, and read-only JSON-RPC requests from
the balance exporter container were used. RPC checks ran Python in memory
without writing files or changing the exporter process. No cluster resources,
Grafana rules, notifications, or running service configuration were changed.

## Findings

| Alert | Observed evidence | Diagnosis |
| --- | --- | --- |
| `TSONoRegisteredSigners` | Prometheus has neither `tso_core_registered_signers_count` nor a TSO `up` series. No TSO ServiceMonitor exists. Direct TSO `/metrics` reports count **5**: Correctness 1, Attestation 3, Sequencer 1. | Missing scrape configuration, not zero signers. The query's `absent(...)` branch returns 1 and fires the critical business alert. |
| `FeeOracleStale` | No fee-oracle Pod, Service, ServiceMonitor, target, or `fee_oracle_*` metrics exist in the observed namespace. | No deployed source for the metric. The `absent(...)` branch cannot establish that a computed value is stale. Whether fee-oracle should be deployed is a deployment decision. |
| `AccountBalanceCollectionFailed` for eth-da-submitter | Exporter target is up. Collection success and last-success timestamp are both 0; collection status is `rpc_unavailable`. Configured RPC host is `sepolia.rpc.sentio.xyz`, expected chain 11155111. | Container-side reads confirmed HTTP 403 / Cloudflare 1010 for both `eth_chainId` and `eth_getBalance`. The generic Python-urllib User-Agent was rejected. An explicit exporter User-Agent allowed the chain-ID request. The old exporter collapses HTTP errors into `rpc_unavailable`. |
| `FeeOracleAccountBalanceLow` | Collection success is 1; the configured account's balance is 0 on chain 6281971. | A successful zero observation, not a missing value. Verify whether this configured account is still intended for the deployment, which has no fee-oracle workload. |
| `DogecoinIndexerLag` | Query returned l1-interface lag 59 and withdrawal-processor lag 119 at the snapshot. | False positive: live Dogecoin indexer confirmations are 60 for l1-interface and 120 for withdrawal-processor. Those raw gaps are consistent with the configured confirmation windows; raw tip distance alone is not excess processing lag. |

The Grafana rules had evaluation health `ok`; these incidents were ordinary
firing instances, not `DatasourceNoData` or `DatasourceError` alerts. The seeded
`noDataState: OK` setting cannot prevent an explicit `absent(...)` query from
returning a firing sample. Globally suppressing data-source errors would not
repair these missing sources.

All 38 discovered Prometheus targets were up at the snapshot. This does not
prove discovery is complete: TSO was entirely missing, as was proof-coordinator.
The internal Reth RPC ServiceMonitor also selected
`app.kubernetes.io/name=l2-reth`, while the live `l2-rpc` Service carried
`app.kubernetes.io/name=l2-reth-rpc`, so it had no target. The extended service
diagnostic catalog starts paused; a healthy list of discovered targets does not
validate coverage for paused rules. Those application deployment mismatches
remain outside this chart's automatic changes.

## Chart changes

- Split the two observed business/missing-metric conditions. The business rules
  still fire critical alerts for observed zero signers or a timestamp older than
  15 minutes. New warning rules identify the missing metrics after five minutes.
- Migrate exact old shipped Grafana queries and unchanged old descriptions;
  retain custom queries, annotations, pause state, routing and evaluation
  intervals. Native Prometheus uses the same expressions without migration keys.
- Add opt-in `additionalServiceMonitors`, including the verified TSO selector,
  named `http` port and `/metrics` path. No host IPs or credentials are embedded.
- Identify the balance RPC client as `scroll-monitor-account-balances/0.1` instead
  of the generic Python-urllib signature, and distinguish HTTP access denial,
  rate limiting and other HTTP errors in the
  balance exporter's bounded `reason` labels. A failed collection still omits
  balance samples and retains the last successful observation time.

## RPC source and example replacement

The old URL came from the active local testnet deployment's
`.data/doge-config.toml`, key `ethereumDa.submitterRpcUrl`. The CLI
`reconcileScrollMonitorBalances` copies it into
`balanceMonitoring.ethereum.ethDaSubmitter.rpcUrl`; Helm projects that into
`SCROLL_BALANCE_ETH_DA_SUBMITTER_RPC_URL`. It was not a scroll-monitor chart default.
The same source also feeds Ethereum DA RPC settings for other services.

The repository's Sepolia config example and both monitor production examples
use the user-selected `https://ethereum-sepolia-rpc.publicnode.com`.
Deployment directories are outside the authorized modification scope. No changes
from this task remain in `dogeos-aws-testnet-upgrade_to_o3o_4`; its source and
generated configuration require a separate deployment task to update.

Both Sentio and PublicNode returned Cloudflare HTTP 403 / 1010 to the generic
Python User-Agent in the exporter container; both returned Sepolia chain ID
`0xaa36a7` with the explicit exporter identity. Thus changing only the URL would
leave the deployed Python client broken. Cloudflare documents 1010 as a
[client signature access denial](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/).

The actual patched exporter `collect` function was evaluated in memory inside
the existing exporter container against PublicNode, with the existing configured
DA account and expected chain ID. Both reads succeeded: chain ID 11155111 and
balance 10762843241452679786 wei (about 10.7628 ETH). This did not replace or
restart the running exporter, whose persisted configuration remains unchanged.

## Confirmation-aware indexer lag

The live `l1-interface-env` ConfigMap has
`DOGEOS_L1_INTERFACE_DOGECOIN_INDEXER__CONFIRMATIONS=60`. The mounted
`WithdrawalProcessor.toml` has `[dogecoin_indexer].confirmations=120`; the inspected
Secret-backed environments had no confirmation overrides.

The reviewed dogeos-core source at `9ae3375fe`,
`crates/indexer_dogecoin/src/sync/rpc.rs`, computes its confirmed target from
`getblockchaininfo.blocks - confirmations`. The corrected alert uses
`dogecoin_chain_block_height`, not the header count, and computes:

```text
excess_lag = max(node_block_height - configured_confirmations - indexer_height, 0)
```

It alerts when excess lag is greater than `maxExcessLagBlocks` (default 12) for
10 minutes. Per-job depths are supplied by
`dogecoinIndexerAlerts.confirmationsByJob`; node and indexer series are matched
within the same namespace. Independent scrapes can make observed tip gaps differ
slightly from the configured depth, which explains why a 59/119 snapshot must not
be treated as proof of delay under a 60/120 policy. A future testnet configuration
must explicitly supply 60 and 120. Generic examples carry 6 and 6,
matching their service examples, with instructions to regenerate effective depths.
The known old Grafana query and unchanged descriptions have an exact migration.
A read-only evaluation of the corrected expression against live Prometheus
returned excess lag 0 for both jobs and no firing sample.

## Deployment follow-up (not executed)

1. Merge `additionalServiceMonitors.tso.enabled: true` into this deployment's
   scroll-monitor values, because no application-owned TSO monitor exists.
   After an authorized upgrade, verify `up{job="tso-service"} == 1` and an
   observed signer count. If the application chart later owns the monitor,
   disable the supplemental entry to avoid duplicate scraping.
2. Decide whether fee-oracle belongs in this deployment. Deploy and scrape it
   if required, or pause its Grafana rules if intentionally absent. Do not
   fabricate freshness data for an undeployed service. Review the independently
   configured fee-oracle funding account as well.
3. Supply a working Ethereum RPC via
   `balanceMonitoring.ethereum.ethDaSubmitter.rpcUrl`, or a Secret through
   `balanceMonitoring.exporter.envFromSecret` with that values field empty.
   Generate the deployment source and projections with the user-selected
   PublicNode endpoint. Keep expected chain ID 11155111 for Sepolia and deploy
   the updated exporter with its explicit User-Agent alongside the URL change.
4. Review application-owned ServiceMonitors for proof-coordinator and internal
   Reth RPC before relying on their diagnostics. Confirm the actual endpoint
   exists and service labels/ports match; those changes need their own deployment.

The local changes prepare a future deployment. They do not claim that live
alerts have cleared or that the provider or absent workload was changed in
the read-only cluster. The previously reported indexer gaps were confirmation
waiting, and the alert now measures only the excess backlog.
