# Temporary Pre-Tsuki Direct-Sign Recovery

This document reconciles scroll-sdk deployment surfaces with dogeos-core PR
#847 / Issue #843. The capability is a bounded, testnet-only migration tool for
already-persisted pre-Tsuki work. It is not a fourth proof mode, is disabled by
default, and is scheduled for removal before the final v0.3.0 release.

The authoritative operational and completion semantics remain in dogeos-core's
`docs/pre-tsuki-direct-sign-runbook.md`. This document only describes how the
same reviewed operator pin reaches scroll-sdk-managed deployment artifacts.

## Canonical intent

Declare the reviewed Tsuki-boundary L2 batch height in DeploymentSpec:

```yaml
proofSystem:
  mode: disabled
  preTsukiDirectSign:
    maxEndBatchHeight: 6863 # example only; use the reviewed deployment boundary
```

For a deployment without DeploymentSpec, use the equivalent doge-config TOML:

```toml
[proofSystem]
mode = "disabled"

[proofSystem.preTsukiDirectSign]
maxEndBatchHeight = 6863 # example only
```

Do not maintain both sources independently. The CLI rejects disagreement.

## Generated projections

`scrollsdk setup prep-charts` projects the one intent to:

| Trust boundary | Generated configuration |
|---|---|
| Withdrawal Processor | `[proof_system.pre_tsuki_direct_sign] max_end_batch_height = <pin>` in native `WithdrawalProcessor.toml` |
| TSO | `TSO_PRE_TSUKI_DIRECT_SIGN_MAX_END_BATCH_HEIGHT=<pin>` in Helm values |
| Deployment contract | `preTsukiDirectSign.maxEndBatchHeight` in schema-v3 `.data/proof-deployment.json` |

`scrollsdk setup export-signer-policy` projects the same intent to the
partner-operated Rust signer bundle as:

```dotenv
ATTESTATION_SIGNER_PRE_TSUKI_DIRECT_SIGN_MAX_END_BATCH_HEIGHT=<pin>
```

This value belongs in the deployment policy bundle's `signer-policy.env`, not
the operator-owned key/backend `attestation-signer.env`. Keeping it out of the
operator file ensures a generated retirement bundle actually removes it.

CubeSigner is correctness/TEE-only and receives no direct-sign attestation
configuration.

The CLI rejects a missing/non-positive/u32-overflow pin, any proof mode other
than `disabled`, and Dogecoin mainnet. `setup proof-config-check --strict`
rejects WP/TSO projection mismatch and disagreement between current intent and
the deployment contract.

## Rollout and retirement

Follow dogeos-core's exact ordering and completion predicate. In summary:

1. Record immutable image identities, the reviewed pin, rendered configuration
   checksums, and state backups.
2. Apply the same pin to TSO, then every Rust attestation signer, then WP.
3. Before enabling WP, restrict TSO `/propose` ingress to WP while preserving
   signer callback access, as required by the core trust model.
4. Verify the signer `/policy` capability rows; the temporary capabilities are
   intentionally excluded from `/ready`.
5. Let the recovery pipeline run and evaluate the authoritative completion
   predicate while quiescent until it is stable.
6. Retire in reverse order: remove the WP posture, then the Rust signer pin,
   then the TSO pin, then the temporary `/propose` restriction.
7. Only after retirement may the deployment switch to `mock` or `production`
   proof mode.

Removing the intent and rerunning `setup prep-charts` removes both WP and TSO
projections and records their absence in a new deployment contract. Export and
apply a fresh signer policy bundle to remove the signer projection. Never edit
only one of the three trust-boundary configurations.
