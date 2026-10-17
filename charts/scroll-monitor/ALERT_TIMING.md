# Alert timing configuration

Set optional overrides in `examples/values/scroll-monitor-production.yaml` (or
`charts/scroll-monitor/values/production.yaml`). Helm merges partial maps: omit
`alertTiming`, use `rules: {}`, or configure only the fields you need. Omitted
fields retain the existing chart defaults and existing section-level settings.
This interface covers the chart's metric and log alerts, including optional
Dstack and status-evaluator diagnostic rules. It does not change service request
timeouts, notification delivery intervals, or public status-page health policy.

```yaml
alertTiming:
  groupIntervals:
    dogeos.metrics: 30s
    dogeos.logs: 1m
  rules:
    FeeOracleStale:
      for: 10m
      maxAgeSeconds: 1800
    DogecoinIndexerLag:
      window: 5m
    ProtocolStateWFTxNumberStalled:
      window: 90m
      step: 1m
    ProofWorkerQueueStalled:
      for: 15m
      maxAgeSeconds: 7200
    TSOSignerResponseSlow:
      window: 15m
      latencySeconds: 90
    ServiceErrorLogs:
      for: 0s
      window: 10m
businessAlerts:
  l2BatchStallSeconds: 9000
```

## Fields and precedence

| Field | Meaning | Accepted values |
| --- | --- | --- |
| `rules.<AlertName>.for` | Condition must remain true this long before firing. Available on every rule, including rules whose default is immediate. | Nonnegative duration; `0s` is immediate. |
| `rules.<AlertName>.window` | Query lookback, history requirement and matching offset. All occurrences in that rule change together. | Positive duration. |
| `rules.<AlertName>.step` | Progress subquery resolution and adjacent-sample comparison offset. | Positive duration no larger than `window`. |
| `rules.<AlertName>.maxAgeSeconds` | Maximum age of observations, queued work or stalled activity. | Positive number of seconds. |
| `rules.<AlertName>.latencySeconds` | Mean operation latency threshold; sample count requirements remain unchanged. | Positive number of seconds, including fractional seconds. |
| `rules.<AlertName>.snapshotMaxAgeSeconds` | Freshness guard for a cached WP/TSO snapshot. | Positive number of seconds. |
| `rules.<AlertName>.predictionSeconds` | Inode-exhaustion prediction horizon. | Positive number of seconds. |
| `groupIntervals.<GroupName>` | Evaluation frequency for a rule group. | Positive duration. |

Durations use one integer and unit: `s`, `m`, `h`, `d`, or `w` (for example `90m`).
Use only the parameters listed for a rule below; misspelled names, unsupported
parameters, negative/zero windows and wrong value types fail Helm rendering.
Disabling a rule's feature does not invalidate its known timing configuration;
the values take effect when the feature is enabled again. Windows must still
contain sufficient scrape samples for the rule to evaluate; changing a window
does not change the sampling requirements or telemetry collection interval.

The `for` delay is additional to the query's observation window/age threshold.
For example `maxAgeSeconds: 1800` plus `for: 10m` requires an observation older
than 30 minutes to remain stale for another 10 minutes before firing.
`BusinessPodContainerRestarted` and `BusinessPodContainerFailed` also derive
their timestamp age checks from `window`, so those checks cannot drift apart.

Explicit per-rule timing wins over existing section-level settings. An omitted
per-rule field uses its section-level value or the rule's shipped default.
The following existing settings remain supported:

| Existing setting | Default | Applies to |
| --- | --- | --- |
| `businessAlerts.l2BatchStallSeconds` | 7500 | L2 batch progress alert and Withdrawals public health; keep this shared window here. |
| `businessAlerts.jobMaxAgeSeconds` | 900 | `WFJobStalled` age threshold. |
| `businessAlerts.publicationDeadlineSeconds` | 3600 | `EthDAPublicationFeeBlocked` publication age. |
| `businessAlerts.proofStuckFor` | 5m | Exhausted proof retries and terminal L2 proof ranges. |
| `businessAlerts.recoveryFor` | 15m | `ProtocolReorgRecoveryStalled`. |
| `businessAlerts.signerFailureFor` | 5m | TSO communication and attestation signing/callback failures. |
| `diskAlerts.warningFor`, `criticalFor` | 15m, 5m | Disk usage and inode usage alerts. |
| `diskAlerts.predictionWarningHours`, `predictionCriticalHours` | 24, 4 | Disk exhaustion forecast horizons. |
| `diskAlerts.predictionWarningFor`, `predictionCriticalFor` | 30m, 5m | Disk exhaustion pending periods. |
| `resourceAlerts.memoryWarningFor`, `memoryCriticalFor` | 10m, 5m | Node/container memory alerts. |
| `resourceAlerts.cpuFor`, `pressureFor` | 15m, 2m | CPU and node pressure alerts. |
| `businessPodAlerts.crashLoopFor`, `notReadyFor` | 5m, 10m | Crash-loop and readiness alerts. |
| `businessPodAlerts.unavailableFor`, `degradedFor` | 2m, 10m | Workload availability alerts. |
| `dstack.alerts.unavailableFor` | 2m | Dstack controller telemetry availability. |
| `dstack.gpuHosts.staleAfterSeconds`, `unavailableFor` | 180, 5m | Expected GPU-host telemetry age and pending period. |

