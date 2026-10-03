# Status-page defaults from deployment configuration

The CLI reads this network's selected deployment files. It does not copy a
Devnet hostname into a shared chart default or infer an environment from a URL.
Configuration readiness is separate from a successful live observation.

## Inputs that can be derived

| Input | Source | Default behavior |
| --- | --- | --- |
| HTTP RPC / enabled WebSocket | `sources.publicRpc` ingress | Use the selected deployment's actual hosts and external scheme. |
| Bridge Portal | `sources.frontends` ingress | Append the configured `bridgePath`, normally `/bridge`. |
| Bridge API | `sources.frontendsConfig` → `scrollConfig` → `REACT_APP_BRIDGE_API_URI` | `bridgeChecks: auto` checks `/txs` with a fixed zero-address read-only query; require `results` array and numeric `total`. Empty history is valid. |
| Sequencing mode | `sources.sequencer` → `reth.sequencer.allowEmptyBlocks` | `sequencingMode: auto` selects continuous/on-demand for an enabled sequencer; missing evidence remains unconfigured. |
| Expected block interval | Selected sequencer `blockTimeMs` | Record in `catalog.probeSources`; this is not automatically a public failure threshold. |
| Official Node Sync | `publication.nodeSync.reference/followers` selected values/release pairs | Derive internal Service names, HTTP ports, replica counts; verify source roles and chain IDs. See [Node Sync](status-page-node-sync.md). |
| Explorer frontend/API | `sources.blockscout` ingress | Derive frontend and enabled backend independently. The rendered data selector still needs validation against the deployed frontend. |

New production examples select `frontends-config.yaml` and
`l2-reth-sequencer-production.yaml`. Change `sources.sequencer` to the effective
numbered file when deployment uses a numbered release, such as
`l2-reth-sequencer-production-0.yaml`. Do not select an unused template containing
`<TODO>` or another network's values. Frontend and sequencer chain IDs are checked
against `config.toml`. Existing callers that omit these optional sources retain
unconfigured evidence; setting either source to `""` disables its inference.

`auto` stays in the inputs so regeneration reads current source values. Explicit
mode overrides and explicit check lists are preserved; `bridgeChecks: []` disables
automatic API checks, and `sequencingMode: unconfigured` disables mode inference.
Only selected non-secret evidence enters the public catalog. Other frontend
configuration, service credentials, and signer fields are not copied.

JSON dependency checks accept either `{url, path, equals}` or `{url, path, type}`,
not both. Supported types are `array`, `object`, `string`, `number`, `boolean`,
and `null`. Browser-origin API requests and direct requests use the same check.
The zero-address history request is not a transfer test and never sends a transaction.
Certificate validation remains enabled.

## Service defaults do not establish processing deadlines

In the inspected dogeos-core source (`57d3315d1`):

- WP indexer polling defaults to 1,000 ms, with one confirmation by default.
- `advance_l1_deposit_stale_after_eligible_blocks` defaults to 5; the frontier
  fallback defaults to 30. These trigger planning using block distance, not an
  upper bound on deposit completion time.
- DA service cycle defaults to 1,000 ms; confirmer polling to 12,000 ms and
  confirmation depth to 1.
- DA `publish.max_batch_wait` defaults to 60 seconds and `max_liveness_delay`
  to 10 minutes. These govern submission selection; the public queue retains
  submitted/failed batches until confirmation, so neither is a completion SLA.

Sources: `crates/withdrawal_processor/src/config.rs` and
`crates/eth_da_submitter/src/service_config.rs` in dogeos-core. Deployment values
can override all of these. Keep the three `*DeadlineSeconds` values at
`0 = unconfigured` until the operator confirms public processing budgets.
The default 5-minute failure window and 10-minute recovery window are additional
monitoring policy, not application execution timeouts.

Official Node Sync uses the existing follower fleet; no independent canary is a
prerequisite in that mode. Select the active sequencer and deployed follower files
and release names. For optional external mode, canary node URLs remain operator
inputs. Independent probe locations/private metrics targets, internal
notification destinations, and the validated explorer selector remain deployment
inputs. Do not use the monitored public RPC as its own independent canary.

## Devnet inspection on 2026-09-28

Read-only inspection of `dogeos-aws-devnet/values/` found:

| Item | Configured value |
| --- | --- |
| Chain ID | `221122` |
| HTTP RPC | `https://rpc.devnet.doge.xyz/` |
| WebSocket | `wss://ws.rpc.devnet.doge.xyz/` |
| Bridge Portal | `https://portal.devnet.doge.xyz/bridge` |
| Frontend Bridge API | `https://bridge-history-api.devnet.doge.xyz/api` |
| Blockscout frontend / API origin | `https://blockscout.devnet.doge.xyz/` |
| Effective sequencer example | `l2-reth-sequencer-production-0.yaml`: empty blocks enabled, 3,000 ms interval |

The RPC returned chain ID `0x35fc2` (221122). The Bridge API request failed
certificate validation with a self-signed certificate, and the Blockscout API
request failed because its certificate was expired. These are observations at
inspection time, not persistent health claims. WebSocket and rendered frontend
health were not verified in this check. Fix endpoint certificates before using
those sites for live acceptance; do not bypass verification in the probe.

The selected Devnet overrides also use two WP confirmations, a 10-second DA
service cycle, a 30-minute batch-open limit and 10-minute publish batch wait.
This illustrates why source defaults must not be copied as deployment SLAs.
The batch-open period is before the public DA batch-queue age begins.

Offline generation against these files produced configured RPC, sequencing and
Bridge Portal rules and was idempotent in the original external Node Sync mode.
Business deadlines, the canary/dependency
checks and the explorer selector remained explicit missing inputs. No chain
values, Kubernetes resources, Instatus configuration or public incidents were
changed by that verification.

A subsequent read-only generation selected sequencer `-0`, bootnodes `-0`/`-1`,
internal RPC and public RPC in official Node Sync mode. The derived Services were
`l2-reth-sequencer-0`, `l2-reth-bootnode-0`, `l2-reth-bootnode-1`, `l2-reth-rpc` and
`l2-reth-rpc-public`, with one replica each and HTTP port 8545. Node Sync became
configuration-ready and repeated generation was unchanged. Release names were
supplied for this offline check; no live Kubernetes discovery or sync health was
verified and no deployment values were written.
