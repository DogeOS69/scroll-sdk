# Running a DogeOS Attestation Signer

This kit is for a partner that operates one Rust `attestation-signer` outside
the bridge operator's cluster. The signer dials out to the bridge operator's
TSO over HTTPS, so no inbound signer API, static IP, or TLS certificate is
required for the TSO connection. Monitoring has its own access rules below.
The bridge operator receives only the signer's descriptor: its
compressed attestation public key and its transport public key. It never
receives the WIF, KMS credentials, the transport key, private RPC credentials,
or the partner's trust policy.

The reference Compose image defaults to `v0.3.0-beta.6`. Update the selected
image and binary approval pins together. Preserve both signer keys and the
partner-owned trust policy; regenerate the proof-policy bundle from the
selected beta.6 proof artifacts. Follow the
[beta.6 configuration checklist](../../examples/core-beta6-configuration.md).
Use a CLI build containing [scroll-sdk-cli #77](https://github.com/DogeOS69/scroll-sdk-cli/pull/77),
including the transport-key installation fix `6e5668a` or its successor. Check
`scrollsdk signer init --help` for `--identity` and
`scrollsdk signer network-check --help` before onboarding. A previously installed
CLI package may predate this workflow.

## Workflow and handoff

| Phase | Owner | Required input | Result / next owner |
|---|---|---|---|
| Prepare | Partner | Approved image and binary pins, signer ID/network, local or KMS backend | Private deployment directory and network access |
| Phase A / Step 1 | Partner | Partner signing key and separate transport key | Public `descriptor.json` sent to the bridge operator; service stays stopped |
| Policy / Step 2 | Partner | Independently selected RPC trust domains and rotation targets | Reviewed partner-owned TOML |
| Bridge handoff | Bridge operator | All descriptors, selected keyset/threshold, canonical context and proof materials | Versioned signer policy bundle and its agreed manifest hash |
| Phase B / Step 3 | Partner | Original keys/descriptor, reviewed TOML, verified bundle | Running signer with the selected policy |
| Acceptance / Step 4 | Both | Local readiness plus TSO polling and a real request | Confirmed end-to-end signing path |

For an existing signer, start with [Operations](#operations--restart-upgrade-and-recovery)
and preserve its registered identity and volume.

The partner runs the commands in Steps 0–4 on the signer host. The bridge
operator runs only the separate bridge-handoff commands in their deployment
workspace. The bridge operator does not generate the partner's private keys.

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

- `GET /metrics` is published only at `127.0.0.1:9100` on the signer host.
- Other routes are not served on port `9100`.

Both published ports are loopback-only by default. No public signer DNS name,
TLS certificate, inbound security-group rule, or port forwarding is required.
`4040` supports local preflight; `9100` supports local monitoring. Optional
remote monitoring is configured separately on a private network; it is not a
requirement for signing.

Permit the outbound paths selected by this deployment:

- polls and signed callbacks to the bridge operator's TSO URL (HTTPS);
- HTTPS GET requests for the concrete proof-artifact URLs carried by requests;
- the partner's Dogecoin, Ethereum, and DogeOS L2 RPC source sets;
- AWS KMS and the selected credential provider when using the KMS backend.

DNS and a synchronized host clock are required. The TSO checks timestamps on
transport-signed requests; a healthy local HTTP endpoint does not prove that
these outbound requests succeed.

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

## Step 0 — prepare an independent signer workspace

Install Docker Engine with Compose v2, the compatible `scrollsdk` CLI and its
Node.js runtime, OpenSSL, `jq`, and GNU `sha256sum`. KMS onboarding also needs
AWS CLI access to the selected key. This runbook assumes Bash on Linux.

Copy the kit into a private deployment directory **outside the Git checkout**.
Do this once for a new signer; reuse that same directory for later operations.
Use a stable, unique Compose project name for this new signer; it determines
the default SQLite volume name. Existing deployments must retain their original
project name so that an upgrade does not select a new volume.

```bash
export SCROLL_SDK_DIR='/absolute/path/to/scroll-sdk'
export SIGNER_WORKDIR='/absolute/path/outside-git/partner-a-signer'
# The parent must already exist; mkdir fails if this signer workspace exists.
(umask 077; mkdir "$SIGNER_WORKDIR") && \
  cp -R "$SCROLL_SDK_DIR/partner-kit/attestation-signer/." "$SIGNER_WORKDIR/"
cd "$SIGNER_WORKDIR"
export COMPOSE_PROJECT_NAME='dogeos-partner-a'
export ATTESTATION_SIGNER_IMAGE_TAG='v0.3.0-beta.6'
```

Run all partner commands from this workspace, including the commands inside
`PARTNER-COMMANDS.md`. Keep the working directory, Compose project identity,
keys, and volume together in your deployment records. Do not copy fresh kit
placeholders over an existing deployment's env or TOML.

`COMPOSE_PROJECT_NAME` and `ATTESTATION_SIGNER_IMAGE_TAG` are Compose inputs.
Keep both set in the shell used for **all** phases and later operations, or
persist them in `docker-compose/.env` in this private workspace.
`attestation-signer.env` is a container `env_file` and
does not select the image. Record the pulled image digest and update the binary
approval pins together with any image change. For the approved beta.6 build:

| Input | Value |
|---|---|
| Image tag | `v0.3.0-beta.6` |
| `--allowed-release-version` | `0.3.0` (the embedded Cargo version, not the image tag) |
| `--allowed-git-commit` | `56007d3c413ad07f33d0e08b272004089c911f78` |

The Compose `attestation-signer.toml` and `signer-policy.env` initially contain
comments only. Leave them in place for Phase A: `--print-identity` exits without
starting the service and does not require a genesis context. Do not run `up -d`
against those placeholders.

For KMS, arrange credentials independently for both environments:

- The host AWS CLI must resolve the intended account/profile for `GetPublicKey`
  during both `signer init` passes; use `AWS_PROFILE` if needed.
- The signer container must resolve credentials granting `kms:GetPublicKey` and
  `kms:Sign` on that same key. Host profiles and shell credentials are not
  automatically passed through Compose. Configure the container's credential
  provider before the Phase A identity command; prefer an instance/workload role.

For routes through a VPN, VPC, or private RPC network, check Docker subnet
conflicts before creating the Compose network. Supply every required IPv4
route, including pod/service ranges when directly routed:

```bash
scrollsdk signer network-check --cluster-cidr '<actual-required-IPv4-CIDR>'
# Repeat --cluster-cidr for additional ranges. If choosing Compose IPAM,
# add --proposed-subnet '<candidate-non-overlapping-IPv4-CIDR>'.
```

This command reads Docker networks, including unused networks; it does not
repair routes. Resolve conflicts before onboarding. A public-only deployment
still needs the outbound connectivity listed above.

## Step 1 — create the keys, policy template, and descriptor

Run from the private signer workspace. Choose a stable DNS-label-shaped signer
id agreed with the bridge operator. [phase-a.sh](scripts/phase-a.sh) runs the
same Phase A body as the CLI-generated `PARTNER-COMMANDS.md`. It stops on the
first failure and validates the transport key before installing it. It is safe
to rerun after an interruption while retaining the original key files. If a
descriptor or runtime key already exists, a missing source key stops the block;
restore the registered key instead of generating a replacement. An existing
descriptor must match the transport key before it is installed.

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
# Replace partner-a and testnet with the ID/network agreed with the operator.
export SIGNER_ID=partner-a DOGE_NETWORK=testnet
# Local backend, with the approved beta.6 binary pins:
export SIGNER_INIT_FLAGS='--allowed-release-version 0.3.0 --allowed-git-commit 56007d3c413ad07f33d0e08b272004089c911f78'
# For an EXISTING KMS key, use this instead (replace key ID and region):
# export SIGNER_INIT_FLAGS='--backend aws-kms --kms-key-id <ECC_SECG_P256K1-key-id-or-arn> --kms-region <region> --allowed-release-version 0.3.0 --allowed-git-commit 56007d3c413ad07f33d0e08b272004089c911f78'
# For intentional first-time KMS creation only, replace --kms-key-id <...>
# with --create-key. Do not add --force when reusing an existing identity.
bash scripts/phase-a.sh
```

The output is:

```text
signer-<id>/
├── attestation-signer.env    # secret key/backend, pull delivery, binary approval pins
├── attestation-signer.toml   # partner-owned V2 source/rotation policy
├── transport.key             # SECRET transport key (0600); never send it
├── identity.json             # --print-identity output
└── descriptor.json           # public handoff: attestation + transport pubkeys
```

For KMS, the container needs `kms:Sign` and `kms:GetPublicKey` on the selected
key. For a local backend, `attestation-signer.env` contains the WIF and must be
stored with secret-file permissions. Keep `transport.key` the same way: the TSO
pins its public key, so replacing it is a coordinated configuration change.
Transport-key rotation is a separate coordinated operation: stage the new key
and descriptor outside the active workspace, retain the attestation key, agree
the TSO directory update and cutover with the bridge operator, then install the
matching key/descriptor pair. Keep the old pair available for the agreed
rollback. Do not remove a key merely to make Phase A regenerate it.

The generated `signer-*/` directories and the operator files copied into
`docker-compose/` (`attestation-signer.env`, `transport.key`) are git-ignored
in this kit; never commit them.

To regenerate files for an existing local signer, copy its current env and
partner TOML into a separate output directory under the filenames above, then
run `signer init --out <directory>` with the same id and network. Preserve the
transport key and re-export the identity with `--print-identity` before updating the descriptor.
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

## Bridge operator handoff

Send only the public descriptor, then wait for the bridge operator's reviewed
bundle. The operator follows the separate [bridge handoff procedure](docs/bridge-handoff.md)
to import descriptors, prepare the canonical context and proof materials,
select the deployment contract, and export a versioned bundle. An existing
bridge uses its upgrade procedure rather than rerunning initialization.

## Step 3 — receive and install the bridge bundle

After the bridge handoff, the partner receives the following files. Preserve
the versioned original and place a reviewed copy at `signer-policy-bundle/`
inside the private signer workspace, as expected by Phase B:

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

Review `signer-policy-bundle/PARTNER-COMMANDS.md` and `signer-policy.json`,
including the network,
genesis bridge key hash, URLs, release/proof identities, and selected mode.
Use the manifest SHA-256 supplied through the agreed handoff channel to run
the [bundle verifier](scripts/verify-bundle.sh):

```bash
export EXPECTED_MANIFEST_SHA256='<64-hex-manifest-hash-from-the-operator>'
bash scripts/verify-bundle.sh
```

It checks the manifest hash, every listed file, and your descriptor's network,
ID, attestation public key, and transport public key against the bundle.
Hashes detect modifications; the trusted handoff identifies who approved them.

A production bundle must select `active / real / enforce` and contain the
aggregate verifying key. Stop on a failed comparison; request a corrected
bundle rather than editing the manifest, context, proof pins, or policy mode
by hand.

Keep the received directory intact. After verification, run
[phase-b.sh](scripts/phase-b.sh) below. Its phase body matches the CLI-generated
`PARTNER-COMMANDS.md` and stops before startup if a step fails. It ends with the
preflight from Step 4 and defaults to `--require-production-ready`. Run either
the kit script or the generated Phase B commands; there is no need to run both.

Phase B requires both the existing `transport.key` and `descriptor.json` from
Phase A. It never creates a key. Before replacing the runtime key, it derives
the source key's compressed secp256k1 public key and compares it with the
descriptor's `transportPubkey`. Missing, malformed, or mismatched inputs stop
installation and leave the runtime key intact. Restore the registered files
on failure; changing the transport key requires the coordinated rotation above.
This local check uses Node.js, which is already required by `scrollsdk`.

```bash
# Use the same signer ID and image selection as Phase A.
export SIGNER_ID=partner-a
# Production readiness is the script default. Only for an intentionally
# selected observe bundle and compatible testnet build: export PREFLIGHT_FLAGS=''
bash scripts/phase-b.sh
```

The Compose service starts the signer with
`-c /etc/dogeos-partner/attestation-signer.toml`. Environment from the bridge
bundle overrides only bridge-owned fields.

## Step 4 — preflight and acceptance

Phase B already ends with this check. Rerun it after startup has settled or
after any image/policy change. For an intentionally selected observe bundle:

```bash
scrollsdk signer preflight --dir "signer-$SIGNER_ID"
```

For production:

```bash
scrollsdk signer preflight \
  --dir "signer-$SIGNER_ID" \
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

Local preflight checks identity and capability readiness. It does not compare
the live transport key with the TSO registry or prove artifact access; Phase B
checks the local key/descriptor pair, and the following acceptance checks close
the network path:

1. Confirm the container is running and inspect recent logs locally:
   `docker compose --project-directory docker-compose ps` and
   `docker compose --project-directory docker-compose logs --tail=100 attestation-signer`.
   Review and redact diagnostics before sharing them.
2. Ask the bridge operator to confirm successful recent polls for the registered
   signer, with no transport-authentication failures. A `GET /health` on the TSO
   alone cannot establish this.
3. Coordinate a real request for the selected topology. Verify artifact GET,
   evaluation, signed submission or a justified rejection, and receipt by TSO.
   The CLI does not fabricate an artifact object key for this check.

| Symptom | Check / next action |
|---|---|
| Phase B rejects the key or descriptor | Restore the originally registered pair; do not regenerate a key or use `--force`. |
| KMS identity export fails | Check host and container credential providers, key region, `GetPublicKey`/`Sign` permissions, and the expected signer public key. |
| `/health` succeeds but production preflight fails | Inspect `/ready` and `/policy` locally for the blocked capability; fill the reviewed source sets, rotation allowlists, binary pins, and matching verifier material. |
| Local preflight passes but TSO sees no polls | Check the TSO URL, DNS, Docker/VPN routes, ALB/policy admission, registered transport public key, and clock synchronization. |
| Artifact GET fails | Check the concrete request URL, allowed origin, proof-store read access, and the selected bundle; do not substitute the DA archive origin. |
| Image changes have no effect | Check Compose interpolation in the shell or `docker-compose/.env`; setting the image tag only in a container env file has no effect. |

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

## Operations — restart, upgrade, and recovery

Keep the partner env, transport key, descriptor, reviewed TOML, received bundle,
Compose image selection, and SQLite volume in the backup/restore plan. Take
consistent database backups with the signer stopped or using your database
backup procedure. Never run two live instances with the same attestation key.

For a routine restart from the same workspace:

```bash
docker compose --project-directory docker-compose restart attestation-signer
scrollsdk signer preflight --dir "signer-$SIGNER_ID" --require-production-ready
```

For an image or policy upgrade:

1. Agree the approved image, binary release pins, and proof-policy bundle with
   the bridge operator. Preserve the existing bridge context and both keys.
   Beta.6 guest commitments require the matching proof materials; see the
   [beta.6 checklist](../../examples/core-beta6-configuration.md).
2. Verify the new bundle as in Step 3 and retain the previous approved bundle.
   Review the partner TOML separately; an operator bundle never replaces its RPC
   trust domains or rotation targets.
3. Stop the signer and take the planned backup:
   `docker compose --project-directory docker-compose stop attestation-signer`.
   Keep the existing Compose project identity and `signer-data` volume.
4. Select the reviewed image in the shell or `docker-compose/.env`, update
   `ATTESTATION_SIGNER_ALLOWED_RELEASE_VERSION` and
   `ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT` in
   `signer-$SIGNER_ID/attestation-signer.env`, then run
   `docker compose --project-directory docker-compose pull attestation-signer`.
5. Put the verified bundle at `signer-policy-bundle/` and rerun Phase B, followed
   by Step 4 acceptance. Stopping first ensures even TOML-only changes are read
   on the next start. Use the same production readiness flags.

Do not rerun bridge initialization or use `signer init --force` for an upgrade.
Do not run `docker compose down -v`: it removes the database volume. If a new
release fails, leave the signer stopped while selecting a compatible rollback
of image, policy, and database state; do not assume a database migration is
reversible.

Attestation-key rotation is a coordinated bridge RotateKey event. Transport-key
rotation changes TSO request authentication but does not change the bridge
attestation key; follow the coordinated key/descriptor cutover in Step 1.
Neither operation is an automatic consequence of redeploying this kit.

## Monitoring reference

See [Prometheus scrape contract](docs/monitoring.md) for port access, metric
families, and aggregation guidance. Monitoring uses port 9100; it does not
require exposing the signer API on port 4040.
