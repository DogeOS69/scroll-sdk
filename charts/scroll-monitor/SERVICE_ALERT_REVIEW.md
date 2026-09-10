# Service alert review

This catalog adds **107 rules**, all **paused when first created in Grafana**.
It supplements the existing enabled business, funding, progress, and log rules.
The alert expressions live under [alerts/services](alerts/services); this document
records their semantics and source requirements, not a copy of service metrics.

## Source versions and ownership

Reviewed on 2026-09-09 against these source commits:

- `DogeOS69/dogeos-core`, `v0.3.0-develop` at `9ae3375fe` (local checkout
  `/data/dogeos-core`, fast-forwarded from `e3fed3e9f` after fetching origin).
- Coordinator metrics implementation in
  `origin/agent/complete-observability-metrics` at `6c138bab8`, including
  `59a875c33` (instrumentation) and `21f2e439c` (histogram buckets). This branch
  **is not merged into the reviewed v0.3.0-develop commit**. Its implementation
  was read with `git show`; it was not merged into the working branch.
- `DogeOS69/dogeos-rollup-node` at `8377dc4`, including derivation and watcher
  metrics. Its pinned `DogeOS69/reth` dependency is `972366a0bfc11cf6a0d5dc79d5e779cd81e32232`;
  the cached source at that exact revision supplies engine, network, downloader,
  transaction-pool, and RPC definitions. Reth's recorder adds the `reth` prefix.

Metrics definitions, exposition examples, and snapshot tests belong in the
repository that exports them. The eight `scroll-sdk` service exposition example
files were removed because they could diverge from the running services. Alert
behavior tests remain here: they supply only the time series necessary to test
queries, pending periods, recovery, and backend activation.

## Activation and upgrades

```yaml
serviceAlerts:
  enabled: true
  paused: true
```

A Helm install or upgrade creates these rules in the `dogeos.services.*` groups
under **Scroll Monitor Alerts**. Review the source prerequisites and thresholds,
then resume selected rules directly in Grafana. Existing rules retain their UI
expressions, labels, and pause state on every import; resuming a new rule is not
undone on upgrade. Changing `serviceAlerts.paused` only affects rules that have
not been created yet. Setting `enabled: false` stops importing the catalog; it
does not delete or pause already stored Grafana rules.

The native Prometheus backend has no pause flag. It omits this catalog while
`paused: true`, even when Grafana is disabled. Set `serviceAlerts.paused: false`
explicitly to render the diagnostic rules into a PrometheusRule. This preserves
the operator's default pause request across backend changes. The original 41
metric rules and the existing log rule keep their previous defaults.

Both per-service target failures and Pod readiness are included. A healthy
replica cannot mask another failed replica. Pod readiness checks include only
Pending or Running pods. They can overlap kube-prometheus-stack workload rules;
resume the desired service-specific routing only where useful. The selectors
assume the deployed job/pod names contain the listed service name; L2 rules use
`l2-reth`. Adapt them in Grafana for custom release names. Scrape failure is not
absence detection: a target removed from discovery requires workload alerts.

## Query design and threshold calibration

- Error events use counter increases, not a lifetime nonzero total. Flat historic
  errors and counter resets alone do not fire. Related lazily registered counters
  share one metric-name selector so an absent counter cannot erase others.
- Readiness and failures are evaluated per target or pod. Cross-metric joins
  retain namespace, job, and instance where the data is emitted by one process.
  No rule compares asynchronous WP and L1 views as an integrity invariant.
- Queue alerts use current nonterminal states and age. Historical terminal proof
  rows, successful rows, cancelled work, and normal idle loops are excluded.
- Reth's no-growth query requires 15 minutes of history and a current series;
  falling height is not progress. Enable it only on lanes that should advance
  continuously. Derivation requires queued work and zero derived-block progress.
- Latency rules use the mean from `_sum` / `_count` with at least five operations
  in ten minutes. This works with the Rust summary exposition as well as the
  histogram implementation; it does not assume `_bucket` exists. They are mean
  latency alerts, not p95 alerts. Error ratios also require a minimum request
  volume to suppress isolated low-traffic failures.
- Queue sizes, operation durations, and age thresholds are initial operating
  limits, not protocol invariants. Calibrate them against signing SLAs, proof
  complexity, traffic, confirmation policy, and configured replacement timers.
  Rule summaries and expressions show the values; the pending column below is
  additional to any lookback or age threshold in the expression.
