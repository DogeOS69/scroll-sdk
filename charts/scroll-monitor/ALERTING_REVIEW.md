# DogeOS Business Alert Review

Reviewed against the local `/data/dogeos-core` checkout at HEAD `e3fed3e9f` and
this repository's production deployment configuration. This review examines code
semantics; it does not include production Prometheus observations or changes to
production notification policies.

## Retired rules

The complete `balance-cheker` group was removed from
`charts/scroll-monitor/values/production.yaml` and
`examples/values/scroll-monitor-production.yaml`:

- `ether_balance_of_L1_COMMIT_SENDER`
- `ether_balance_of_L1_FINALIZE_SENDER`
- `ether_balance_of_L1_GAS_ORACLE_SENDER`
- `ether_balance_of_L1_SCROLL_FEE_VAULT`
- `ether_balance_of_L2_GAS_ORACLE_SENDER`
- `ether_balance_of_L2_TX_FEE_VAULT`

The balance-checker dependency is commented out in `charts/scroll-sdk/Chart.yaml`
and disabled in the default values. These rules reference old, fixed Scroll
addresses. Both fee-vault rules use `< 0`, which cannot fire for normal,
nonnegative balances. The current data path uses the Ethereum DA submitter for
publication, WP inbox discovery, and the L1 Interface for serving data, as shown
in the component diagram in the dogeos-core `README.md`. Funding alerts for this
architecture need thresholds and addresses appropriate to its current accounts.

A Helm upgrade using the updated production values removes the PrometheusRule
group managed by the previous release. Remove the same group from any private
production `additionalPrometheusRules` overrides, especially when using
`--reuse-values`, which can retain old configuration. Rules previously copied in
Grafana are database resources: inspect and remove them in the UI using the names
above. The importer does not delete manually created rules by name.

## Existing rules

Retain the alerts for Ethereum DA readiness, publication backlog and failures;
inbox worker failures and staleness; L1 Interface readiness; fee oracle staleness
and errors; missing TSO signers; and Dogecoin indexer lag. Their metrics are still
exported by the current code and cover distinct failure modes. Log alerts provide
additional coverage.

The aggregation in `EthDASubmitterFailures` and `FeeOracleErrors` was also fixed.
Previously, adding several `sum(increase(...))` results could erase the entire
result when a lazily created error counter was absent. The updated expressions
select the relevant counters together and then sum them, so missing counters do
not suppress errors reported by existing counters.

Primary code references:

- `crates/eth_da_submitter/src/metrics.rs`: readiness, publication backlog,
  lifecycle failures, and reorg failures.
- `crates/withdrawal_processor/src/eth_da_inbox_worker.rs:440`: worker status
  metrics. `last_observed_at_ms` comes from the inbox synchronization
  `last_success_at_ms`; it is not simply the timestamp of the last business
  transaction.
- `crates/fee_oracle/src/monitoring/metrics.rs`: latest computation timestamp,
  RPC errors, and update errors.
- `crates/tso_core/src/metrics.rs`: registered signers and counts by role.

`eth_da_publish_canonicality_events_total` is now separated from the combined
failure alert. Its `kind` values are `reorg_suspicion` and
`provider_inconsistency`, which describe canonicality observations rather than
terminal publication failures. `EthDACanonicalityAnomaly` is a warning for
recurring observations over five minutes; reorg safety violations and prolonged
recovery have separate critical alerts. See
`crates/eth_da_submitter/src/txmgr.rs:41`.

## Accepted additions

The following recommendations are implemented under `businessAlerts.enabled`
and enabled by default. Exact per-role signer thresholds require
`businessAlerts.requiredSignersByRole` to be populated from the active policy;
runtime TSO signing-progress and communication-failure alerts are always included.
Time thresholds are starting points to calibrate against proof duration,
signing timeouts, chain confirmation policy, and actual traffic. Safety invariant
violations warrant immediate investigation; expected waiting states need duration
thresholds.

