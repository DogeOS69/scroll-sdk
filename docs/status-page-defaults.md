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