- No-data is not automatically a service failure. These rules do not fabricate
  zero values for optional metrics. Before resuming, confirm the deployed image
  exports each required metric. Existing missing-balance and target alerts cover
  their own observation failures.

## Service-specific evidence and boundaries

### Withdrawal Processor

Sources: dogeos-core `crates/withdrawal_processor/src/metrics_utils.rs`,
`protocol_metrics.rs`, and `latency_metrics.rs`.

Funding deferral is a scheduler-admission signal, not a failed-job count: an
unfunded bridge lane can be withheld without creating a FailedRetryable row.
This distinguishes bridge funding/reservations from fee-wallet UTXO inventory.
Funding-row corruption and witness/gate invariant failures are safety events.
Operator-intent head drift needs a new rotation request, not indefinite retry.
Pipeline staleness is gated on pipeline enablement; a handoff age of -1 is an
observation failure, not negative waiting time. Its age-probe error counter is
covered separately. The existing post-handoff `WFJobStalled` remains in place;
the new build-queue rule covers earlier statuses.

### TSO Service

Source: dogeos-core `crates/tso_core/src/metrics.rs` and the corresponding TSO
status/response emission sites. Existing alerts cover missing signers, required
role counts, communication failures, and pending work without signing progress.
The additions cover mean response, role quorum and whole-cycle latency, capacity
pressure, and unexpected shadowfork sentinel use. Waiting states are exactly
`proposed`, `collecting_signatures`, and `collecting_p2pkh`. Role latency uses the
emitted lowercase roles; configured registration quorum rules use their own
case-sensitive registration roles.

### Proof Coordinator

Sources: the observability branch's `crates/proof_coordinator/src/metrics.rs`,
`prover_api/server.rs`, and `runner.rs`; mainline `prover_api/observe_degrade.rs`,
`backends/eager_locate_metrics.rs`; WP's `protocol_metrics.rs` for durable work age.

The following nine rules require the **unmerged coordinator instrumentation**:
`ProofCoordinatorNotReady`, `ProofCoordinatorTerminalClaimFault`,
`ProofCoordinatorUploadIssuanceFailing`, `ProofCoordinatorRunLoopFailing`,
`ProofCoordinatorRunLoopStale`, `ProofCoordinatorWorkerFencesRecurring`,
`ProofCoordinatorWorkerAPIErrors`, `ProofCoordinatorWorkerAuthorizationFailures`,
and `ProofCoordinatorWorkerAPISlow`. Deploy an image containing that implementation
before resuming them. This review does not claim those metrics already exist in
mainline or that an image has been published. The branch also adds `/metrics`.
Mainline observe-degrade and eager-locator counters need that exposition endpoint
(or another verified recorder endpoint) to be scraped as well.

`/healthz` deliberately returns HTTP 200 even for a latched terminal WP claim
fault, allowing in-flight proofs to finish. The claim-state gauge and `/readyz`
are the proper readiness signals. `local_upload_issuance_probe_ready` is ready
for a recovery probe, so it is not treated as a terminal state. A zero active
worker lease count by itself is healthy during idle periods; the age of pending
WP prove work detects a capacity problem without inventing a worker-count SLA.
The materialize/prove/verify queue rules query WP but route to proof-coordinator.
Eager locator conflicts are warnings because the completed receipt still binds
the authoritative artifact. Missing locators alone are an expected fallback.

### L2 Reth nodes

Sources: rollup-node `crates/derivation-pipeline/src/metrics.rs` and
`crates/watcher/src/metrics.rs`; pinned Reth `crates/engine/tree/src/tree/metrics.rs`,
`crates/net/network/src/metrics.rs`, `crates/net/downloaders/src/metrics.rs`,
`crates/transaction-pool/src/metrics.rs`, and `crates/rpc/rpc-builder/src/metrics.rs`.

Zero peers can be intentional for an isolated node; leave that rule paused in
such topologies. Forkchoice/payload `syncing` and `accepted` are not invalid
payloads. An L1 reorg is a diagnostic warning, not automatically a violated safety
boundary. Queued transaction counts can reflect nonce gaps or low fees; tune the
1000-transaction limit. No fleet-height difference rule assumes that all nodes
are on the same chain or share the same sequencer/DA derivation role.