Kubernetes dependency rules remain configurable through the existing
`kube-prometheus-stack.customRules.<AlertName>.for` and
`kube-prometheus-stack.defaultRules` values. They are not part of the DogeOS
rule catalog below. Public status-page failure/recovery and deadline settings
remain under `statusPage.publication` and its generated runtime contract.

## Existing Grafana rules

Both Grafana and Prometheus receive the same rendered metric expressions and
pending periods; Loki log windows use the same override mechanism.
Explicit `for` overrides update existing Grafana pending periods even if edited
in the UI. Explicit query timing overrides restore that rule's chart-managed
query A with the configured timing, including when query A was customized in
the UI. Associated timing annotations update with the configured values.
Pause state, labels, notification routing and query stages B/C remain unchanged.

An explicit `groupIntervals` entry updates that Grafana group's interval;
omitting it preserves the UI interval. Other omitted fields retain the existing
three-way reconciliation behavior. Removing an override makes that field follow
the chart default again when it still matches the last applied value; subsequent
UI edits remain protected. Repeated upgrades with unchanged configuration are
idempotent. Normal rule-group defaults are not newly forced onto existing groups.

## Rule catalog

Defaults below describe the shipped chart. `for` is available for every row.
Parameters not listed in a row must use the existing shared settings above.
Snapshot freshness is per rule; when changing it, keep observation-unavailable
rules consistent with the associated business rules.

### `dogeos.account-balances` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `FeeOracleAccountBalanceLow` | `0s` | — |
| `EthDASubmitterAccountBalanceLow` | `0s` | — |
| `AccountBalanceCollectionFailed` | `5m` | `maxAgeSeconds: 180` |
| `FeeOracleBalanceMonitorMissing` | `5m` | — |
| `EthDASubmitterBalanceMonitorMissing` | `5m` | — |

### `dogeos.business-pods` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `BusinessPodContainerRestarted` | `0s` | `window: 10m` |
| `BusinessPodContainerFailed` | `0s` | `window: 10m` |
| `BusinessPodCrashLooping` | `5m` | `window: 5m` |
| `BusinessPodFailed` | `0s` | `window: 10m` |
| `BusinessPodNotReady` | `10m` | — |

### `dogeos.availability` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `BusinessDeploymentReplicasDegraded` | `10m` | — |
| `BusinessDeploymentUnavailable` | `2m` | — |
| `BusinessStatefulSetReplicasDegraded` | `10m` | — |
| `BusinessStatefulSetUnavailable` | `2m` | — |
| `BusinessDaemonSetReplicasDegraded` | `10m` | — |
| `BusinessDaemonSetUnavailable` | `2m` | — |
| `BusinessJobFailed` | `0s` | — |

### `dogeos.business` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `CubeSignerTransactionViewMismatch` | `0s` | — |
| `EthDAReorgSafetyBoundaryViolated` | `0s` | `window: 5m` |
| `AdvanceL1DeadAtHead` | `0s` | `window: 5m` |
| `AdvanceL1TerminalProofChild` | `0s` | `window: 5m` |
| `ProofWorkRetryBudgetExhausted` | `5m` | `snapshotMaxAgeSeconds: 120` |
| `L2ProofRangeTerminal` | `5m` | — |
| `WFJobStalled` | `5m` | `snapshotMaxAgeSeconds: 120` |
| `TSOSignerCommunicationFailures` | `5m` | `window: 5m` |
| `TSOSigningProgressStalled` | `15m` | `window: 15m`, `snapshotMaxAgeSeconds: 120` |
| `ProtocolReplayStopped` | `2m` | — |
| `ProtocolReorgRecoveryStalled` | `15m` | — |
| `WFIrreversibleBoundaryBlocked` | `0s` | `window: 5m` |
| `WFExternalProposalReconciliationRequired` | `0s` | `window: 5m` |
| `WFStaleSpecsPendingSweep` | `5m` | — |
| `AttestationSignerNotReady` | `2m` | — |
| `CubeSignerNotReady` | `2m` | — |
| `AttestationSignerTerminalFailure` | `0s` | `window: 5m` |
| `AttestationSignerSigningFailures` | `5m` | `window: 5m` |
| `AttestationSignerCallbackFailures` | `5m` | `window: 5m` |
| `EthDAPublicationFeeBlocked` | `5m` | `window: 5m` |
| `EthDACanonicalityAnomaly` | `5m` | `window: 5m` |
| `TSOTransactionObservationUnavailable` | `5m` | `snapshotMaxAgeSeconds: 120` |
| `WPProtocolObservationUnavailable` | `5m` | `maxAgeSeconds: 120` |

