# Core service example review

Reviewed against dogeos-core commit
`e3fed3e9f246db191dd5073bb7c87932b4c9f2eb` and scroll-sdk base
`f34bcef54a676bf12c08d69fd21c904f62e5e0f4`.
This review changes only `examples/`; it does not update chart defaults,
`charts/*/values/production.yaml`, CLI code, or service binaries.

These are **input templates**, not ready-to-install deployment artifacts.
Image tags, `<TODO>` deployment facts, native proof configuration, genesis
material and signer policy identities must be resolved before installation.
Do not replace missing security identities with dummy values to pass readiness.

## Findings and changes

| Service | Finding and action | Source of truth in dogeos-core |
| --- | --- | --- |
| l1-interface | Made the Secrets Manager region explicit instead of inheriting `us-west-2`. Existing replay/DA fields and shared-file mounts match the current config. Port 9091 is valid: the control listener uses the health port plus one. | `crates/l1_interface/src/config.rs`, `src/startup.rs` |
| withdrawal-processor | Split the proof-work bearer token from the ordinary RPC/signer-key ExternalSecret. They have different ownership and can use different AWS regions. Removed the obsolete PostgreSQL instructions: the binary constructs a SQLite connection pool. Exposed the existing 5-second/5-minute broadcast backoff defaults in native TOML. | `crates/withdrawal_processor/src/config.rs`, `src/startup.rs::setup_db` |
| eth-da-submitter | No confirmed missing required field found in this review. Preserve the KMS-only profile, genesis/context mounts, optional DA archive and segmentation settings. The configured finalization depth is an explicit deployment policy, not changed to the source default by this review. | `crates/eth_da_submitter/src/service_config.rs` |
| fee-oracle | Made inherited service ports, health/readiness/startup probes, SQLite PVC and monitoring explicit, and added service-account selection. Normal startup remains chart-owned. Made the local-key secret region explicit. KMS remains selected through managed signer setup, not by copying deployment-specific key ARNs into the generic example. | `crates/fee_oracle/src/config.rs` and HTTP health/metrics handlers |
| proof-coordinator | Removed duplicate `DOGEOS_PROOF_COORDINATOR_*` environment entries: Figment gives them precedence over generated TOML, including a different coordinator ID and stale S3 settings. Made the proof secret region explicit. Keep native configuration compiler-owned. | `crates/proof_coordinator/src/main.rs::ServiceConfig` and config loader |
| tso-service | Made the service port, `/health` probes and `/metrics` endpoint explicit; made the existing external ingress decision explicit. Normal startup remains image-owned. Made the signing-journal PVC type and retention explicit. Preserve the accepted-signature journal on uninstall. | `crates/tso_service/src/main.rs::Args`, `create_routes`, `crates/tso_core/src/tso/` |
| cubesigner-signer | Made both secret regions explicit. Required protocol context, session, transport limits and production-policy identity inputs already exist. Empty production-policy identities intentionally prevent readiness until real policy material is provided. | `ts-packages/cubesigner-signer/src/server.ts`, `productionPolicy.ts` |

`http://l2-rpc:8545` is **not** evidence of an obsolete l2geth dependency:
`values/l2-reth-rpc-production.yaml` explicitly retains `service.main.fullname:
l2-rpc`. The fee-oracle and eth-da-submitter URLs therefore stay unchanged.

## Operator steps and configuration ownership

### Startup command decision

Normal startup belongs to the image or service chart. Environment values only
override `command`/`args` when that deployment requires different behavior;
they do not repeat these fields just to document startup. This is a deliberate
exception to the older blanket command/args duplication rule in
`docs/production-values.md`, not a Kubernetes prohibition on overrides.

This follow-up removes only the redundant command/args added to fee-oracle and
TSO in the initial review. Fee-oracle inherits `/usr/local/bin/fee_oracle` from
its chart; TSO leaves both container fields unset and uses image defaults.
Other services' existing launch settings are unchanged. No chart defaults or
chart-local production files are modified by this example-only follow-up.

References: [Kubernetes command/args semantics](https://kubernetes.io/docs/tasks/inject-data-application/define-command-argument-container/),
[Helm default and user-supplied values](https://helm.sh/docs/topics/charts/#templates-and-values),
and [Bitnami Redis optional command/args overrides](https://github.com/bitnami/charts/blob/main/bitnami/redis/values.yaml).

### Deployment steps

1. Use the CLI deployment procedure linked from [README.md](README.md), including
   bridge initialization, protocol context and managed signer setup. Fill image
   tags and deployment endpoints through that procedure. The minimal native
   ProofCoordinator example is not a complete standalone daemon config.
2. Ordinary ExternalSecrets need the region containing their Secrets Manager
   entries. `setup push-secrets` writes the selected AWS region into ordinary
   service secret mappings; verify the generated values. If managing secrets
   outside that command, set `externalSecrets.<name>.secretRegion` yourself.
   The Secrets Manager region is independent of a signer's KMS key region.
3. `setup proof-aws-init` records the proof secret name/region and workload IRSA
   identities in `.data/proof-aws.json`. `setup prep-charts` projects these facts
   into both proof-coordinator and `withdrawal-proof-token`. Do not put the
   proof-work token into the ordinary withdrawal-processor service secret.
4. For fee-oracle KMS mode, `prep-charts` selects `aws_kms`, supplies the key
   ID/region/expected address, creates the IRSA service account, and removes both
   the local-key environment selector and its Secret references. The local
   example deliberately uses the namespace's default service account; it does
   not reference an account that has not been created.
5. Keep compiler-owned proof settings in the proof intent/materials workflow.
   `prep-charts` renders WP/PC native TOML, genesis sequencer transaction,
   activation and signer transport together. Do not add environment overrides
   for partial proof tables or manually fill verifier/materializer identities.
6. Before installing TSO, check the generated ingress hostname, TLS and access
   controls, and ensure external signers can reach it. `/health` is the binary's
   current probe route; it does not certify end-to-end signer availability.
7. The fee-oracle database and TSO signing journal PVCs now explicitly use
   `retain: true`. An uninstall leaves them behind. Review and recover retained
   state when reinstalling; never treat journal deletion as a routine restart.

The L1 replay cold-start issue under investigation is a binary concern, not a
missing example switch. This review does not add an init-container workaround,
disable validation or fabricate replay data. Nor does it claim the separate
chart-local production overlays are synchronized with these examples.

## Local validation

From the scroll-sdk root, run:

```bash
python3 .github/scripts/validate_production_values.py
git diff --check
```

The existing production-values check covers l1-interface,
withdrawal-processor, eth-da-submitter, proof-coordinator and cubesigner-signer;
it does not cover fee-oracle or TSO and does not render Helm manifests. Local
Helm rendering for all seven services was also checked during this review,
but no additional test script is retained in examples. These checks do not
resolve Secrets Manager/KMS, launch binaries, or prove runtime readiness.
Normal generated-artifact validation
(`scrollsdk setup proof-config-check --deployment-dir .`) and deployment
health checks are still required.
