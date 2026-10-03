# Fresh deployment: checks learned from the beta.5b rollout

This document records the causes and fixes from the 2026-09-29 devnet rollout.
It describes configuration generation and deployment checks, not authorization
to reset a running network. Use the selected release's native tools and matching
contracts deploy/gen-configs images. Existing chains need an explicit migration
or replacement plan.

The current examples select core `v0.3.0-beta.5c`, contracts
`deploy-dogeos-v0.3.0-rc.2`, and WP chart `0.1.22`. The issues below were observed
during the beta.5b rollout. For beta.5b-to-beta.5c in-place upgrades, follow the
[beta.5c checklist](../examples/core-beta5c-configuration.md); that transition
preserves existing databases and proof identities. The CLI's default contracts
release is `dogeos-v0.3.0-rc.2`, so its generator selects the matching
`gen-configs-dogeos-v0.3.0-rc.2`. The deploy, generator and verify tags were
checked in the registry. beta.5b requires a fresh shared database, new Bridge
and aggregation identities, and proof materials baked for that context. This
is not an in-place image upgrade of beta.5a. Reth and CUDA images have separate
release/identity checks; an application tag alone does not select a matching
CUDA worker.

## Contract owner and signing access

Contracts can transfer ownership to an address without that address signing.
A successful deployment therefore does not prove that the operator can change
parameters later. The devnet retained a historical owner address for which its
local deployment configuration contained no matching private key.

The example leaves `OWNER_ADDR` empty. `setup gen-keystore --accounts` prepares
the deployer and fills an empty owner with that address. It preserves explicitly
configured owners. Keystore preparation, genesis generation and deployment
preflight reject a zero/invalid owner and mismatched local keys. They report
external ownership as unverified when neither the owner key nor the deployer
key matches. Confirm external wallet/multisig access before deployment; the CLI
does not require copying such wallets' private keys to the deployment machine.

Changing `OWNER_ADDR` in a file does not update deployed contracts. The current
owner must sign ownership transfers on the chain where those contracts live.

## Bridge genesis sequencing output

The WF builder emits a sequencing output of **42,069,000 sat (0.42069 DOGE)**.
The supported circuit requires the genesis sequencing output to have that value.
The old 4.2069 DOGE setting allowed Bridge creation but could not prove the first
WF transition.

Both SDK and CLI setup templates use the required value. DeploymentSpec
validation, Bridge preparation, the setup broadcast step and deployment
preflight check it. Do not treat it as an adjustable funding budget. Confirm
the actual on-chain output and recomputed genesis anchors before activating WF.
A configuration correction cannot repair a previously broadcast wrong output.

## CubeSigner mode and policy binding

The gamma membership used during deployment could not change C2F HTTP egress:
that provider operation requires an organization Owner. This is a provider
permission boundary, not a CLI authorization bug.

For non-mainnet, an explicit `transport_only` choice is independent of WP's
`real/enforce` choice; WP uses Plain correctness transport. This mode does not
establish CubeSigner remote proof verification. Mainnet requirements remain in
place.

A hosted structural policy still runs in `transport_only`. After Bridge
replacement, its old namespace caused `wrong_namespace`. Rebuild and attach
the policy for the new context, then import the matching provider readback.
When receipts are present, the CLI checks attachment/key/release binding and
compares the pinned context to the current `.data/protocol_context.json` in
both modes. When attachment evidence is absent, remote policy state is reported
as unverified. No automatic policy replacement or switch to mock is performed.

## Retained L2 nodes and the DA blob source

Keeping the L2 genesis, contracts and databases across a Bridge replacement
does not mean all runtime configuration stays valid. The retained nodes used
the old `--blob.s3_url`; the new blobs existed under the new prefix. Derivation
stopped with `MissingBlob`, although WP had indexed the DA publications.

`prep-charts` derives `reth.blobS3Url` for every node from the current archive
configuration. Apply that value to every retained sequencer, bootnode and RPC
release before releasing genesis hold. Preserve each retained release's original
resource ownership identity, PVC and genesis. Audit the resulting Helm revision
and manifest rather than changing an old receipt to claim it is still current.
The devnet deployment runner now checks the installed manifest against generated
blob configuration before skipping a retained release, on every resume. A
mismatch stops deployment with the required reconciliation instructions; the
runner does not automatically adopt or overwrite the retained release.

Verify actual blob access from the cluster and advancing derivation afterwards.
A correct local YAML file or Ready pod is insufficient.

## dstack bootstrap and monitoring

Single-replica dstack supports SQLite on its retained PVC. PostgreSQL is optional.
Preserve the controller's database and encryption identity together when reusing
the controller.

On a fresh installation, `kubectl get secret ... --ignore-not-found -o json`
can succeed with empty stdout. The CLI now treats that successful empty result
as no existing Secrets and continues through server-side dry-run and publication.
Failed reads, malformed nonempty responses and mismatching existing admin,
monitoring or encryption credentials still stop publication.

Dstack native metrics and the scroll-monitor integration default to enabled in
the current chart/templates and CLI generation. Verify the monitoring Secret,
ServiceMonitor selection, Prometheus target and task/GPU metrics. A Ready
controller does not prove provider capacity or successful real proof execution.

## Generation staging and interrupted commands

Transactional generation copies inputs into a staging directory. Historical
external symlinks and large adapter/build directories caused rejection or long
copy times. Keep runtime logs and historical evidence separate. Copy the
example `.scrollsdkignore`, and add exact deployment-relative paths for unused
build/history directories. The file supports paths, not globs or negation.
Do not exclude active proof materials, receipts or their inputs; do not disable
the symlink checks or exclude the entire `.data` directory.

Avoid concurrent writers in the deployment checkout during generation. The
2026-09-30 deployment exposed a CLI bug: commit compared the live directory to
an earlier staged clone and could delete newly created operator receipts or
restore stale file contents. The CLI now fingerprints the original content and
rejects the commit if it changed during generation, preserving the operator's
files. After other writers finish, regenerate. Operational command journals
and independent policy build evidence can be excluded explicitly; selected
proof configuration inputs must remain included.

The devnet runner treats a process terminated by a signal as a failed step.
Resume must validate artifacts and checkpoint state; it must not treat a null
exit code after interruption as success or automatically broadcast Bridge setup
again.

## Before the next fresh deployment

1. Select matching core, contracts, genesis generator and real-proof materials.
2. Confirm owner signing access and verify the intended owner address.
3. Verify the fixed Bridge output amount before broadcast and on chain afterwards.
4. Bind Bridge context, proof materials, CubeSigner policy and signer receipts.
5. Regenerate DA/proof archive paths; update all retained Reth runtime values.
6. Prepare dstack Secrets and storage, and verify monitoring collection.
7. Run `setup proof-config-check` and `setup deployment-preflight`.
8. Verify actual WF/DA progress and accepted Production proofs, then exercise
   deposits and withdrawals. Pod readiness alone is not end-to-end acceptance.

The earlier beta.5b confirmation-depth increase was only a temporary mitigation:
a fixed block count does not guarantee Ethereum consensus finality. In beta.5c,
WP uses Ethereum consensus safe/finalized heads and rejects the retired
`ethereum_da.min_finality`, `ethereum_da.inbox_worker.safe_depth`, and
`ethereum_da.inbox_worker.finalized_depth` settings. The current templates omit
these fields; do not carry the old depth workaround into a fresh deployment.