### L1 Interface

Sources: dogeos-core `crates/l1_interface/src/protocol_metrics.rs`,
`replay_maintainer.rs`, `replay_read/event_plane.rs`, `indexer.rs`, `db/mod.rs`,
and `rpc/eth_api.rs`.

Service startup readiness does not imply replay readiness. The lag and validation
checks apply only to a configured replay read model; the lag compares discovered
and validated frontiers within that same model. Terminal replay faults and
synthetic transaction-index integrity violations are distinct from normal
confirmation waiting. Database and metrics-read errors can explain stale gauges.
RPC ratio alerts filter `status="error"` and do not count normal success results.

### Ethereum DA Submitter

Source: dogeos-core `crates/eth_da_submitter/src/metrics.rs` plus the publication,
transaction manager, and blob uploader emission sites.

The existing alerts already cover publication deadline, fee caps, general cycle
failures, canonicality, reorg boundaries, and balance. The additions distinguish
parked replay, signing rejection, retry exhaustion, queue validation, archive
integrity, and size/codec conditions that prevent a valid batch. Ordinary prefix
shrinking and hardfork-boundary truncation are expected batching behavior.
Fee-sample absence only alerts when ready work exists. Optional archive task
metrics are tested when present; no missing series is interpreted as a fatal task.
A conclusive anonymous-write probe result `denied` is healthy. `allowed_success`
is critical; indeterminate/disabled/transport failures are warnings and do not
establish that a bucket is public. Archived row counts are current state gauges,
not monotonically increasing error counters.

### CubeSigner Signer

Sources: dogeos-core `ts-packages/cubesigner-signer/src/metrics.ts`,
`policyEvalTree.ts`, and `server.ts`.

PSBT authorization checks include returned-signature and immutable-field integrity.
Policy explain outcomes are **`Permitted` and `Denied`**, not `Allow`: the latter
is policy semantics, not the exported label. Successful signs without observed
`Permitted` evaluations can reveal missing explain telemetry or policy attachment.
Testnet fallback signatures are a policy diagnostic, not automatic evidence of
unauthorized signing. Worker-cycle staleness identifies a hung loop even when
readiness still passes. Cached signed-PSBT delivery retries are not new signing
attempts, so a pending-queue stall can also require TSO callback investigation.

### Fee Oracle

Sources: dogeos-core `crates/fee_oracle/src/monitoring/metrics.rs`,
`calculator/oracle_values.rs`, and `runtime/live`.

The computation timestamp advances for degraded rows as well as usable rows.
New rules therefore inspect the active one-hot status, sampling freshness, and
live transaction state separately. `held` and `deferred` can be ordinary update
policy decisions and are not generic errors. A persistent spike cap can under-
recover DA costs, so it is a warning to review economic policy. Nonce drift,
unsent/orphan requests, replacement eligibility, recovery failure, and execution
reverts concern **L2 update transactions**. Raw fee sampling concerns Ethereum DA.
`still_unconfirmed` is not an execution revert. Account funding stays covered by
the existing L2 balance alert.

## Full rule catalog

Every rule below is paused by default. Follow the linked YAML for its exact
expression and operational response. `Immediate` means no additional pending
period; evaluation and notification intervals still apply.

### [cubesigner-signer](alerts/services/cubesigner-signer.yaml) — 12 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `CubesignerSignerMetricsTargetDown` | A cubesigner-signer metrics target cannot be scraped. | 5m | critical |
| `CubesignerSignerPodNotReady` | A cubesigner-signer pod is not ready. | 10m | critical |
| `CubeSignerSigningAttemptsFail` | CubeSigner signing attempts keep failing. | 5m | critical |
| `CubeSignerPSBTAuthorizationRejected` | CubeSigner rejected PSBT authorization or signed-output integrity. | Immediate | critical |
| `CubeSignerWorkerStale` | CubeSigner background worker has not completed a cycle in five minutes. | 5m | critical |
| `CubeSignerWorkerFailures` | CubeSigner background polling cycles keep failing. | 5m | critical |
| `CubeSignerPendingQueueStalled` | CubeSigner has pending signatures but no successful signing attempts. | 15m | critical |
| `CubeSignerProofFallbackUsed` | CubeSigner signed through a testnet proof fallback. | Immediate | warning |
| `CubeSignerPolicyTelemetryBroken` | CubeSigner policy explain telemetry could not be parsed. | Immediate | critical |
| `CubeSignerMetricsFault` | CubeSigner metric recording failed. | Immediate | warning |
| `CubeSignerPolicyEvaluationMissing` | Successful CubeSigner signs have no observed Permitted policy evaluation. | 10m | critical |
| `CubeSignerSigningSlow` | cubesigner-signer mean operation latency exceeds 30 seconds. | 5m | warning |

