# Core beta.6 configuration and rollout

The eight core service examples and the partner attestation-signer Compose
file select `v0.3.0-beta.6`. The source tag is
`56007d3c413ad07f33d0e08b272004089c911f78`. The published signer image's OCI
revision and `GIT_COMMIT` metadata match that commit; its release version is
`0.3.0`. All nine service image tags were available when these examples were
updated. Resolve and record deployment digests before rollout.

Contracts remain the separately released rc.4 images. Reth and dstack have
independent releases; this core upgrade does not change their application tags.

## Generate beta.6 configuration before selecting the images

Use a CLI containing [scroll-sdk-cli #77](https://github.com/DogeOS69/scroll-sdk-cli/pull/77)
and a compatible, digest-pinned topology compiler. Preserve deployment secrets,
signing keys, RPC trust policies and persistent volumes while regenerating the
reviewed configuration. This checklist does not establish an automatic database
or bridge-identity migration from earlier releases.

### Signer directory and public edge

Beta.6 implements [core #1483](https://github.com/DogeOS69/dogeos-core/pull/1483).
Each WP `[[tso_signers]]` entry uses `roles = ["Correctness"]` or
`roles = ["Attestation"]`, with exactly one role. The old `role` field is
rejected. Helm `tsoSigners` uses `publicKeyOverride` and `transportPubkey`, which
render to `public_key_override` and `transport_pubkey` in native TOML.

In-cluster CubeSigner keeps `delivery = "push"` and its internal Service URI.
An external attestation signer uses `delivery = "pull"`, both public keys,
and no URI. Preserve its attestation key; create and persist its separate
transport key, export its `--print-identity` descriptor, and register the
descriptor before enabling pull delivery. Use the
[partner runbook](../partner-kit/attestation-signer/README.md).

Partners do not provide a signer endpoint or open an inbound signing port.
The reference Compose deployment binds both local preflight (`4040`) and
metrics (`9100`) to host loopback. Optional remote monitoring needs its own
explicit private-network configuration; TSO never calls those listeners.
The runtime must set `ATTESTATION_SIGNER_TSO_DELIVERY=pull` and provide its
transport key. Replacing an old image alone does not migrate push delivery;
the binary still supports the legacy push default.

The public TSO Ingress exposes exactly `/health` (Exact) and `/signer` (Prefix).
Legacy callbacks, registration, proposals, status and metrics stay on the
internal Service. Coordinate signer migration with that route change;
old external push signers cannot continue using the removed public callbacks.
The TSO and proof coordinator use separate ALBs, each with its own reviewed
certificate and optional WAF/source policy.

### Independent S3 targets

Beta.6 implements [core #1482](https://github.com/DogeOS69/dogeos-core/pull/1482).
`[s3]` is the DA archive. `[segmentation_sidecar.s3]` is the independent proof
artifact target and must match the coordinator's artifact reader, including
its key prefix. Snapshot storage remains separate from both.

Remove `DOGEOS_ETH_DA_SUBMITTER_SEGMENTATION_SIDECAR__S3` and any native
`segmentation_sidecar.s3 = true/false` setting. The boolean form fails to load;
setting it to false does not make it compatible. For an active proof topology,
`prep-charts` supplies `SEGMENTATION_SIDECAR__S3__BUCKET`, `REGION`, `KEY_PREFIX`,
`FORCE_PATH_STYLE` and the optional `ENDPOINT_URL`, all under the
`DOGEOS_ETH_DA_SUBMITTER_` prefix. Local development can instead select
`local_root`; do not configure both targets. Keep the retired
`SEGMENTATION_SIDECAR__RESTART_BACKOFF_MS` override absent.

### Metrics and network isolation

TSO, WP and CubeSigner still serve metrics on their API listener in beta.6.
[Core #1406](https://github.com/DogeOS69/dogeos-core/pull/1406) is not included:
do not enable its dedicated metrics ports or inject its environment overrides.
The external Rust attestation signer already has a separate metrics listener;
its `ATTESTATION_SIGNER_METRICS_PORT=9100` setting is supported.

The optional TSO/WP NetworkPolicies remain disabled until the deployment
configures all API, monitoring, proof-work and edge peers. With shared API
listeners, a monitoring peer can reach other API routes. When enabling the
TSO policy, set `allowFrom.edge` to the actual ALB subnet CIDRs (or ingress
proxy pod selectors); only the Ingress filters HTTP paths. Check that the CNI
enforces policy and verify signer callbacks and Prometheus scrapes afterwards.

## Update binary and proof approvals together

For the published beta.6 signer image, the binary approval fields are:

```dotenv
ATTESTATION_SIGNER_ALLOWED_RELEASE_VERSION=0.3.0
ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT=56007d3c413ad07f33d0e08b272004089c911f78
```

Use `enforce` for production. `observe` requires a build with the
`testnet-observe` feature and is testnet-only. `production_enforce` and
`staging_scaffold` are retired. Neither supported mode removes the canonical
protocol-context requirement: generate identities before genesis and start
services after receiving the reviewed policy bundle.

[Core #1486](https://github.com/DogeOS69/dogeos-core/pull/1486) records refreshed
beta.6 bridge and aggregation guest identities. Do not reuse the historical
beta.5b-to-beta.5c advice that proof identities are unchanged. Regenerate and
cross-check the selected bridge/prover artifacts, compiler identity inputs,
signer policy bundle and CubeSigner bindings from the beta.6 bake manifest.
The recursive verification key remaining unchanged does not make the guest
program commitments interchangeable. An existing bridge needs its separately
reviewed identity/upgrade procedure before activating those new commitments.

## Validation before rollout

- Render the generated WP signer TOML and check roles, delivery and both keys.
- Validate native configuration using the selected beta.6 images, including
  compiler-generated WP/PC proof configuration and any init-container tools.
- Check DA archive and proof-artifact access separately, including their IAM
  roles, key prefixes and permitted anonymous reads.
- Confirm an external signer can poll and submit signed results, while public
  registration, proposal and unprefixed callback routes remain inaccessible.
- Confirm internal metrics scraping and proof-work callbacks after any policy
  activation, then follow deposit, proving and withdrawal progress.

Helm rendering and chart tests do not substitute for this deployment check.
