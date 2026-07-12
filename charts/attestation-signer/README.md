# attestation-signer

Helm chart for the DogeOS correctness attestation signer.

## Configuration model

The attestation-signer binary supports `-c/--config` with precedence
`defaults < TOML < env/CLI`. This chart exposes typed `attestationSigner.*`
values and renders the non-secret application configuration into
`/etc/dogeos/attestation-signer.toml`.

The mounted ConfigMap contains the generated application TOML plus the two
operator-owned policy documents that the binary reads as separate files:

- `verifier-registry.toml`
- `source-set.toml`

Secrets never live in chart values or ConfigMaps. Local WIF and KMS key ID
values are injected with Kubernetes `secretKeyRef` environment overrides.
Production release identity also remains environment-based because it is a
runtime/build attestation boundary rather than application file config.

## Security profiles

### `staging-local`

For development and staging only:

- policy mode: `staging_scaffold`
- signer backend: `local`
- `allow_unimplemented_checks=true`
- signing WIF loaded from `attestationSigner.local.wifSecretRef`

```yaml
attestationSigner:
  profile: staging-local
  network: testnet
  tso:
    url: http://tso-service:3000
    callbackPhase: attestation
  local:
    wifSecretRef:
      name: attestation-signer-0-env
      key: ATTESTATION_SIGNER_WIF
  proofArtifact:
    fetchMode: disabled
```

### `production-kms`

Fail-closed production profile:

- policy mode: `production_enforce`
- signer backend: `aws_kms`
- `allow_unimplemented_checks=false`
- KMS key ID rendered from non-secret `attestationSigner.kms.keyId`
- verifier registry and source-set policy mounted from the config ConfigMap
- release identity and production policy values required explicitly

Start from `values/production.yaml`, replace every `<TODO>`, pin the image,
configure the KMS key ID, and configure an IRSA role scoped to
`kms:Sign` and `kms:GetPublicKey` on exactly one key.

### `staging-kms`

For shared staging environments that need KMS-backed keys while production
policy checks are still under rollout:

- policy mode: `staging_scaffold`
- signer backend: `aws_kms`
- KMS key ID rendered from non-secret `attestationSigner.kms.keyId`
- KMS region and expected compressed signer ID rendered into TOML
- no production release-policy requirements

## Important values

| Value | Description |
| --- | --- |
| `attestationSigner.profile` | `staging-local`, `staging-kms`, or `production-kms`; selects policy and backend together. |
| `attestationSigner.network` | `dogecoin`, `mainnet`, `testnet`, or `regtest`. |
| `attestationSigner.port` | Container and Service HTTP port. |
| `attestationSigner.tso` | TSO URL and callback phase. |
| `attestationSigner.database.path` | Durable SQLite ledger path on the data PVC. |
| `attestationSigner.local.wifSecretRef` | WIF Secret reference for staging-local. |
| `attestationSigner.kms` | KMS Secret reference, region, expected signer ID, and optional endpoint. |
| `attestationSigner.productionPolicy` | Fail-closed production protocol and policy identity. |
| `attestationSigner.envelopePolicy` | Evidence-envelope allowlists and bounds. |
| `attestationSigner.proofArtifact` | Artifact fetch mode and bounded maximum size. |
| `attestationSigner.releasePolicy` | Allowed binary/build identity for production. |

The JSON schema rejects unknown profiles, invalid network/callback/fetch modes,
out-of-range ports and replicas, missing profile-specific Secret references,
and missing production policy fields.

## Upgrading from 0.1.x

Version 0.2.0 replaces CLI-owned raw TOML with chart-owned rendering from typed
values. Legacy values containing a directly supplied
`configMaps.config.data.attestation-signer.toml` fail rendering intentionally.
Regenerate values with a current `scrollsdk` and select an explicit
`attestationSigner.profile`; the chart then renders the application TOML and
mounts verifier/source-set TOML files in the same ConfigMap.

## Rollouts and storage

The chart deploys one replica per release because each signer owns a durable
single-writer SQLite signing ledger. Deploy multiple attestation keys as
separate releases (`attestation-signer-0`, `attestation-signer-1`, etc.).

## Persistence sizing

Each release owns an independent PVC containing the original and signed PSBTs,
evidence/bundle/envelope audit JSON, policy decisions, and the anti-double-sign
ledger. Proof artifact bytes are fetched and verified out of band; they are not
stored in SQLite. The database currently has no automatic retention or vacuum
policy, and deleting request rows would also delete linked ledger rows, so the
default is `5Gi` per signer rather than `1Gi`. Use at least `10Gi` per signer for
sustained workloads near 50-100 requests/day, keep 20-25% free for SQLite WAL,
and alert before PVC usage reaches 85%.

The common chart adds configuration checksums to Pod annotations. Policy
ConfigMap changes therefore trigger a controlled StatefulSet rollout. The
SQLite PVC is retained by default.
