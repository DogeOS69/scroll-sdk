# Running a DogeOS Attestation Signer

This kit is for a partner that operates one Rust `attestation-signer` outside
the bridge operator's cluster. The bridge operator receives only the signer's
HTTPS endpoint and compressed public key. It never receives the WIF, KMS
credentials, private RPC credentials, or the partner's trust policy.

The current dogeos-core contract is `attestation_evidence_v2`:

```text
partner creates key + descriptor
            ↓
bridge operator fixes keyset and generates canonical protocol context
            ↓
bridge operator exports selected proof-mode bundle
            ↓
partner installs bundle + partner-owned TOML, starts signer, runs preflight
```

Unlike older signer builds, the current binary requires canonical protocol
context in every mode. Therefore the pre-genesis step creates the identity and
descriptor but does not start the service. Runtime preflight happens after the
bridge operator returns the generated policy bundle.

## What the signer exposes

TSO needs one inbound application API and three status surfaces:

- `POST /sign` receives signing requests.
- `GET /health` reports process health, public key, network, and build identity.
- `GET /ready` is HTTP 503 in `production_enforce` until every production V2
  capability can serve.
- `GET /policy` reports the active V2 contract, capability rows, and blocks.

Prometheus uses a separate metrics-only listener:

- `GET /metrics` is exposed on port `9100` by the reference Compose file.
- Other routes, including `POST /sign`, are not served on port `9100`.

The signer makes two outbound connections:

- callbacks to the bridge operator's TSO URL;
- HTTPS GET requests for the concrete proof-artifact URLs carried by requests.

Use a private network/VPN or an IP-allowlisted TLS proxy. There is no
application-layer authentication on the signer↔TSO HTTP path today.

## Prometheus scrape contract

The reference Compose deployment sets
`ATTESTATION_SIGNER_METRICS_PORT=9100` and publishes host port `9100`. Configure
an authorized Prometheus server to pull `GET /metrics` from that port. Keep the
signing port (`4040`) on the TSO-only network; do not expose it merely to enable
monitoring. The partner is responsible for private routing, firewall or
allowlist rules between Prometheus and the metrics port.

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

All labels use bounded domains. Request IDs, public keys, trust-domain IDs,
RPC and TSO URLs, hashes and roots, PSBT data, and raw error strings are
deliberately excluded from labels. The interface is pull-only: the signer does
not push metrics, remote-write them, or send them to an OTLP collector.

## Ownership boundary

The bridge operator's generated bundle owns facts derived from bridge/proof
configuration:

- `protocol_context.json`;
- selected mode and TSO URL in `signer-policy.env`;
- accepted proof-artifact HTTPS origin;
- in production, the aggregate verifying key plus direct-batch and
  L2-range-aggregation program commitments;
- a machine-readable summary and SHA-256 manifest.

The partner-owned `attestation-signer.toml` owns operational trust choices:

- Dogecoin terminal-anchor source set;
- Ethereum canonicality/finality source set;
- DogeOS L2 state-root source set;
- allowed next bridge script hashes;
- allowed next sequencer signers.

`scrollsdk signer init` creates that TOML once and never overwrites it, even
with `--force`. The bridge bundle must never contain a common source-set file:
different partners are expected to use independently operated sources.

## Step 1 — create the key, policy template, and descriptor

Run from this directory. Choose a stable DNS-label-shaped signer id agreed with
the bridge operator.

Local WIF backend:

```bash
scrollsdk signer init \
  --id <agreed-signer-id> \
  --network testnet \
  --endpoint https://signer.your-org.example:4040
```

AWS KMS backend (recommended for production):

```bash
scrollsdk signer init \
  --id <agreed-signer-id> \
  --network testnet \
  --endpoint https://signer.your-org.example:4040 \
  --backend aws-kms \
  --kms-key-id <ECC_SECG_P256K1-key-id-or-arn> \
  --kms-region <region> \
  --allowed-release-version <approved-cargo-version> \
  --allowed-git-commit <approved-full-40-character-git-sha>
```

The output is:

```text
signer-<id>/
├── attestation-signer.env    # secret key/backend and image approval pins
├── attestation-signer.toml   # partner-owned V2 source/rotation policy
└── descriptor.json           # public endpoint + key handoff
```

For KMS, the container needs `kms:Sign` and `kms:GetPublicKey` on the selected
key. For a local backend, `attestation-signer.env` contains the WIF and must be
stored with secret-file permissions.

Send only `descriptor.json` to the bridge operator. The public key enters the
bridge keyset at genesis, so review it carefully. Do not send either signer
configuration file.

## Step 2 — prepare partner-owned production policy

Open `signer-<id>/attestation-signer.toml`. Its examples use the exact current
dogeos-core section names. In production, configure all of the following:

1. `[advance_l1_policy.terminal_anchor_sources]` with independently trusted
   Dogecoin sources. Production quorum needs at least two trust domains.
2. `[advance_l2_policy.ethereum_sources]` for Ethereum canonicality/finality.
3. `[advance_l2_policy.l2_sources]` for the exact L2 state root. A deliberate
   one-source deployment must use `explicit_single_source`; quorum is better
   when independent sources exist.