| Priority | Business failure | Suggested condition | Rationale and response |
| --- | --- | --- | --- |
| P0 | Signed transaction views disagree | `cubesigner_signer_policy_fallback_txid_mismatch_total > 0` | The unsigned txid reported by the policy differs from the gateway's actual PSBT txid. The source requires this counter to remain zero; investigate immediately. |
| P0 | A finalized L2 batch is orphaned, or a reorg exceeds the allowed bound | `increase(eth_da_submitter_l2_reorg_orphaned_finalized_batches_total[5m]) > 0` or `increase(eth_da_submitter_l2_reorg_depth_exceeds_bound_total[5m]) > 0` | These events violate an established safety boundary and deserve a direct alert before a generic failure or stalled-progress alert fires. |
| P1 | A terminally failed AdvanceL1 job blocks the WF chain | `increase(withdrawal_processor_advance_l1_dead_at_head_total[5m]) > 0`; also inspect increases in `advance_l1_built_terminal_child_total` | The code explicitly states that a failed head blocks the lane and starves AdvanceL2. Investigate the terminal cause and associated proof child. |
| P1 | Proof work exhausts its retry budget or an attached range becomes terminal | `withdrawal_processor_proof_work_stuck_item_count > 0` for 5 minutes; `withdrawal_processor_l2_proof_pipeline_terminal_ranges > 0` for 5 minutes | The first gauge reflects the business-defined retry-attempt ceiling; the second reflects currently attached terminal ranges. Preserve proof-family labels. A total count of historical `failed_terminal` rows does not establish an ongoing failure. |
| P1 | WF work remains with TSO or awaits replay too long | `withdrawal_processor_protocol_job_oldest_age_seconds{status=~"proposed_to_tso\|awaiting_replay"} > 900` for 5 minutes | Identifies signing callback, broadcast, or replay delays before the 60-minute progress alert. Preserve `action_kind` and `status`. |
| P1 | The signing quorum cannot be satisfied | `tso_core_registered_signers_by_role` stays below the configured required threshold for each role for 2–5 minutes; correlate with waiting transactions and timeout / dispatch_failed events | A nonzero total signer count can hide a missing role or insufficient signers. Derive thresholds from the active policy instead of hard-coding 1 or 3. Registration alone does not prove responsiveness; also monitor timeouts. |
| P1 | Replay has stopped or reorg recovery remains active too long | `l1_interface_protocol_replay_stopped == 1` for 2 minutes; `l1_interface_protocol_replay_active_regression_episode == 1` or `eth_da_submitter_l2_reorg_recovery_active == 1` for 15 minutes | Distinguishes brief recovery from persistent failure. Include the stop reason and calibrate the recovery timeout against the active reorg policy. |
| P1 | Canonicality checks block an irreversible boundary | An increase in `withdrawal_processor_candidate_canonicality_checks_total` with `stage=~"FinalizedCallback\|Broadcast"` and `outcome=~"stale\|retry_unavailable\|blocked"`, or an increase in `withdrawal_processor_external_proposal_reconciliation_required_total` | Reconcile source evidence, reorg history, and persisted bindings at signing or broadcast boundaries. Do not bypass checks by manually broadcasting or forcing job state. |
| P1 | A signer cannot sign or deliver callbacks | `attestation_signer_ready == 0` / `cubesigner_signer_production_policy_ready == 0` for 2–5 minutes; increases in terminal worker failures or sustained TSO callback failures | Evaluate each signer's job/instance independently so healthy signers do not mask a failing signer. |
| P2 | Fee caps persistently block publication | Publication backlog is nonzero and oldest age is increasing while `eth_da_publish_liveness_blocked_total` or `eth_da_publish_replacement_fee_cap_blocked_total` keeps increasing | Expected gas-price waiting and an inability to meet a publication deadline require different treatment. Use the configured deadline and avoid alerting on a single fee deferral. |

