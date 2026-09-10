# scroll-monitor configuration generation contract

Use [values/scroll-monitor-production.yaml](values/scroll-monitor-production.yaml)
as the operator-facing input/output example for the configuration generator.
The matching chart production profile exposes the same monitoring fields.
Replace `<TODO>` with deployment facts; do not copy testnet addresses, provider
URLs or chain IDs from an investigation report into generic generated values.
The Sepolia example explicitly uses the user-selected
`https://ethereum-sepolia-rpc.publicnode.com`, matching
`config.toml.example`'s `ethereumDa.submitterRpcUrl`. Other deployments must
generate their own network's URL and chain ID.

## Account monitoring inputs

The existing `scrollsdk setup prep-charts` balance reconciler consumes the
canonical signer configuration, `config.toml` and doge-config. The mapping is:

| Output field | User/configuration input |
| --- | --- |
| `balanceMonitoring.ethereum.feeOracle.address` | Canonical public address of the managed `l2GasOracleSender` signer. For KMS, use its validated expected address. |
| `balanceMonitoring.ethereum.feeOracle.rpcUrl` | `config.toml` `general.L2_RPC_ENDPOINT`, reachable from the exporter Pod. |
| `balanceMonitoring.ethereum.feeOracle.expectedChainId` | `config.toml` `general.CHAIN_ID_L2`, serialized as a string. |
| `balanceMonitoring.ethereum.ethDaSubmitter.address` | Canonical public address of the managed `l1CommitSender` signer. For KMS, use its validated expected address. |
| `balanceMonitoring.ethereum.ethDaSubmitter.rpcUrl` | doge-config `ethereumDa.submitterRpcUrl`. It must allow `eth_chainId` and `eth_getBalance` from the deployment network. |
| `balanceMonitoring.ethereum.ethDaSubmitter.expectedChainId` | doge-config `ethereumDa.chainId`, serialized as a string. |
| `balanceMonitoring.ethereum.*.minimumEth` | Operator funding thresholds; preserve on regeneration. |
| `balanceMonitoring.feeWallet.minimumDoge` / `jobRegex` | Operator funding threshold and the generated withdrawal-processor Prometheus job selection. |
| `balanceMonitoring.exporter.envFromSecret` | User-supplied existing Secret name, when RPC URLs require credentials. |

Do not assume that a publicly reachable RPC permits automated balance reads.
Verify the two read methods and chain ID using the deployment's network and
authentication. An HTTP 403 is an access failure; it does not imply zero funds.
No private keys or signing permissions are needed by the exporter.
The bundled exporter identifies itself with
`User-Agent: scroll-monitor-account-balances/0.1`; both the previous Sentio
endpoint and PublicNode rejected the generic Python User-Agent during the
read-only testnet investigation. Deploy the exporter fix with the URL change.

With `exporter.envFromSecret` set, an **explicit empty** `rpcUrl: ""` delegates
that account's URL to the Secret. The existing generator preserves this choice;
it refreshes generated addresses and chain IDs and preserves operator thresholds.
Nonempty values override the Secret, including an unreplaced `<TODO>`.

For example, the user supplies the Secret name and creates its contents through
their secret-management workflow; the generated values contain only the reference:

```yaml
balanceMonitoring:
  ethereum:
    feeOracle:
      address: "<TODO>" # Generated from l2GasOracleSender.
      rpcUrl: "" # Secret-owned.
      expectedChainId: "<TODO>" # Generated L2 chain ID.
    ethDaSubmitter:
      address: "<TODO>" # Generated from l1CommitSender.
      rpcUrl: "" # Secret-owned.
      expectedChainId: "<TODO>" # Generated Ethereum chain ID.
  exporter:
    envFromSecret: "<TODO>" # Existing Secret name, supplied by the user.
```

The Secret keys are `SCROLL_BALANCE_FEE_ORACLE_RPC_URL` and
`SCROLL_BALANCE_ETH_DA_SUBMITTER_RPC_URL`. Supply only the keys delegated to it.
Secret values must not be committed to the example. The example also makes
`intervalSeconds: 60` and `rpcTimeoutSeconds: 10` explicit; valid chart ranges
are 1–120 and 1–15 seconds respectively.

## Metrics discovery inputs

`additionalServiceMonitors.tso` is a supplemental monitor owned by scroll-monitor.
The generator/operator must select exactly one owner for TSO scraping:

- When generated TSO values enable their own ServiceMonitor, leave the
  supplemental entry disabled. This is the current TSO production example.
- For a legacy TSO deployment without its own monitor, set
  `additionalServiceMonitors.tso.enabled: true` in scroll-monitor values.
  Populate `selector.matchLabels` from the actual generated Service labels and
  `endpoints[].port` from the **named Service port**, normally `http`.
  The normal path is `/metrics`, with a 30-second interval and 10-second timeout.
- Keep the entry disabled if TSO is not part of the deployment. Supplemental
  monitors discover Services only in the scroll-monitor release namespace.

The existing balance reconciler does not infer this new ServiceMonitor ownership
decision. The explicit example supplies the field contract for the generator
and operator to retain/populate; no separate CLI repository was changed here.

## Dogecoin indexer stall monitoring

The example exposes `dogecoinIndexerAlerts.jobRegex`, defaulting to
`l1-interface|withdrawal-processor`. The configuration generator must match the
actual Prometheus job names. No confirmation depth, Dogecoin node address or
RPC URL is required for this rule: it uses each service's exported
`indexer_dogecoin_last_synced_block` directly.

The rule alerts when the value remains unchanged for two minutes, independently
per namespace, job and instance. It requires current and historical samples;
missing telemetry is not treated as an unchanged height. There is no additional
pending period beyond the two-minute observation window.

Do not generate `dogecoinIndexerAlerts.confirmationsByJob` or
`dogecoinIndexerAlerts.maxExcessLagBlocks` for new installations. When upgrading
an installation with customized legacy values, retain those values for the
upgrade so the seeder can exactly recognize its old saved Grafana query. They
are used only for migration. The old default ten-minute pending period is
removed if unchanged; operator-edited pending periods remain under UI control.

An absent `up` series can mean no ServiceMonitor was selected. It is different
from `up == 0`, which means a discovered endpoint failed its scrape. Check both
target discovery and the native metric before relying on an alert.

If fee-oracle is intentionally not deployed, review and pause its Grafana rules,
including funding rules for any account that is no longer used. Missing metrics
produce warning rules rather than false claims of zero signers or stale oracle
values. The chart does not silently turn off monitoring when a service disappears.
Existing Grafana rules retain user edits and pause choices on upgrades, apart
from exact migrations of known shipped query defects.