### `dogeos.disks` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `NodeDiskUsageHigh` | `5m` | — |
| `NodeDiskUsageHighCritical` | `5m` | — |
| `PVCUsageHigh` | `5m` | — |
| `PVCUsageHighCritical` | `5m` | — |
| `NodeDiskFillingUp` | `30m` | `window: 6h` |
| `NodeDiskFillingUpCritical` | `5m` | `window: 6h` |
| `NodeDiskInodesHigh` | `5m` | — |
| `NodeDiskInodesHighCritical` | `5m` | — |
| `PVCFillingUp` | `30m` | `window: 6h` |
| `PVCFillingUpCritical` | `5m` | `window: 6h` |
| `PVCInodesHigh` | `5m` | — |
| `PVCInodesHighCritical` | `5m` | — |
| `NodeFilesystemReadOnly` | `2m` | — |
| `PVCInodesFillingUp` | `1h` | `window: 6h`, `predictionSeconds: 345600` |

### `dogeos.metrics` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `EthDASubmitterNotReady` | `2m` | — |
| `EthDAPublishBacklogStalled` | `5m` | `maxAgeSeconds: 3600` |
| `EthDASubmitterFailures` | `0s` | `window: 10m` |
| `WithdrawalInboxWorkerFailures` | `5m` | — |
| `WithdrawalInboxWorkerStale` | `5m` | `maxAgeSeconds: 900` |
| `L1InterfaceNotReady` | `2m` | — |
| `FeeOracleStale` | `5m` | `maxAgeSeconds: 900` |
| `FeeOracleMetricMissing` | `5m` | — |
| `FeeOracleErrors` | `0s` | `window: 10m` |
| `TSONoRegisteredSigners` | `5m` | `snapshotMaxAgeSeconds: 120` |
| `TSOSignerMetricMissing` | `5m` | `snapshotMaxAgeSeconds: 120` |
| `DogecoinIndexerLag` | `0s` | `window: 2m` |
| `ProtocolStateWFTxNumberStalled` | `0s` | `step: 1m`, `window: 60m` |
| `ReplayHeadWFTxNumberStalled` | `0s` | `step: 1m`, `window: 60m` |
| `L2BatchHeightStalled` | `0s` | — |

### `dogeos.dstack` (default evaluation interval `30s`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `DstackMetricsUnavailable` | `2m` | — |
| `DstackRunFailures` | `0s` | `window: 10m` |

### `dogeos.fee-wallet` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `FeeWalletBalanceLow` | `0s` | — |
| `FeeWalletBalanceMetricMissing` | `10m` | — |

### `dogeos.logs` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `ServiceErrorLogs` | `0s` | `window: 5m` |
| `ServicePanicOrFatalLogs` | `0s` | `window: 5m` |

### `scroll.monitoring` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `MetricsTargetDown` | `5m` | — |

### `dogeos.resources` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `NodeMemoryUsageHigh` | `10m` | — |
| `NodeMemoryUsageHighCritical` | `5m` | — |
| `ContainerMemoryUsageHigh` | `10m` | — |
| `ContainerMemoryUsageHighCritical` | `5m` | — |
| `NodeCPUUsageHigh` | `15m` | `window: 5m` |
| `ContainerCPUUsageHigh` | `15m` | `window: 5m` |
| `ContainerCPUThrottlingHigh` | `15m` | `window: 5m` |
| `NodeMemoryPressure` | `2m` | — |
| `NodeDiskPressure` | `2m` | — |