4. `[rotation_policy].allowed_next_bridge_script_hashes`.
5. `[rotation_policy].allowed_next_sequencer_signers`.

RPC credentials may be kept in the operator secret env where supported. Never
put credentials in URLs. dogeos-core rejects URL userinfo/query/fragment and
strictly validates source thresholds, unique trust domains, timeouts, and
canonical hex.

Missing optional policy does not silently become production-safe. The signer
may start, but production `/ready` stays HTTP 503 and the relevant capability
reports a named block.

## Step 3 — receive and install the bridge bundle

After descriptor import and bridge initialization, the bridge operator sends:

```text
signer-policy-bundle/
├── PARTNER-COMMANDS.md
├── protocol_context.json
├── signer-policy.env
├── signer-policy.json
├── signer-policy-manifest.json
└── advance-l2-agg-verifying-key.bin  # production only
```

The obsolete `verifier-registry.toml`, generic `source-set.toml`, proof-triple
allowlist, and TEE signer allowlist are not part of V2. A bundle containing
those instead of the files above targets an old dogeos-core release.

Keep the received directory intact and execute its generated
`signer-policy-bundle/PARTNER-COMMANDS.md`. The equivalent file placement is:

```bash
export SIGNER_ID=<agreed-signer-id>

cp "signer-$SIGNER_ID/attestation-signer.env" docker-compose/
cp "signer-$SIGNER_ID/attestation-signer.toml" docker-compose/
chmod 600 docker-compose/attestation-signer.env
mkdir -p docker-compose/policy
cp signer-policy-bundle/signer-policy.env docker-compose/signer-policy.env
cp signer-policy-bundle/protocol_context.json docker-compose/policy/protocol_context.json

# Production bundle only:
cp signer-policy-bundle/advance-l2-agg-verifying-key.bin docker-compose/policy/

docker compose --project-directory docker-compose config --quiet
docker compose --project-directory docker-compose up -d
```

The Compose service starts the signer with
`-c /etc/dogeos-partner/attestation-signer.toml`. Environment from the bridge
bundle overrides only bridge-owned fields.

## Step 4 — preflight

For disabled or mock mode:

```bash
scrollsdk signer preflight --dir signer-<agreed-signer-id>
```

For production:

```bash
scrollsdk signer preflight \
  --dir signer-<agreed-signer-id> \
  --require-production-ready
```

The production check requires:

- `/ready` HTTP 200;
- `policy_mode=production_enforce` and contract
  `attestation_evidence_v2`;
- scaffold/unimplemented bypasses disabled;
- public key and network equal `/health` and the descriptor;
- exactly one serving row for each of `advance_l1`, `advance_l2`,
  `rotate_key`, and `rotate_sequencer_signer`;
- `production_v2_ready=true` on both `/ready` and `/policy`.

Recovery capability rows are intentionally visible but do not count toward
production readiness.

Mock uses `staging_scaffold` with deterministic, non-cryptographic proof bytes.
AdvanceL1 never bypass-signs; incomplete eligible AdvanceL2/rotation policy may
use dogeos-core's explicit audited scaffold bypass. It is not production-safe.

## Proof artifacts versus release files

Proof artifacts are produced continuously as batches progress. The signer
fetches their per-request HTTPS URLs from shared artifact storage. The
aggregate verifying key and other proof release material are static,
release-versioned files; the production bundle copies the signer-required
aggregate key and binds it by SHA-256.

## Current production closure boundary

The Rust attestation-signer now implements the V2 AdvanceL1, AdvanceL2, and
rotation evaluators; the old statement that its STARK verifier is globally
`NotImplemented` is no longer correct.

The separate CubeSigner/TEE production policy is still not cryptographically
closed in the current dogeos-core release: exact deployed verifier-program and
AggVK provenance, namespace/policy evidence, restart ambiguity, and final E2E
evidence remain tracked implementation gaps. Generating this Rust-signer bundle
does not waive that boundary. Keep asset-bearing production activation blocked
until the selected dogeos-core release closes those recorded gaps.

## Temporary pre-Tsuki recovery

An Issue #843 testnet-only bundle may contain
`ATTESTATION_SIGNER_PRE_TSUKI_DIRECT_SIGN_MAX_END_BATCH_HEIGHT`. Never add or
change it by hand. WP, TSO, and every Rust signer must use the same reviewed
height. The two direct-sign rows are visible in `/policy` but excluded from
`production_v2_ready`.

Retire the posture only after the authoritative completion predicate is stable,
in this order: WP, Rust signer, TSO; then enable proof mode. See
[`docs/pre-tsuki-direct-sign-recovery.md`](../../docs/pre-tsuki-direct-sign-recovery.md).

## Operations

- Persist the SQLite volume; it contains the signer audit/request database.
- Never operate two live instances with the same signing key.
- Do not rotate the key unilaterally; RotateKey is a coordinated bridge event.
- The bridge operator should independently probe `/health` from the actual TSO
  network. A successful laptop check does not prove that route.
- The CLI does not invent an artifact key for reachability checks. A real
  withdrawal request is authoritative for signer artifact GET and TSO callback.
