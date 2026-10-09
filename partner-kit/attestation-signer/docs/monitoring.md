# Prometheus scrape contract

The reference Compose deployment sets
`ATTESTATION_SIGNER_METRICS_PORT=9100` and publishes only
`127.0.0.1:9100:9100`. A monitoring process on the signer host can scrape
`http://127.0.0.1:9100/metrics`. No remotely accessible port is required for
the signer or for local monitoring.

If an authorized Prometheus server must scrape over a private network or VPN,
explicitly replace the existing metrics port mapping with
`<private-monitoring-IP>:9100:9100` in the deployment's Compose file and restrict
access to that server. Replace the mapping rather than adding a second one.
Keep `127.0.0.1:4040:4040` unchanged for local preflight. Do not publish either
listener to all interfaces merely to operate the signer. These are optional
monitoring network rules, separate from the signer's outbound TSO connection.

The exposition provides these metric families:

- `attestation_signer_ready{mode}`
- `attestation_signer_intake_requests_total{result,kind}`
- `attestation_signer_worker_ticks_total{result,kind}`
- `attestation_signer_worker_active_rows_loaded`
- `attestation_signer_worker_rows_total{starting_status,result,kind}`
- `attestation_signer_worker_failures_total{kind,terminal}`
- `attestation_signer_queue_rows{status}`
- `attestation_signer_queue_oldest_age_seconds{status}`
- `attestation_signer_worker_tick_duration_seconds{result}`
- `attestation_signer_worker_last_success_timestamp_seconds`
- `attestation_signer_queue_wait_seconds{capability}`
- `attestation_signer_row_evaluation_seconds{capability,decision}`
- `attestation_signer_tso_submit_seconds{capability,result}`
- `attestation_signer_policy_decisions_total{mode,classification,reason_code}`
- `attestation_signer_signing_attempts_total{result}`
- `attestation_signer_tso_callbacks_total{path,result}`
- `attestation_signer_release_outcomes_total{result}`
- `attestation_signer_artifact_fetch_total{transition,result,cache}`
- `attestation_signer_artifact_fetch_latency_ms{transition,result}`
- `attestation_signer_artifact_bytes{transition}`
- `attestation_signer_witness_decode_total{transition,result}`
- `attestation_signer_rotation_replay_total{transition,result}`
- `attestation_signer_rotation_replay_latency_ms{transition}`
- `attestation_signer_rotation_result_total{transition,result}`
- `attestation_signer_rotation_ready{transition}`
- `attestation_signer_advance_l1_replay_total{result}`
- `attestation_signer_advance_l1_replay_latency_ms`
- `attestation_signer_advance_l1_result_total{result}`
- `attestation_signer_advance_l2_replay_total{result}`
- `attestation_signer_advance_l2_replay_latency_ms`
- `attestation_signer_advance_l2_result_total{result}`
- `attestation_signer_source_set_evaluations_total{fact,posture,outcome}`
- `attestation_signer_source_verdicts_total{fact,verdict}`
- `attestation_signer_source_set_evaluation_latency_ms{fact,posture,outcome}`

Latency and artifact-size observations are Prometheus summaries. Consume their
exported `quantile` series per signer instance; quantiles from multiple signer
instances cannot be averaged or aggregated into a valid fleet-wide quantile.
Use `_sum / _count` when a per-instance average is required.

All labels use bounded domains. Request IDs, public keys, trust-domain IDs,
RPC and TSO URLs, hashes and roots, PSBT data, and raw error strings are
deliberately excluded from labels. The interface is pull-only: the signer does
not push metrics, remote-write them, or send them to an OTLP collector.
