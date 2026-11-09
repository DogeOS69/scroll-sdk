# Public component health rules

Current implementation: 2026-10-01. The rules and collectors are implemented. Enabling them requires
deploying the matching application images, the existing Alloy public probes and the generated
monitoring configuration. Every component defaults to `automatic`, and an initial OPERATIONAL state is
not treated as evidence of health. See [component publication configuration](status-page-publication.md)
for fields and generation commands.

## Three-state contract

Each component's custom expression must return a single unlabeled 0 (healthy), 1 (failing) or no
series (unobservable). Non-binary values, multiple series, NaN, missing required sources and stale or
future timestamps cannot represent health. Built-in rules also carry an internal partial-observation
marker: a confirmed failure still stands, but observation completeness and the monitoring heartbeat
must keep the gap. The scroll-monitor scripts own the rules and confirmation windows and gather
evidence through Prometheus. An unknown period resets the confirmation window, keeps an existing
failure and does not send a recovery. Grafana only displays results and handles internal alerts; it
does not control public status. `up=1` only means the scrape succeeded; the business snapshot time
must also be checked.

## Probe modes

The first version selects `probes.mode: alloy`, reusing the existing Alloy without adding a public
probe Pod. Public RPC checks the HTTP JSON-RPC response pattern and latency; Bridge/Blockscout check
HTTP/TLS availability of the page and API entry points. CLI readiness labels these
`public-entrypoint`, and the public description no longer claims that these checks prove browser
functionality or indexing freshness. WebSocket runs real JSON-RPC checks through a helper container in
the existing Alloy Pod. With the official Node Sync mode and continuous block production, Sequencing
reuses the reference sequencer's block time; other modes need custom rules. See
[Alloy public probes](status-page-alloy.md) for all parameters and limits.

## Eight components (external deep-probe mode and common business rules)

| Component | Implemented check | Deployer must provide |
| --- | --- | --- |
| Public RPC | Runs chainId, blockNumber and block queries against every public HTTP/WS entry point; checks the returned content and p95 request-sequence duration | Independent probe locations; latency thresholds adjusted per chain |
| Transaction Sequencing | Checks the latest block time while RPC observation is valid; an RPC failure cannot be attributed directly to a sequencer failure | An explicit continuous block-production mode and maximum block age; on-demand block production needs a custom executable backlog expression |
| Deposits | Confirmed canonical deposits not yet scanned plus deposits submitted but not consumed by L2; index, replay and RPC canonical chain agree | New WP image and an explicit processing deadline |
| Withdrawals | Index range of protocol-eligible unfinished withdrawals, the complete unique queue and canonical replay; earliest eligibility time | New WP image and an explicit processing deadline; not measured from the user's original transaction |
| Batch Publication | Unconfirmed batches in pending_publish / submitted / failed, excluding confirmed, finalized and archived items | New DA image and a deadline that includes normal confirmation time |
| Node Sync | Official mode compares, per Pod, the same-height hash and time difference of bootnodes, internal RPC and public RPC against the active sequencer; a failed reference source or incomplete membership is unknown | Select valid values/releases; an independent canary is an optional external mode, see [Node Sync](status-page-node-sync.md) |
| Bridge Portal | Chromium renders the deposit/withdrawal UI, checks chain identity and the deposit payload, and verifies required API responses in the browser | API type checks are generated from the frontend configuration by default; JSON paths/semantics can be overridden; never signs or initiates transfers |
| Block Explorer | Chromium data selector plus the Blockscout latest indexed block API; compares same-height hash and block time with the canonical chain | Backend entry point (can be derived automatically), a CSS selector for real data, tolerated indexing lag |

External-mode public RPC/web probes need at least two independent locations, each with fresh, valid
data and consistent results. Partial absence, duplicate reporters or diverging observations become
unknown; one successful probe cannot override another failing probe. Location independence is
guaranteed by the actual deployment: two renamed replicas in the same cluster are not independent
locations. The official Node Sync collector runs inside the chain and does not count as an external
probe location.

