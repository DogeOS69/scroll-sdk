# Core beta.5a configuration

The eight core service values examples select `v0.3.0-beta.5a`: withdrawal-processor,
proof-coordinator, eager-materializer, l1-interface, eth-da-submitter, fee-oracle,
tso-service and cubesigner-signer. Keep matching init-container images aligned
with the application image when generating deployment values. This selection
does not change the separately released Reth or CUDA worker images.

## Native withdrawal-processor configuration

- Omit `wf_withdrawal_parity_v1` entirely. Withdrawal fulfillment is unconditional;
  setting the removed key, even to false, fails startup because unknown fields
  are rejected. The example does not generate a compatibility override.
- `max_withdrawal_outputs_per_tx` remains 256 in the example. It reserves
  AdvanceL1 output space and paces AdvanceL1/rotation withdrawal fulfillment.
  AdvanceL2's output bound comes from transaction size, not this setting.
- The example uses 60 Dogecoin confirmations, the recommended mainnet depth.
  Mainnet with strict L1 validation rejects depths below 50. Testnet and
  shadowfork deployments can explicitly configure their own depth; do not use
  that exception as a mainnet sizing recommendation. Other strict-validation
  settings remain operator decisions.

Keep native configuration in `withdrawal-processor/WithdrawalProcessor.toml`.
Run `scrollsdk setup prep-charts` with the selected native topology compiler
and this deployment's inputs to generate proof configuration, identities and
Helm values. These examples intentionally contain no deployed credentials,
wallet addresses, bucket names or generated proof identities.

The release has no database migrations relative to beta.5 and supports an
in-place image update after the removed field is deleted. A database reset is
not required. See the [author's rollout instructions](https://github.com/DogeOS69/dogeos-core/issues/1284#issuecomment-5851335607).
Before applying complete generated values to an existing installation, review
the diff against its live proof mounts, seed resources and native configuration.

## Temporary WP host-memory sizing

The WP production example now limits memory to **4 GiB**. This follows the
[author's catch-up recommendation](https://github.com/DogeOS69/dogeos-core/issues/1284#issuecomment-5852435864)
after a real-proof deployment reached its 2 GiB limit and was OOMKilled. CPU
and memory requests are unchanged. Check available node capacity and observe
peak working set, container restarts and backlog size during catch-up.

Four GiB is a temporary operational allowance, not a demonstrated bound or a
fix for growing per-pass memory. Revisit it after the backlog drains. Preserve
the peak working set and last completed proof-pipeline pass before any OOM.
[Core #1313](https://github.com/DogeOS69/dogeos-core/issues/1313) tracks profiling
and bounding memory growth.

Host memory and CUDA VRAM are separate. Raising the WP Kubernetes memory limit
does not resolve a CUDA worker's GPU allocation failure. Select worker images
and GPU capacity from the matching proof release and measured workload; repeated
failure of one statement requires diagnosis rather than cycling instances.

## Monitoring acceptance

Watch these event counters, together with successful scrapes and WF progress:

```promql
withdrawal_processor_wf_lane_liveness_total{outcome="dead_candidate_retry"}
advance_l1_schedule_decision_total{reason="reorg_settling"}
```

An absent event series does not prove a measured zero. A steadily increasing
`dead_candidate_retry` count calls for investigation of repeated candidate
failure. Compare committed WF batch height with DA finalized batch height and
verify new Production proofs; Pod readiness alone does not establish progress.

beta.5a has a known public queue observation bug: its collector expects
`tip + 1 - confirmations` while its Dogecoin indexer reaches
`tip - confirmations`. The [author confirmed the mismatch](https://github.com/DogeOS69/dogeos-core/issues/1284#issuecomment-5852325521);
[core #1312](https://github.com/DogeOS69/dogeos-core/pull/1312) contains the fix.
Do not work around it by weakening confirmation depth or reporting an invalid
snapshot as healthy. A future image containing the fix must be validated before
accepting these metrics. Public queue health requires a valid, fresh snapshot,
complete count/age data and a live scrape target.

## Local checks

Run the repository's production-values validation after editing the examples:

```bash
python3 .github/scripts/validate_production_values.py
```

Review the generated deployment diff and render the applicable Helm charts
before applying to a cluster. Runtime acceptance also needs real WF, DA and
proof progress on the target deployment.
