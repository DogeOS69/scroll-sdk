# Running a DogeOS Attestation Signer

This kit is for a partner that operates one Rust `attestation-signer` outside
the bridge operator's cluster. The signer dials out to the bridge operator's
TSO over HTTPS, so the partner opens nothing inbound and needs no static IP or
certificate. The bridge operator receives only the signer's descriptor: its
compressed attestation public key and its transport public key. It never
receives the WIF, KMS credentials, the transport key, private RPC credentials,
or the partner's trust policy.

The reference Compose image defaults to `v0.3.0-beta.6`. Update the selected
image and binary approval pins together. Preserve both signer keys and the
partner-owned trust policy; regenerate the proof-policy bundle from the
selected beta.6 proof artifacts. Follow the
[beta.6 configuration checklist](../../examples/core-beta6-configuration.md).
Use a CLI release containing scroll-sdk-cli #77 for the pull-signer workflow.

The current dogeos-core contract is `attestation_evidence_v2`:

```text
partner creates signing key + transport key + descriptor
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

Nothing is exposed to the TSO. With pull delivery the signer long-polls the TSO
(`/signer/poll`) and returns signatures or rejections on `/signer/*`; every
request carries a signature from the transport key, which the TSO pins.

Locally (loopback in the reference Compose file) it serves three status
surfaces for preflight:

- `GET /health` reports process health, public key, network, and build identity.
- `GET /ready` is HTTP 503 in `enforce` until every production V2
  capability can serve.
- `GET /policy` reports the active V2 contract, capability rows, and blocks.

Prometheus uses a separate metrics-only listener:

- `GET /metrics` is exposed on port `9100` by the reference Compose file.
- Other routes are not served on port `9100`.

The signer makes two outbound connections:

- polls and signed callbacks to the bridge operator's TSO URL (HTTPS);
- HTTPS GET requests for the concrete proof-artifact URLs carried by requests.

## Prometheus scrape contract

The reference Compose deployment sets
`ATTESTATION_SIGNER_METRICS_PORT=9100` and publishes host port `9100`. Configure
an authorized Prometheus server to pull `GET /metrics` from that port. Keep the
API port (`4040`) on loopback; do not expose it merely to enable monitoring. The partner is responsible for private routing, firewall or
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

Latency and artifact-size observations are Prometheus summaries. Consume their
exported `quantile` series per signer instance; quantiles from multiple signer
instances cannot be averaged or aggregated into a valid fleet-wide quantile.
Use `_sum / _count` when a per-instance average is required.

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

## Step 1 — create the keys, policy template, and descriptor

Run from this directory. Choose a stable DNS-label-shaped signer id agreed with
the bridge operator. The block below is the same Phase A that scrollsdk
generates in `PARTNER-COMMANDS.md`. It is one `set -eu` subshell, so it stops
at the first failing step: a corrupt transport key or a failed `openssl` never
reaches the identity step, and the runtime key is left as it was. It is safe
to rerun after an interruption.

1. `signer init` creates the signing key and env once (pull delivery and the
   transport key file are selected there).
2. The signing env and policy are copied next to the Compose file, and the
   transport key is created locally only if absent, validated as a whole and
   installed into `docker-compose/`.
3. `--print-identity` runs through the same Compose service and mounts the
   runtime uses, with the real backend, network and transport key.
4. The second `signer init` only reads the existing signer (it re-checks the
   KMS public key) and writes `descriptor.json`; it never reprovisions.

```bash
export SIGNER_ID=<agreed-signer-id> DOGE_NETWORK=testnet
# Local WIF backend: leave SIGNER_INIT_FLAGS unset. AWS KMS backend
# (recommended for production) and production release pins:
# export SIGNER_INIT_FLAGS='--backend aws-kms --kms-key-id <ECC_SECG_P256K1-key-id-or-arn> --kms-region <region> --allowed-release-version <approved-cargo-version> --allowed-git-commit <approved-full-40-character-git-sha>'
(
  set -eu
  # 1. Signing key and env, once (a rerun keeps them). The env selects pull
  #    delivery and the transport key file.
  [ -e "signer-$SIGNER_ID/attestation-signer.env" ] \
    || scrollsdk signer init --id "$SIGNER_ID" --network "$DOGE_NETWORK" ${SIGNER_INIT_FLAGS:-}
  # 2. Signing env and policy next to the Compose file, then the transport key:
  #    created locally only if absent, validated, installed.
  cp "signer-$SIGNER_ID/attestation-signer.env" "signer-$SIGNER_ID/attestation-signer.toml" docker-compose/
  chmod 600 docker-compose/attestation-signer.env
  (
    set -eu
    key="signer-$SIGNER_ID/transport.key"
    # Create only when absent: write a temp file, then link it in exclusively.
    if [ ! -e "$key" ]; then
      umask 077
      openssl rand -hex 32 > "$key.new"
      ln "$key.new" "$key"
      rm -f "$key.new"
    fi
    # The whole file must be exactly 64 lowercase hex characters and a newline.
    if [ "$(wc -c < "$key")" -ne 65 ] || [ "$(tail -c 1 "$key" | wc -l)" -ne 1 ] \
      || ! head -c 64 "$key" | grep -Eqx '[0-9a-f]{64}'; then
      echo "$key must be exactly one line of 64 hex characters; restore it (rotation is a separate step)" >&2
      exit 1
    fi
    # Install atomically: the runtime key is replaced only by a validated copy.
    cp "$key" docker-compose/transport.key.new
    chmod 600 docker-compose/transport.key.new
    mv -f docker-compose/transport.key.new docker-compose/transport.key
  )
  # 3. Print the identity with the real backend, network and transport key
  #    (the same Compose service and mounts the runtime uses).
  docker compose --project-directory docker-compose run --rm --no-deps -T attestation-signer \
    -c /etc/dogeos-partner/attestation-signer.toml --print-identity > "signer-$SIGNER_ID/identity.json.new"
  mv "signer-$SIGNER_ID/identity.json.new" "signer-$SIGNER_ID/identity.json"
  # 4. Wrap it into descriptor.json (read-only for the existing signer).
  scrollsdk signer init --id "$SIGNER_ID" --network "$DOGE_NETWORK" --identity "signer-$SIGNER_ID/identity.json"
)
```

The output is:

```text
signer-<id>/
├── attestation-signer.env    # secret key/backend, pull delivery, image pins
├── attestation-signer.toml   # partner-owned V2 source/rotation policy
├── transport.key             # SECRET transport key (0600); never send it
├── identity.json             # --print-identity output
└── descriptor.json           # public handoff: attestation + transport pubkeys
```

For KMS, the container needs `kms:Sign` and `kms:GetPublicKey` on the selected
key. For a local backend, `attestation-signer.env` contains the WIF and must be
stored with secret-file permissions. Keep `transport.key` the same way: the TSO
pins its public key, so replacing it is a coordinated configuration change.
Rotating it is an explicit step, never a rerun: move the old file aside,
create a new key, send the new descriptor, and switch the runtime key only after
the bridge operator has updated the TSO signer directory.

The generated `signer-*/` directories and the operator files copied into
`docker-compose/` (`attestation-signer.env`, `transport.key`) are git-ignored
in this kit; never commit them.

To regenerate files for an existing local signer, copy its current env and
partner TOML into a separate output directory under the filenames above, then
run `signer init --out <directory>` with the same id and network. Preserve the transport key and re-export the
identity with `--print-identity` before updating the descriptor.
Without `--force`, the CLI reuses the WIF and preserves the partner TOML. Check
that the resulting descriptor has the original public key before installing
anything. Do not use `--force` for this workflow: it creates a new local key.
Keep the existing bridge policy bundle, release approvals, and database volume.
For an existing KMS signer, generate into a new output directory using its
original `--kms-key-id` and `--kms-region`, without `--create-key`. Pass the
currently approved release/commit pins, compare the resulting public key with
the existing descriptor, and copy the reviewed partner TOML over the new
template. This only reads the existing KMS public key; it does not create or
rotate a KMS key.

Send only `descriptor.json` to the bridge operator. The public key enters the
bridge keyset at genesis, so review it carefully. Do not send the signer
configuration files or `transport.key`.

## Step 2 — prepare partner-owned production policy

Open `signer-<id>/attestation-signer.toml`. Its examples use the exact current
dogeos-core section names. In production, configure all of the following:

1. `[advance_l1_policy.terminal_anchor_sources]` with independently trusted
   Dogecoin sources. Production quorum needs at least two trust domains.
2. `[advance_l2_policy.ethereum_sources]` for Ethereum canonicality/finality.
3. `[advance_l2_policy.l2_sources]` for the exact L2 state root.
4. `[rotation_policy].allowed_next_bridge_script_hashes`.
5. `[rotation_policy].allowed_next_sequencer_signers`.

All three source sets must use `posture = "quorum"` with
`required_agreement >= 2` and enough independently trusted source domains to
meet that threshold in `enforce` mode. `explicit_single_source` is accepted
only in `observe` mode; using it in `enforce` prevents startup.
Both rotation allowlists must contain reviewed, approved targets. Do not
invent targets merely to satisfy readiness.

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
`signer-policy-bundle/PARTNER-COMMANDS.md`. Its Phase B is the block below:
one `set -eu` subshell, so the signer is configured and started only if every
step succeeds (a bad transport key never reaches `up -d`). It ends with the
preflight from Step 4; `PREFLIGHT_FLAGS` selects the production check.

```bash
export SIGNER_ID=<agreed-signer-id>
# Production bundles (enforce):
# export PREFLIGHT_FLAGS='--require-production-ready'
(
  set -eu
  cp "signer-$SIGNER_ID/attestation-signer.env" "signer-$SIGNER_ID/attestation-signer.toml" docker-compose/
  chmod 600 docker-compose/attestation-signer.env
  (
    set -eu
    key="signer-$SIGNER_ID/transport.key"
    # Create only when absent: write a temp file, then link it in exclusively.
    if [ ! -e "$key" ]; then
      umask 077
      openssl rand -hex 32 > "$key.new"
      ln "$key.new" "$key"
      rm -f "$key.new"
    fi
    # The whole file must be exactly 64 lowercase hex characters and a newline.
    if [ "$(wc -c < "$key")" -ne 65 ] || [ "$(tail -c 1 "$key" | wc -l)" -ne 1 ] \
      || ! head -c 64 "$key" | grep -Eqx '[0-9a-f]{64}'; then
      echo "$key must be exactly one line of 64 hex characters; restore it (rotation is a separate step)" >&2
      exit 1
    fi
    # Install atomically: the runtime key is replaced only by a validated copy.
    cp "$key" docker-compose/transport.key.new
    chmod 600 docker-compose/transport.key.new
    mv -f docker-compose/transport.key.new docker-compose/transport.key
  )
  mkdir -p docker-compose/policy
  cp signer-policy-bundle/signer-policy.env docker-compose/signer-policy.env
  cp signer-policy-bundle/protocol_context.json docker-compose/policy/protocol_context.json
  # Production bundles also carry the aggregate verifying key.
  if [ -e signer-policy-bundle/advance-l2-agg-verifying-key.bin ]; then
    cp signer-policy-bundle/advance-l2-agg-verifying-key.bin docker-compose/policy/advance-l2-agg-verifying-key.bin
  fi
  docker compose --project-directory docker-compose config --quiet
  docker compose --project-directory docker-compose up -d
  scrollsdk signer preflight --dir "signer-$SIGNER_ID" ${PREFLIGHT_FLAGS:-}
)
```

The Compose service starts the signer with
`-c /etc/dogeos-partner/attestation-signer.toml`. Environment from the bridge
bundle overrides only bridge-owned fields.

## Step 4 — preflight

Phase B already ends with this check. Rerun it any time. For disabled or mock mode:

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
- `policy_mode=enforce` and contract
  `attestation_evidence_v2`;
- scaffold/unimplemented bypasses disabled;
- public key and network equal `/health` and the descriptor;
- exactly one serving row for each of `advance_l1`, `advance_l2`,
  `rotate_key`, and `rotate_sequencer_signer`;
- `production_v2_ready=true` on both `/ready` and `/policy`.

Recovery capability rows are intentionally visible but do not count toward
production readiness.

Mock uses `observe` with deterministic, non-cryptographic proof bytes. Observe
requires a signer binary built with the `testnet-observe` feature and is
rejected on mainnet. AdvanceL1 never bypass-signs; eligible AdvanceL2/rotation
checks may use dogeos-core's audited observe bypass. It is not production-safe.

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
- The bridge operator sees each signer's last poll in TSO metrics; a signer that
  stops polling becomes unavailable on the same schedule as an unreachable one.
- The CLI does not invent an artifact key for reachability checks. A real
  withdrawal request is authoritative for signer artifact GET and TSO poll and
  callback.