### [eth-da-submitter](alerts/services/eth-da-submitter.yaml) — 19 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `EthDaSubmitterMetricsTargetDown` | A eth-da-submitter metrics target cannot be scraped. | 5m | critical |
| `EthDaSubmitterPodNotReady` | A eth-da-submitter pod is not ready. | 10m | critical |
| `EthDAQueueValidationIncomplete` | DA L2 queue-state validation has not completed. | 15m | critical |
| `EthDAParkedReplays` | DA replay or replacement rows remain parked. | 15m | critical |
| `EthDAReplaySafetyBudgetExhausted` | DA automatic replay exhausted its safety budget. | Immediate | critical |
| `EthDASigningFailure` | DA transaction signing failed or was rejected by policy. | Immediate | critical |
| `EthDAReplacementFailure` | DA replacement transactions keep failing. | 5m | critical |
| `EthDAFeeSampleUnavailable` | DA cannot obtain a fee sample while publication work is ready. | 10m | warning |
| `EthDAWindowBudgetBlocked` | The publication window budget repeatedly defers DA work. | 15m | warning |
| `EthDABatchDataInvalid` | DA batch construction encountered corrupt or unpublishable data. | Immediate | critical |
| `EthDALifecycleCorrelationFailure` | DA lifecycle events cannot be correlated to durable submissions. | Immediate | critical |
| `EthDABlobUploadRetryExhausted` | Blob archive uploads exhausted their retry budget. | 5m | critical |
| `EthDABlobArchiveConflict` | Blob archive rows are in a terminal conflict state. | Immediate | critical |
| `EthDABlobArchiveMalformedState` | Blob archive recovery found malformed or inconsistent durable state. | Immediate | critical |
| `EthDABlobUploadFailures` | Archive upload writer failures persist. | 10m | critical |
| `EthDAArchiveTaskFatal` | The blob uploader is in fatal restart backoff. | 2m | critical |
| `EthDASegmentationSidecarFatal` | The chunk-segmentation sidecar publisher hit a fatal condition. | Immediate | critical |
| `EthDAArchiveAnonymousWriteAllowed` | The archive accepted an anonymous S3 write probe. | Immediate | critical |
| `EthDAArchiveWriteProbeInconclusive` | The archive write-permission probe did not confirm denial. | Immediate | warning |

### [fee-oracle](alerts/services/fee-oracle.yaml) — 13 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `FeeOracleMetricsTargetDown` | A fee-oracle metrics target cannot be scraped. | 5m | critical |
| `FeeOraclePodNotReady` | A fee-oracle pod is not ready. | 10m | critical |
| `FeeOracleCalculationInvalid` | Fee oracle computation has an invalid configuration or arithmetic overflow. | Immediate | critical |
| `FeeOracleCalculationNotReady` | Fee oracle computation remains not ready. | 10m | critical |
| `FeeOracleRawSampleStale` | The raw Ethereum DA fee sample is stale or unavailable. | 10m | warning |
| `FeeOraclePriceFeedFailures` | Oracle price fetching keeps failing. | 10m | warning |
| `FeeOracleBlobFeeCapped` | The configured blob fee spike cap limits the oracle fee. | 15m | warning |
| `FeeOracleNonceDrift` | Oracle update requests remain blocked by nonce drift. | 10m | critical |
| `FeeOracleUnsentRequests` | Oracle update requests remain unsigned or unsent. | 15m | critical |
| `FeeOracleTransactionsStuck` | Oracle transactions remain eligible for stuck-transaction replacement. | 15m | critical |
| `FeeOracleExecutionReverted` | An oracle update transaction reverted on L2. | Immediate | critical |
| `FeeOracleLiveRecoveryFailures` | Oracle live-update recovery keeps failing or abandoning requests. | 5m | critical |
| `FeeOracleLiveSubmissionFailure` | Oracle live submission fails before broadcast. | 5m | critical |