TSO's current exported waiting states are `proposed`, `collecting_signatures`,
and `collecting_p2pkh`; older observability prose naming `collecting_tee` or
`collecting_attestation` does not match this checkout. The implemented rule uses
the exported states and requires no completed signing cycle while work remains
pending. The configured role-count checks use the registration labels verbatim.

Source references for these additions:

- `ts-packages/cubesigner-signer/src/metrics.ts:404`: txid mismatch must remain zero.
- `crates/eth_da_submitter/src/metrics.rs:44`: reorg failures, depth bounds,
  finalized orphaning, and active recovery.
- `crates/withdrawal_processor/src/metrics_utils.rs:67`: the effect of a failed
  queue head and terminal proof children on AdvanceL2.
- `crates/withdrawal_processor/src/protocol_metrics.rs:345`: proof-work metrics
  and the meaning of the retry-attempt ceiling.
- `crates/withdrawal_processor/src/protocol_metrics.rs:50`: job age metrics;
  terminal jobs are excluded from the age query.
- `crates/tso_core/src/metrics.rs` and
  `docs/protocol/protocol-observability-metrics.md`: roles, quorums, waiting
  states, and timeouts.
- `crates/l1_interface/src/protocol_metrics.rs`: replay readiness, stopped state,
  and regression episodes.
- The Withdrawal Processor alert candidates in
  `docs/protocol/protocol-observability-metrics.md`: irreversible boundaries and
  reconciliation.
- `crates/attestation_signer/src/metrics.rs`: readiness, worker failures, and
  callbacks. Use the actual result-label values from the source; do not
  substitute `ok` for `success`.
- `crates/eth_da_submitter/src/metrics.rs:115`: publication deadlines, fee caps,
  and replacement transactions.

## Alerts that need additional metrics

- **Deposit or withdrawal SLA violations:** existing counts and amounts by status
  do not show the age of the oldest pending transaction. Add oldest-pending-age
  metrics with bounded status labels, and correlate them with confirmation
  height, queue progress, and terminal causes. A nonzero pending count alone
  does not establish an SLA violation.
- **Replay views disagree:** compare the L1 Interface and WP at the same
  canonical checkpoint. Comparing WF numbers or amounts sampled at different
  synchronization points can misclassify normal catch-up as inconsistency.

`cubesigner_signer_policy_fallback_signs_total` describes proof fallback permitted
on testnet. Assign severity according to the current network and policy; a
fallback event does not establish an unauthorized signature in every environment.

## Implemented balance monitoring

`FeeWalletBalanceLow` uses the existing
`fee_wallet_total_unredeemed_utxo_amount` gauge from the embedded Dogecoin indexer
in WP, divided by 1e8 to convert satoshis to DOGE. The query in
`crates/indexer_dogecoin/src/db/utxo.rs:521` includes non-orphaned,
unredeemed UTXOs. It does not subtract WP reservations. The initial threshold is
100 DOGE and is configurable under `balanceMonitoring.feeWallet.minimumDoge`.
The metric is already present in the WP and overview dashboards; this adds the
missing alert, not a second UTXO indexer.

Fee oracle and the Ethereum DA submitter did not export account-balance gauges.
The chart now includes a read-only JSON-RPC exporter and a ServiceMonitor.
`FeeOracleAccountBalanceLow` defaults to less than 5 native units on the fee
oracle's L2 chain. `EthDASubmitterAccountBalanceLow` defaults to less than 0.1 ETH
on the submitter's Ethereum chain. Both values use 1e18 wei per unit. Addresses,
RPC URLs, and optional expected chain IDs are injected through documented
`SCROLL_BALANCE_*` environment variables. Production configuration generators
populate the corresponding `balanceMonitoring.ethereum` fields.

Collection failures and missing/stale observations have separate alerts; the
exporter never reports an RPC failure as a zero balance. Reservation-adjusted
spendability and projected funding runway remain possible future additions.