Business rules must select the complete set of real service targets and their namespace. Configure the
expected WP/DA target counts; a missing target must not lower the recovery requirement. WP's proof-only
role must not be mixed in. The deposit integrity check covers mid-scan cursors, missing records,
unclassified data, lagging replay and same-height reorgs. The DA rule keeps submitted but unconfirmed
work in the backlog, so work is not mistaken as done just because it left the pending-send queue. When
a business queue is fully observed and empty, it explicitly outputs 0 items and 0 seconds, so normal
idleness is not treated as a failure.

## Current defaults and configurable parameters

| Parameter | Production default | Meaning |
| --- | --- | --- |
| `health.failureFor` | `5m` | Sustained failure confirmation; a component can override it with `rule.for` |
| `health.recoveryFor` | `10m` | Continuous fresh health required to recover |
| `health.freshnessSeconds` | `120` | Maximum age of underlying observations |
| `health.minimumProbeLocations` | `2` | Used only in external mode; Alloy does not pretend to be two locations |
| `health.maxRpcLatencySeconds` | `2` | p95 of each Alloy HTTP probe / external RPC query sequence; needs at least 10 samples within 5 minutes |
| Maximum block age / indexing lag / node lag | `120` seconds each | Deployer confirms against actual chain behavior |
| Deposit / withdrawal / batch deadline | `0` | Unconfigured; no business SLA is invented and the corresponding built-in rule is not generated |
| `components.<key>.affectedStatus` | No default | CLI-managed automatic publication must set it explicitly and review the rule semantics; severity cannot be derived from a binary rule |
| `incidents.notifySubscribers` | `false` | The template requests subscriber notification only when explicitly enabled |

These are configuration defaults, not public commitments. The 3/5/10-minute tiers and recovery
hysteresis discussed in the earlier design do not automatically become current parameters; the
generated configuration is authoritative. Custom expressions need `rule.builtin: false` and follow the
same three-state contract.

## Publication and operations boundaries

Each component has exactly one final rule and webhook. Multiple internal causes must first be combined
into the component expression, so the recovery of one cause cannot override another failure. Existing
internal diagnostic rules do not map directly to public status. The validator persists the current
incident and waits for a full window again after a restart, an unknown period, a sampling gap or a
clock rollback. For manual maintenance or incident takeover, deploy manual mode first; existing
incidents and receipts are kept. Linking scheduled maintenance windows to automatic publication is
deferred until after the first probe deployment and acceptance of a real failure and recovery.

Loss of the whole monitoring cluster notifies the internal on-call through the heartbeat timeout of an
Instatus Cron Monitor. With a delivery validator, the heartbeat also depends on the validator running
freshly with no delivery errors. Loss of monitoring does not automatically mark every component as
failed. Real Instatus templates, duplicate delivery, recovery correlation and subscriber behavior must
pass first-version acceptance against a test target. Dedicated acceptance of the maintenance link
follows its later implementation. Local tests use a local HTTP receiver and do not trigger public
incidents.

## Collection template fixes and validation

scroll-monitor's PodMonitor discovery selects by release namespace/instance labels, consistent with
ServiceMonitor discovery, and covers the existing Blockscout frontend PodMonitor. The
eager-materializer example enables the application's own ServiceMonitor instead of creating a
duplicate. The proof coordinator has no application metrics endpoint, so adding a ServiceMonitor cannot
fix it; its related diagnostic rules stay paused.