### [l1-interface](alerts/services/l1-interface.yaml) — 11 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `L1InterfaceMetricsTargetDown` | A l1-interface metrics target cannot be scraped. | 5m | critical |
| `L1InterfacePodNotReady` | A l1-interface pod is not ready. | 10m | critical |
| `L1InterfaceReplayLagging` | L1 Interface discovered replay work is more than 10 WF transactions ahead of validation. | 15m | warning |
| `L1InterfaceReplayValidationUnavailable` | The configured L1 replay read model remains unready. | 10m | critical |
| `L1InterfaceReplayTerminalFault` | L1 replay committed a terminal validation fault. | Immediate | critical |
| `L1InterfaceSyntheticIndexIntegrityViolation` | The synthetic transaction index violated an integrity check. | Immediate | critical |
| `L1InterfaceIndexerFailures` | L1 Interface Dogecoin indexing keeps failing. | 10m | critical |
| `L1InterfaceDatabaseFailures` | L1 Interface database operations keep failing. | 5m | critical |
| `L1InterfaceProtocolMetricsReadFailure` | L1 Interface cannot refresh protocol metrics. | 5m | warning |
| `L1InterfaceRPCErrors` | L1 Interface RPC errors exceed 5 percent. | 5m | warning |
| `L1InterfaceRPCSlow` | l1-interface mean operation latency exceeds 2 seconds. | 5m | warning |

### [l2-reth](alerts/services/l2-reth.yaml) — 12 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `L2RethMetricsTargetDown` | A l2-reth metrics target cannot be scraped. | 5m | critical |
| `L2RethPodNotReady` | A l2-reth pod is not ready. | 10m | critical |
| `L2RethNoPeers` | An L2 Reth node has no connected peers. | 10m | critical |
| `L2RethHeadStalled` | An L2 Reth canonical head has not advanced for 15 minutes. | Immediate | critical |
| `L2RethDerivationStalled` | L2 derivation has queued work but produces no blocks. | 15m | critical |
| `L2RethPayloadValidationFailed` | Reth rejected a payload or forkchoice update. | Immediate | critical |
| `L2RethDownloaderErrors` | Reth block downloads keep failing. | 10m | warning |
| `L2RethRPCErrors` | L2 Reth RPC failure ratio exceeds 10 percent. | 5m | warning |
| `L2RethRPCSlow` | l2-reth mean operation latency exceeds 2 seconds. | 5m | warning |
| `L2RethBlobStoreFailure` | Reth transaction-pool blob storage operations failed. | Immediate | critical |
| `L2RethTransactionQueueLarge` | The Reth queued transaction pool exceeds 1000 transactions. | 15m | warning |
| `L2RethL1ReorgObserved` | The L2 derivation watcher observed an L1 reorg. | Immediate | warning |

### [proof-coordinator](alerts/services/proof-coordinator.yaml) — 17 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `ProofCoordinatorMetricsTargetDown` | A proof-coordinator metrics target cannot be scraped. | 5m | critical |
| `ProofCoordinatorPodNotReady` | A proof-coordinator pod is not ready. | 10m | critical |
| `ProofCoordinatorNotReady` | Proof Coordinator cannot admit worker claims. | 5m | critical |
| `ProofCoordinatorTerminalClaimFault` | Proof Coordinator latched a terminal WP claim fault. | Immediate | critical |
| `ProofCoordinatorUploadIssuanceFailing` | Proof Coordinator cannot issue upload capabilities. | 5m | critical |
| `ProofCoordinatorRunLoopFailing` | The coordinator proof-work loop keeps failing. | 5m | critical |
| `ProofCoordinatorRunLoopStale` | The coordinator has no successful or idle tick in 15 minutes. | 5m | critical |
| `ProofCoordinatorWorkerFencesRecurring` | Workers repeatedly lose their proof leases. | 10m | warning |
| `ProofCoordinatorWorkerAPIErrors` | Worker API server errors exceed 5 percent. | 5m | warning |
| `ProofCoordinatorWorkerAuthorizationFailures` | Worker authentication or authorization is failing. | 5m | critical |
| `ProofCoordinatorWorkerAPISlow` | proof-coordinator mean operation latency exceeds 5 seconds. | 5m | warning |
| `ProofMaterializationQueueStalled` | Proof materialization work is not being drained. | 10m | critical |
| `ProofVerificationQueueStalled` | Proof verification or result import is delayed. | 10m | critical |
| `ProofWorkerQueueStalled` | Proof work waits more than one hour for progress. | 10m | critical |
| `ProofCoordinatorObserveDegraded` | A terminal real-proof failure was degraded to mock retry. | Immediate | warning |
| `ProofCoordinatorEagerLocatorInvalid` | An eager artifact locator failed validation. | Immediate | warning |
| `ProofCoordinatorEagerLocatorConflict` | Eager locator publication found conflicting bytes. | Immediate | warning |

