# DogeOS dashboard source review

Reviewed on 2026-09-28. This covers all eleven dashboards provisioned into the
`dogeos` Grafana folder, including Dstack and GPU fleets. It records a source
review and local validation, not production acceptance or a deployment.

## Source revisions

- dogeos-core: `/data/dogeos-core`, commit
  `7ff5e30f18756c949935c4341c664b60d6af7c05`.
- [dogeos-core #1007](https://github.com/DogeOS69/dogeos-core/pull/1007): reviewed
  commit `5bd4635b6dfafff0fb8f27689a81c2b35e86546f`, still unmerged at review time.
  Its additional signer and coordinator instrumentation is a separate rollout
  dependency, not assumed to exist in the current baseline.
- [dstack 0.21.5 native exporter](https://github.com/dstackai/dstack/blob/0.21.5/src/dstack/_internal/server/services/prometheus/custom_metrics.py).
- Dogecoin RPC-to-metric mapping: this SDK's
  [metrics-exporter configuration](../metrics-exporter/templates/config.yaml).
- Runtime and log labels: kube-state-metrics, cAdvisor and this chart's Alloy
  relabel configuration.

For Rust metrics, registration macros alone do not determine the Prometheus
wire format. The shared `crates/metrics_utils/src/lib.rs` exporter configuration
exports time histograms ending in `_seconds` or `_latency_ms` as buckets.
Service-specific overrides also matter. Other distributions can remain
summaries. The review checked declarations, recording sites, labels, units and
exporter configuration together.

## Dashboard findings and changes

| Dashboard | Source of application metrics | Findings and resulting behavior |
| --- | --- | --- |
| Service Operations | Core service metrics, indexer metrics, kube-state-metrics, cAdvisor and Alloy logs | Time percentiles use histogram buckets. Namespace labels survive aggregation. Readiness preserves unhealthy instances. Indexer lag joins the corresponding namespace and compares against downloaded Dogecoin blocks, not headers. Loki queries accept the default All selection and respect the selected service; All services remains scoped to DogeOS workloads. |
| Dogecoin Node | SDK `metrics-exporter` RPC mapping | The legacy metric named `mempool_bytes_total` is a current byte gauge; `mempool_size_bytes` actually contains transaction count. Panels use those actual meanings and do not take a rate of current mempool bytes. The string-valued RPC error field cannot serve as a numeric error counter. Its old panel is replaced with clearly labelled exporter scrape health, which does not establish RPC health. Network and memory units are explicit. |
| TSO Service | `crates/tso_core/src/metrics.rs` and recording sites | Replicated inventory snapshots remain separate by namespace and instance instead of being summed into a duplicated total. Signer identity rows select active entries; old identity series reset to zero are excluded. |
| Withdrawal Processor | `crates/withdrawal_processor/src/protocol_metrics.rs`, `latency_metrics.rs` and worker recording sites | Time quantiles use buckets. Removed two bootstrap height/index queries that have no emitted metric in the reviewed sources. Count, DOGE and duration series have separate units. The proof-age panel explicitly includes failed work items. |
| L1 Interface | `crates/l1_interface/src/protocol_metrics.rs`, RPC, database and indexer recording sites | Time quantiles use buckets. Readiness and namespace aggregation preserve instance failures and network boundaries. Embedded indexer metrics retain the owning job filter. |
| Ethereum DA Submitter | `crates/eth_da_submitter/src/metrics.rs` and service initialization | Time quantiles use buckets while size distributions follow their actual exporter configuration. Separate units distinguish queue counts, elapsed seconds, throughput and cost. Readiness does not use a global maximum that masks a failing replica. |
| Fee Oracle | `crates/fee_oracle/src/monitoring/metrics.rs` | Time quantiles use buckets. The latest-status panel selects the active one-hot value rather than displaying historical status labels reset to zero. |
| CubeSigner Signer | `ts-packages/cubesigner-signer/src/metrics.ts` and recording sites | Prometheus histograms and existing labels match the source. Zero last-cycle timestamps are not rendered as an age since 1970. The All job selection cannot include unrelated healthy targets. Policy-rule identity remains an observed history, not an invented current-only inventory. |
| Attestation Signer | `crates/attestation_signer/src/metrics.rs`, HTTP and worker code; #1007 additions | Current worker-loaded rows are labelled as a bounded in-memory view, not the durable backlog. Extended durable queue, loop freshness and terminal-request panels remain in a collapsed row labelled #1007. Time histograms use buckets. Artifact-size percentiles support current per-instance summaries and #1007 buckets, preferring buckets where available. |
| Proof Coordinator | Kubernetes runtime metrics, WP-owned durable queues, and #1007 coordinator metrics | Always-visible panels show runtime state and WP queue depth/age. Native coordinator readiness, workers, leases and work-attempt panels remain in a collapsed row labelled #1007. Pod readiness is distinguished from claim-plane readiness; queues retain WP as their source. |
| Dstack and GPU fleets | dstack 0.21.5 native exporter and optional host exporters | GPU model uses the emitted `dstack_gpu` label. Native DCGM panels exclude separately scraped host series to avoid duplication. Legends retain controller/project/GPU identity, and CPU time rate is displayed in cores. Run-count changes describe retained database rows; they are not an immutable completion-event ledger. |

Across the dashboards, current stat/table panels use instant queries, missing
series remain `No data`, and time-series gaps are not connected. These choices
avoid presenting a previous healthy value as a current result. They do not
detect an absent replica by themselves; expected-replica and scrape alerts
remain necessary.

## Timing boundaries in #1007

- Signer request lifetime runs from intake to a durable terminal state. It
  includes configured signing delay, retries and process downtime. Completion
  outcomes distinguish submission, TSO rejection and permanent failure.
- Coordinator work-item duration measures a claimed processing attempt,
  including reporting the result to Withdrawal Processor. It excludes claim
  wait and remote proving. A successful attempt requires WP acknowledgement;
  attempt counts are not unique durable work-item counts.
- Signer last-success timestamps describe worker-loop freshness, including
  idle ticks and handled row failures. They do not prove that signing succeeded.

These boundaries are also stated in the relevant panel descriptions.

## Verification

- Checked dashboard metric names against the reviewed core declarations and
  #1007 implementation; checked external metric ownership separately. No
  unresolved application metric names remained in this review.
- Eight dashboard structure/query-shape tests and six existing dstack tests
  passed. The dashboard tests are included in the status-page CI workflow.
- Prometheus 2.52.0 `promtool` accepted all 429 PromQL expressions after Grafana
  variable substitution.
- Nine temporary behavioral scenarios passed: falling mempool values,
  namespace-separated block lag, unhealthy replica readiness, zero timestamps,
  replicated TSO inventory, artifact histogram preference and summary fallback,
  absent service targets, and native/host GPU isolation.
- A rendered Helm ConfigMap provisioned all eleven dashboards into a disposable
  Grafana 11.1.5 instance. All 429 PromQL and three LogQL queries executed against
  local Prometheus 2.52.0 and Loki 3.1.1 without errors. Empty data sources
  produced empty results rather than fabricated healthy values.
- Helm strict lint and repository chart/version checks passed.

Local query execution checks do not establish that a deployed service exposes
the same revision, that external scrape targets are configured, or that GPU
telemetry is available. This was not a visual browser acceptance test. No
Devnet release or local dstack process was changed by this review.

## Rollout and future reviews

1. Deploy an application image matching the intended metric implementation.
   #1007 panels require that implementation and an enabled `/metrics` scrape;
   merging the PR alone does not populate them.
2. Confirm the external signer/coordinator job names match the dashboard's job
   selector and that expected targets are actually scraped. Select the deployed
   namespace and check real series after the next scrape interval.
3. Validate dstack against the deployed dstack version. Optional host exporters
   require their own targets; absent targets should continue to show `No data`.
4. For future core changes, review metric declarations, labels, recording sites
   and exporter configuration directly at the intended source revision, then
   validate the affected dashboard expressions.

No service metric exposition snapshots or example metric payloads are stored in
this repository for this review. Source extracts and synthetic query-test data
were temporary local artifacts. The checked-in tests validate dashboard
structure and query behavior constraints; they are not a copied service metric
contract and do not replace reviewing updated core source.

## Acceptance with older application images

Do not upgrade application images to validate this chart. Skip panels and alerts
whose metric implementation is absent from the deployed image, and record the
reason as an image prerequisite rather than a failed dashboard. In particular,
Proof Coordinator application telemetry stays `No data` until its new image is
published and deployed. Missing business snapshots must not become healthy public
status. Use Slack as the first internal notification acceptance target; leave
SMTP disabled unless the operator explicitly configures it.