Regression coverage includes real Prometheus expression evaluation, CLI-to-Helm rendering, Grafana
13.3.0 notification formatting, browser rendering/API failures, delivery restarts and blocked recovery
during unknown periods, and business database integrity and reorgs. See
[configuration automation](status-page-automation.md) for deployment steps and
[local acceptance](status-page-publication.md#reproducing-local-acceptance) for acceptance checks.

## WF stalls affect deposits and withdrawals

The built-in deposit and withdrawal rules also check WF. `health.wfStallSeconds` defaults to 3600
seconds. It uses core's read-only `withdrawal_processor_public_workflow_*` snapshot together with the
validity and timestamps of the jobs source, and no longer queries one-hour Prometheus `offset` history
by Pod IP. A stall is confirmed only when queued, building, built, failed_retryable, bug,
proposed_to_tso or awaiting_replay work is older than the limit and core has continuously observed the
same canonical WF head for longer than the limit. Historical completed / failed_terminal rows do not
participate; when idle, or when no job has exceeded the limit yet, WF can be judged healthy
immediately. Replay persists the first-observed time of a recent canonical head, so a new process can
also use this positive progress evidence. This is not the scrape time and repeated reads do not refresh
it.

The continuous stall time is computed with core's monotonic clock. A read failure, a collection gap
longer than 45 seconds, a change of head identity (including a same-height reorg), a clock going
backwards or a process restart all restart the timer. After a restart, even if an old job has already
exceeded the limit and there is no recent progress evidence, continuous observation is still required;
unobserved time before the restart must not count as stalled. An older core without the new workflow
metrics is unknown: upgrade core first during deployment, then regenerate the CLI configuration.

When the WF snapshot itself is valid and clearly stalled, both components output affected, even if the
separate deposit or withdrawal queue snapshot is invalid. A failed global consistency check also
invalidates the workflow snapshot, and old values cannot be used to publish a failure. A business
backlog exceeding its deadline can independently be judged affected. Recovery is allowed only when
both the WF and business snapshots prove normal; missing metrics are never replaced with 0. The normal
failure confirmation window `failureFor` (default 5m) and recovery window `recoveryFor` (default 10m)
still apply, so with defaults a WF stall is published after about 65 minutes.

New templates and components that omit mode default to automatic. The top-level statusPage.enabled
still has to be enabled explicitly. When automatic mode lacks a business deadline, a health expression,
a heartbeat or an explicit severity, the CLI reports an error instead of silently downgrading to
observe. Existing configurations that explicitly set observe must be migrated deliberately. The
deposit and withdrawal examples explicitly use MAJOROUTAGE; a binary rule cannot yet distinguish a
complete WF halt from partial request timeouts. Provide a reviewed custom rule and policy when finer
severity is needed.

## L2 adoption stalls affect withdrawals

Withdrawals reuses the progress expression and configured window from
`L2BatchHeightStalled`. Set `businessAlerts.l2BatchStallSeconds` in scroll-monitor
values (integer seconds, minimum 60; default 7500 seconds / 125 minutes):

```yaml
businessAlerts:
  l2BatchStallSeconds: 7500
```

The expression lives in `scripts/l2-batch-progress.json`. Helm injects the same
configured duration into Grafana/Prometheus alerts, their annotations, and the
shared definition mounted by the status-page evaluator. Changing the value also
rolls the evaluator through its configuration checksum. The CLI does not generate
a separate expression or timeout, so CLI regeneration is unnecessary. When using
`helm upgrade --reuse-values` from an older chart, explicitly supply this new value
with `--set businessAlerts.l2BatchStallSeconds=7500` or an overriding values file.
Only an increase in adopted L2 batch height counts as progress. A decrease does
not establish recovery, and AdvanceL1 WF progress cannot substitute for AdvanceL2.
The shared expression also compares current height with the window-start height,
so progress during a scrape gap or Pod replacement clears the diagnostic alert.

Public failure additionally requires outstanding DA batches throughout the window:
`protocol_latest_da_batch_height > protocol_state_l2_batch_height`. Snapshots are
validated per target, then aggregated by the alert's stable `namespace/job`
identity so a Pod IP change does not erase service history. Both replay and L2
snapshots must be valid and fresh at the current observation and window start.
History is sampled every minute. A gap inside an otherwise confirmed stall marks
the failure as partial coverage; a missing start anchor or invalid current
snapshot is unknown. A partial failure cannot establish a monitoring heartbeat.
Fresh, valid current height higher than the valid window-start height positively
proves progress even across a Pod replacement or a historical scrape gap. No
outstanding DA work, or a recent observed interval caught up with DA, also rules
out a continuous stall. An absent alert alone never proves recovery.

This covers proof/materialize failures that block AdvanceL2 while the eligible
withdrawal queue is empty and AdvanceL1 continues. Confirmed failure reports
`unavailable` with reason `l2_progress_stalled`, even when queue and WF checks pass.
Publication retains the existing `failureFor` (default 5 minutes) and `recoveryFor`
(default 10 minutes). With defaults, continuous outstanding work without progress
therefore publishes an incident after approximately 130 minutes; publication does
not add a second 125-minute confirmation window.