### `dogeos.services.cubesigner-signer` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `CubeSignerSigningAttemptsFail` | `5m` | `window: 5m` |
| `CubeSignerPSBTAuthorizationRejected` | `0s` | `window: 5m` |
| `CubeSignerWorkerStale` | `5m` | `maxAgeSeconds: 300` |
| `CubeSignerWorkerFailures` | `5m` | `window: 5m` |
| `CubeSignerPendingQueueStalled` | `15m` | `window: 15m` |
| `CubeSignerProofFallbackUsed` | `0s` | `window: 5m` |
| `CubeSignerPolicyTelemetryBroken` | `0s` | `window: 5m` |
| `CubeSignerMetricsFault` | `0s` | `window: 5m` |
| `CubeSignerPolicyEvaluationMissing` | `10m` | `window: 10m` |
| `CubeSignerSigningSlow` | `5m` | `window: 10m`, `latencySeconds: 30` |

### `dogeos.services.eth-da-submitter` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `EthDAQueueValidationIncomplete` | `15m` | — |
| `EthDAParkedReplays` | `15m` | — |
| `EthDAReplaySafetyBudgetExhausted` | `0s` | `window: 5m` |
| `EthDASigningFailure` | `0s` | `window: 5m` |
| `EthDAReplacementFailure` | `5m` | `window: 5m` |
| `EthDAFeeSampleUnavailable` | `10m` | — |
| `EthDAWindowBudgetBlocked` | `15m` | `window: 5m` |
| `EthDABatchDataInvalid` | `0s` | `window: 5m` |
| `EthDALifecycleCorrelationFailure` | `0s` | `window: 5m` |
| `EthDABlobUploadRetryExhausted` | `5m` | — |
| `EthDABlobArchiveConflict` | `0s` | — |
| `EthDABlobArchiveMalformedState` | `0s` | `window: 5m` |
| `EthDABlobUploadFailures` | `10m` | `window: 5m` |
| `EthDAArchiveTaskFatal` | `2m` | — |
| `EthDASegmentationSidecarFatal` | `0s` | — |
| `EthDAArchiveAnonymousWriteAllowed` | `0s` | `window: 5m` |
| `EthDAArchiveWriteProbeInconclusive` | `0s` | `window: 5m` |

### `dogeos.services.fee-oracle` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `FeeOracleCalculationInvalid` | `0s` | — |
| `FeeOracleCalculationNotReady` | `10m` | — |
| `FeeOracleRawSampleStale` | `10m` | `maxAgeSeconds: 300` |
| `FeeOraclePriceFeedFailures` | `10m` | `window: 5m` |
| `FeeOracleBlobFeeCapped` | `15m` | — |
| `FeeOracleNonceDrift` | `10m` | — |
| `FeeOracleUnsentRequests` | `15m` | — |
| `FeeOracleTransactionsStuck` | `15m` | — |
| `FeeOracleExecutionReverted` | `0s` | `window: 5m` |
| `FeeOracleLiveRecoveryFailures` | `5m` | `window: 5m` |
| `FeeOracleLiveSubmissionFailure` | `5m` | `window: 5m` |

### `dogeos.services.l1-interface` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `L1InterfaceReplayLagging` | `15m` | — |
| `L1InterfaceReplayValidationUnavailable` | `10m` | — |
| `L1InterfaceReplayTerminalFault` | `0s` | `window: 5m` |
| `L1InterfaceSyntheticIndexIntegrityViolation` | `0s` | `window: 5m` |
| `L1InterfaceIndexerFailures` | `10m` | `window: 5m` |
| `L1InterfaceDatabaseFailures` | `5m` | `window: 5m` |
| `L1InterfaceProtocolMetricsReadFailure` | `5m` | `window: 5m` |
| `L1InterfaceRPCErrors` | `5m` | `window: 10m` |
| `L1InterfaceRPCSlow` | `5m` | `window: 10m`, `latencySeconds: 2` |

### `dogeos.services.l2-reth` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `L2RethNoPeers` | `10m` | — |
| `L2RethHeadStalled` | `0s` | `step: 1m`, `window: 15m` |
| `L2RethDerivationStalled` | `15m` | `window: 15m` |
| `L2RethPayloadValidationFailed` | `0s` | `window: 5m` |
| `L2RethDownloaderErrors` | `10m` | `window: 5m` |
| `L2RethRPCErrors` | `5m` | `window: 10m` |
| `L2RethRPCSlow` | `5m` | `window: 10m`, `latencySeconds: 2` |
| `L2RethBlobStoreFailure` | `0s` | `window: 5m` |
| `L2RethTransactionQueueLarge` | `15m` | — |
| `L2RethL1ReorgObserved` | `0s` | `window: 5m` |

