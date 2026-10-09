# Core beta.5c configuration and in-place upgrade

This historical checklist describes `v0.3.0-beta.5c`. The current examples
select beta.6; use the [beta.6 checklist](core-beta6-configuration.md) for that
release. The identity and state-retention statements below apply only to the
beta.5b-to-beta.5c transition.

Release instructions:
[dogeos-core #1284](https://github.com/DogeOS69/dogeos-core/issues/1284#issuecomment-5904045604).
This checklist covers **beta.5b → beta.5c**. It does not extend the upgrade
guarantee to older releases.

## 1. Remove retired WP finality fields before updating the image

The native example `withdrawal-processor/WithdrawalProcessor.toml` omits:

- `ethereum_da.min_finality`
- `ethereum_da.inbox_worker.safe_depth`
- `ethereum_da.inbox_worker.finalized_depth`

Beta.5c rejects these keys at startup, even when their values look reasonable.
For an existing installation, remove them from its native TOML and rendered
Helm ConfigMap. Also remove corresponding environment overrides from values,
ConfigMaps and Secrets, including `DOGEOS_WITHDRAWAL_ETHEREUM_DA__MIN_FINALITY`
and any inbox-worker safe/finalized depth overrides.

Retain `ingest_depth` and the deployment's scan cursor, start block, batcher
allowlist and other observer settings. `ingest_depth` controls scanning; it
does not configure consensus finality. The new observer reads Ethereum's
`safe` and `finalized` block tags. Proving can start at `safe`, while AdvanceL2
construction waits for `finalized`. The selected Ethereum RPC must support
both tags.

## 2. Update application images and binary approval pins

Update the eight core services: withdrawal-processor, proof-coordinator,
eth-da-submitter, l1-interface, tso-service, cubesigner-signer, fee-oracle and
eager-materializer. Update external attestation signers as part of the same
rollout. Pin deployment images by digest after resolving the release tag.

Generated WP/PC values may have proof-runtime init containers. Update their
core images alongside the main containers. If these containers check CPU-tool
SHA-256 values, verify those values against the new image. The beta.5b and
beta.5c images inspected during the devnet rollout had identical chunk and
batch CPU-tool checksums; no checksum change was needed there. Keep generated
proof material, mounts and identity pins intact.

For attestation signers configured with build approval pins, use:

```dotenv
ATTESTATION_SIGNER_ALLOWED_RELEASE_VERSION=0.3.0
ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT=3e4ecac76fd21abb8034e5327c9de1d21e3bfad3
```

The release version is the binary's Cargo version, not the image tag. These
values approve the host binary; they are separate from proof-program and
CubeSigner pins. Preserve the existing signer key/backend, policy bundle,
canonical protocol context and database volume. Update any explicit Compose
`ATTESTATION_SIGNER_IMAGE_TAG` override as well as the build approval values.

## 3. Keep eager proving configuration compiler-owned

The coordinator defaults `[prover_api].eager_chunk_proving` to `true`. It acts
only with real generation, the real chunk materializer, chunk segmentation
and the required chunk verifier identity. The selected topology must also
provide the eager materializer's chunk locator and segmentation sidecar index.

Use a beta.5c-compatible, digest-pinned topology compiler when generating new
configuration. Its `proof_coordinator.tuning.eager_chunk_proving` input defaults
to true. The compiler renders an explicit false for real materialization
without the eager materializer, or when that input is set to false. Omission
of the output key can therefore be intentional; it uses the service default.

The native PC example keeps only stable process defaults. It does not add a
partial `[prover_api]` table or copy generated verifier/materializer blocks
from a deployed network. Check the compiler-generated output and the startup
message `eager chunk proving is effective`. A no-op message explains unmet
prerequisites; changing only the boolean cannot supply them.

## 4. Verify the genesis guard and retain compatible state

WP checks that the genesis sequencer output pays **42,069,000 sat** to the
configured sequencer public key's P2PKH address. The setup-defaults example
already sets `sequencer_target_amount = 42_069_000`. For an existing deployment,
check the recorded transaction and recipient; changing a template cannot alter
an existing genesis transaction.

For the supported beta.5b-to-beta.5c transition:

- Reuse the existing databases, PVCs and genesis. The release has no baseline
  database migration change.
- Keep Bridge and batch-aggregation proof identities, the CUDA Worker image
  and CubeSigner proof pins. No re-bake is required.
- Keep separately released Reth settings and images unless another approved
  rollout explicitly changes them.

## 5. Render, roll out and verify progress

These examples are inputs for deployment generation; they are not complete
values for an existing installation. Preserve its generated proof mounts,
credentials, instance annotations and PVC template metadata. Review the
generated diff and render the selected chart versions before applying them.
Retain any deployment-specific Helm post-renderer that supplies immutable
StatefulSet/PVC identity metadata.

Roll out services one at a time, checking the actual running image and
readiness. Then verify:

1. WP reports Ethereum `safe_head` and `finalized_head` successfully.
2. The coordinator selects the real verifier and reports effective eager
   proving when the chosen topology supports it.
3. New production proof receipts are accepted after the rollout, and canonical
   WF advances. Confirm both AdvanceL1 and AdvanceL2 when eligible work exists.
4. DA continues ingesting L2 and publishes according to the configured
   batching policy. Waiting for the target blob count or its deadline is not
   itself a submission failure.

A single-batch AdvanceL2 can complete without creating a new tag-5 range
aggregation task; testing aggregation scheduling priority requires eligible
aggregation work. Do not reset queues or weaken proof mode to force acceptance.

Local example checks:

```bash
python3 .github/scripts/validate_production_values.py
python3 .github/scripts/validate_charts.py
```

Parse the edited native TOML and render the affected Helm charts as well.
Example validation does not replace runtime progress checks on the selected
network.