### [tso-service](alerts/services/tso-service.yaml) — 7 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `TsoServiceMetricsTargetDown` | A tso-service metrics target cannot be scraped. | 5m | critical |
| `TsoServicePodNotReady` | A tso-service pod is not ready. | 10m | critical |
| `TSOSigningCycleSlow` | tso-service mean operation latency exceeds 120 seconds. | 5m | warning |
| `TSOSignerResponseSlow` | tso-service mean operation latency exceeds 60 seconds. | 5m | warning |
| `TSORoleQuorumSlow` | tso-service mean operation latency exceeds 120 seconds. | 5m | warning |
| `TSOSigningQueueLarge` | TSO pending signing work exceeds 100 transactions. | 15m | warning |
| `TSOShadowforkSentinelAccepted` | TSO accepted a shadowfork sentinel signature. | Immediate | warning |

### [withdrawal-processor](alerts/services/withdrawal-processor.yaml) — 16 rules

| Rule | Condition / symptom | Pending | Severity |
| --- | --- | --- | --- |
| `WithdrawalProcessorMetricsTargetDown` | A withdrawal-processor metrics target cannot be scraped. | 5m | critical |
| `WithdrawalProcessorPodNotReady` | A withdrawal-processor pod is not ready. | 10m | critical |
| `WFFundingDataCorrupt` | Persisted WF funding data is corrupt. | Immediate | critical |
| `WFBridgeFundingDeferred` | WF work remains blocked by bridge funding. | 15m | warning |
| `WFOperatorIntentHeadDrift` | A rotation request was terminalized after replay-head drift. | Immediate | critical |
| `WFProofGateInvariantViolation` | A WF proof gate or witness invariant failed. | Immediate | critical |
| `WFWitnessInvariantViolation` | Bridge witness materialization hit a terminal invariant. | Immediate | critical |
| `WFProofRuntimeUnavailable` | WF proof dependencies keep failing. | 10m | critical |
| `WFWitnessArtifactMissing` | Bridge witness artifact bytes remain unavailable. | 5m | critical |
| `WFTSOHandoffRecoveryFailures` | TSO handoff recovery cannot complete or observe its backlog. | 5m | critical |
| `WFTSOHandoffRecoveryBlocked` | A stale TSO handoff blocks dispatch. | 5m | critical |
| `WFL2ProofPipelineFailing` | The L2 proof pipeline keeps failing. | 5m | critical |
| `WFL2ProofPipelineStale` | The enabled L2 proof pipeline has no recent successful pass. | 5m | critical |
| `WFBuildQueueStalled` | A WF job is stuck before successful TSO handoff. | 10m | critical |
| `WFProtocolMetricsReadFailure` | WP protocol metrics cannot read their source state. | 5m | warning |
| `WFDatabasePoolSlow` | withdrawal-processor mean operation latency exceeds 1 seconds. | 5m | warning |

## Deliberately deferred conditions

- Deposit/withdrawal age SLAs need oldest-pending time metrics with bounded labels;
  status totals alone cannot prove a time SLA.
- Reservation-adjusted fee-wallet spendability needs an exported reservation or
  spendable-value metric; the existing canonical UTXO total is not that value.
- A reviewed CubeSigner policy-hash mismatch needs deployment-owned expected pins;
  comparing info labels without the reviewed identity would invent policy.
- Per-role TSO quorum counts must come from the bridge policy, using the existing
  `businessAlerts.requiredSignersByRole` map.
- Proving duration limits need proof-family and workload-size budgets. Pending
  queue age is covered; a running large proof is not automatically stalled.
- Disk exhaustion, OOM, crash loops, CPU throttling, and PVC usage remain covered
  by the Kubernetes stack where its infrastructure rules are enabled. Avoid
  duplicating them as speculative application counter thresholds.