### `dogeos.services.proof-coordinator` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `ProofCoordinatorNotReady` | `5m` | — |
| `ProofCoordinatorTerminalClaimFault` | `0s` | — |
| `ProofCoordinatorUploadIssuanceFailing` | `5m` | `window: 5m` |
| `ProofCoordinatorRunLoopFailing` | `5m` | — |
| `ProofCoordinatorRunLoopStale` | `5m` | `maxAgeSeconds: 900` |
| `ProofCoordinatorWorkerFencesRecurring` | `10m` | `window: 5m` |
| `ProofCoordinatorWorkerAPIErrors` | `5m` | `window: 10m` |
| `ProofCoordinatorWorkerAuthorizationFailures` | `5m` | `window: 5m` |
| `ProofCoordinatorWorkerAPISlow` | `5m` | `window: 10m`, `latencySeconds: 5` |
| `ProofMaterializationQueueStalled` | `10m` | `maxAgeSeconds: 1800`, `snapshotMaxAgeSeconds: 120` |
| `ProofVerificationQueueStalled` | `10m` | `maxAgeSeconds: 1800`, `snapshotMaxAgeSeconds: 120` |
| `ProofWorkerQueueStalled` | `10m` | `maxAgeSeconds: 3600`, `snapshotMaxAgeSeconds: 120` |
| `ProofCoordinatorObserveDegraded` | `0s` | `window: 5m` |
| `ProofCoordinatorEagerLocatorInvalid` | `0s` | `window: 5m` |
| `ProofCoordinatorEagerLocatorConflict` | `0s` | `window: 5m` |

### `dogeos.services.tso-service` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `TSOSigningCycleSlow` | `5m` | `window: 10m`, `latencySeconds: 120` |
| `TSOSignerResponseSlow` | `5m` | `window: 10m`, `latencySeconds: 60` |
| `TSORoleQuorumSlow` | `5m` | `window: 10m`, `latencySeconds: 120` |
| `TSOSigningQueueLarge` | `15m` | `snapshotMaxAgeSeconds: 120` |
| `TSOShadowforkSentinelAccepted` | `0s` | `window: 5m` |

### `dogeos.services.withdrawal-processor` (default evaluation interval `1m`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `WFFundingDataCorrupt` | `0s` | `window: 5m` |
| `WFBridgeFundingDeferred` | `15m` | `window: 5m` |
| `WFOperatorIntentHeadDrift` | `0s` | `window: 5m` |
| `WFProofGateInvariantViolation` | `0s` | `window: 5m` |
| `WFWitnessInvariantViolation` | `0s` | `window: 5m` |
| `WFProofRuntimeUnavailable` | `10m` | `window: 5m` |
| `WFWitnessArtifactMissing` | `5m` | `window: 5m` |
| `WFTSOHandoffRecoveryFailures` | `5m` | `window: 5m` |
| `WFTSOHandoffRecoveryBlocked` | `5m` | `maxAgeSeconds: 900` |
| `WFL2ProofPipelineFailing` | `5m` | — |
| `WFL2ProofPipelineStale` | `5m` | `maxAgeSeconds: 900` |
| `WFBuildQueueStalled` | `10m` | `maxAgeSeconds: 1800`, `snapshotMaxAgeSeconds: 120` |
| `WFProtocolMetricsReadFailure` | `5m` | `window: 5m` |
| `WFDatabasePoolSlow` | `5m` | `window: 10m`, `latencySeconds: 1` |

### `scroll.status-observation` (default evaluation interval `30s`)

| Alert | Default `for` | Optional query parameters and defaults |
| --- | --- | --- |
| `StatusEvaluatorUnavailable` | `3m` | `maxAgeSeconds: 120` |
| `StatusEvidenceIncomplete` | `5m` | — |
| `StatusDeliveryNeedsReconciliation` | `2m` | — |

### Generated rules

| Group | Alert | Default interval | Default `for` | Other timing settings |
| --- | --- | --- | --- | --- |
| `dogeos.quorum` | `TSO<Role>QuorumUnavailable` | 1m | 5m | `snapshotMaxAgeSeconds: 120`; role must exist in `businessAlerts.requiredSignersByRole`. |
| `dogeos.dstack-hosts` | `DstackHostTelemetryUnavailable` | 30s | 5m | Shared `dstack.gpuHosts.staleAfterSeconds`. |
| `dogeos.dstack-hosts` | `DstackHostDiskSpaceLow` | 30s | 10m | None. |
