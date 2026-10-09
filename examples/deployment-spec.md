# Prepare from a complete DeploymentSpec

Use [deployment-spec.example.yaml](deployment-spec.example.yaml) together with
[deployment.env.example](deployment.env.example). The spec selects deployment
intent for `scrollsdk setup plan` / `setup apply`.
Operator inputs, automatically generated artifacts and external approval handoffs
are described below. Enforcing-policy evidence remains a separate integration
boundary; see the completion limits before using this starter.

## Selected scope

This example prepares a **testnet deployment** with the beta.6 production Bridge
outpoint flow, two Reth sequencers, two bootnodes, AWS KMS signing identities for
eth-da-submitter, fee-oracle, both L2 sequencers and the Dogecoin Bridge sequencer,
and a SQLite dstack controller
with imported Vast.ai credentials. P2P nodekeys remain local. Both the
attestation and recovery cohorts use 2-of-3; Bridge funding requires 6 confirmations.
It selects `active / real / enforce` proofs. The approved release producer
generates this deployment's Bridge-bound compiler identity; no hand-written
compiler identity or mock proof hashes are accepted. This is a testnet policy;
CubeSigner remains explicitly `transport_only`.

Select only `dogecoin.network`: `mainnet`, `testnet` or `regtest`. The CLI derives
the fixed L1 chain ID (`1`, `111111` or `5555555`) for every generated consumer.
`network.l1ChainId` is not a spec input; remove it from older specs.
`network.l2ChainId` is still operator-selected. The Ethereum DA chain ID is
separate: `ethereumDa.chainId` is `11155111` for Sepolia.

The beta.6 eth-da-submitter still consumes `ethereumDa.confirmationDepth` and
`finalizationDepth`. The example explicitly selects `1` and `64`, matching core's
submitter `.env.example`. These depths use Ethereum tip height minus transaction
inclusion height, controlling confirmation and later settlement finalization.
They do not replace the DA readers' `safe`/`finalized` checks. The Rust fallback
for omitted finalization depth is `1`; `64` is the explicit policy selected here.

Bridge fees match `config.toml.example`: 1 DOGE per deposit, 0.1 DOGE per
withdrawal and a 1 DOGE minimum withdrawal amount. `depositFeeSats` uses Dogecoin's
8 decimals, so 1 DOGE is `100000000` sats. The CLI converts it to
`contracts.DEPOSIT_FEE = "1000000000000000000"` in L2 wei (18 decimals); withdrawal
and minimum withdrawal values already use L2 wei.

Core service images are beta.6, with `v0.3.0-beta.6-kms` for withdrawal-processor.
That image supports KMS sequencing; its fee wallet still uses a local key.
The CLI genesis default is contracts rc.5, and
fresh-chain defaults are 30,000,000 gas, 2-second blocks and a 1,400 ms build window.
Empty blocks are disabled by default (`reth.sequencer.allowEmptyBlocks: false`);
the block interval does not require producing a block when there is no eligible work.
Reth has its own release lineage; its tag must be selected explicitly. Plan
resolves the committed HEAD of `--sdk-dir` and freezes its full commit in
the saved intent. Working-tree edits do not affect template selection. Advanced
users may override it with `templates.sdkRevision: <full-commit>`; normal specs
omit `templates`. Apply keeps the frozen revision even if the checkout advances.

Use a CLI build containing `setup plan` and `setup apply`. Check `scrollsdk setup
plan --help` before starting. AWS, Kubernetes and the external RPCs
referenced here already exist. PostgreSQL is needed when deploying Blockscout,
or when explicitly selecting PostgreSQL for dstack. The SQLite example does not
select Blockscout database initialization; PostgreSQL can be deferred while
preparing the chain. Apply creates the five declared AWS KMS signing identities
and their IAM/IRSA resources using the configured region, EKS cluster and
namespace. It also creates/reconciles the declared proof bucket, its workload
roles and token Secret, and publishes the real proof program bundle. Secret
upload into Kubernetes and blob bucket creation are not selected. Plan itself
does not provision resources;
generated configuration does not establish runtime access.

## Prepare the private inputs

Create an operator-owned directory outside both source repositories. Keep the
future `deployment/` directory absent or empty for `plan`:

```text
private-instance/
  deployment-spec.yaml
  deployment.env
  inputs/                     # other external inputs, when selected
  deployment/                 # created by setup plan
```

From the scroll-sdk checkout, copy the examples into that private directory:

```bash
install -m 600 examples/deployment-spec.example.yaml /private/instance/deployment-spec.yaml
install -m 600 examples/deployment.env.example /private/instance/deployment.env
```

Create `/private/instance` first, using your own writable location with private
permissions. Edit the copies. Every `REPLACE_WITH_*`, `TODO_*`, `*.example.invalid`
and marked numeric value is an operator input. These are deliberately unusable
placeholders, not working identities or credentials.

| Input | Required action |
| --- | --- |
| Infrastructure, endpoints and domains | Select the existing cluster/namespace, PostgreSQL host/user and Dogecoin testnet RPC. Sepolia execution/beacon URLs use the CLI defaults; override them if needed. Set `frontend.baseDomain` once. The proof URL derives from its `proofCoordinator` subdomain and dstack ingress defaults to `dstack.<baseDomain>`; explicit endpoint overrides remain supported. |
| Environment file | Fill the six base spec variables, `DOGECOIN_FEE_WALLET_KEY` and `VASTAI_API_KEY`. The KMS/SQLite example does not use `DOGECOIN_SEQUENCER_KEY`, `SEQUENCER_SIGNING_KEY` or `DSTACK_DATABASE_URL`. |
| Owner and deployment salt | Select the owner address and a unique deployment salt. Apply creates the deployer account unless the spec explicitly imports one. |
| Reth image tags | Replace all three `TODO_APPROVED_RETH_TAG` values with the reviewed compatible Reth release. |
| Bridge public keys | Select the CubeSigner role ID (and key ID for a multi-key role); plan queries the TEE public key. Apply obtains the Bridge sequencer public key from KMS and derives the fee-wallet public key from its environment WIF. Supply three recovery public keys using [Prepare the Bridge keys](#prepare-the-bridge-keys). |
| Bridge policy | Replace `timelock: 100` with a reviewed future Dogecoin block height below 500,000,000. Attestation and recovery each select 2-of-3; funding requires 6 confirmations. Review these policies and funding budgets. The initial sequencer amount remains exactly 42,069,000 satoshis. |
| Ethereum anchor | Keep `ethereumAnchor.blockTag: finalized` for a fresh deployment. Apply resolves and saves the finalized block hash/height with transaction index 0 before DA starts. An explicit historical `blockNumber` and `transactionIndex` pair is available for reviewed overrides; do not combine it with `blockTag`. |
| Attestation identities | Fill `attestationSigners` from approved Governance records: one `name`, `attestationPubkey` and `transportPubkey` per signer. Selected names must match `bridge.initialAttestationKeyset.signerIds`. No descriptor files or publicly reachable signer endpoints are required. |
| Proof software release | Keep `preparation.proofRelease.version: v0.3.0-beta.6` or select the reviewed compatible version. Plan retrieves the official release manifest and checksum, validates them and freezes image pins. No manifest file or SHA256 is an operator input. If the release is missing, plan reports a core release dependency before resource creation. |
| Proof resources | The example selects `preparation.proofAws.action: create`; apply provisions/reconciles the proof bucket, IAM/IRSA roles and token Secret, then writes `proof-aws.json`. For existing resources use `action: reuse` with `existing-public-s3` or `existing-gateway`. Optional role names and Secret name select nonstandard resources; ARNs are queried. Reuse makes no AWS changes and verifies account, bucket region, EKS trust and current Secret metadata. Access/readback still needs validation during publication. |
| dstack credentials | Set `VASTAI_API_KEY` in the private environment file. `vastaiApiKeyEnv` names that variable; no extra key file is needed. The alternative `vastaiApiKeyFile` remains supported; choose only one. Importing credentials does not rent GPUs. |
| Blob/proof buckets | Select two distinct bucket names; the blob bucket already exists and apply prepares the proof bucket as selected by `proofAws`. Configure proof storage only at `proofArtifacts.s3`, and blob storage at `ethereumDa.blobArchive.s3`. The CLI derives Coordinator and Topology bucket/region/prefix/endpoint settings; repeating those fields in the spec is rejected. Proof region defaults to `infrastructure.aws.region`; set `proofArtifacts.s3.region` only for a different region. For AWS S3, omit `publicBaseUrl` to derive `https://<bucket>.s3.<region>.amazonaws.com`. Set it for a different HTTP read origin, such as a CDN or gateway; it must serve the same blob objects. Keep `keyPrefix` separate. Deriving a URL does not configure public-read permissions. Separate prefixes in one bucket are insufficient. |

PostgreSQL settings can remain unconfigured while Blockscout is deferred and
dstack uses SQLite. Do not select `preparation.databases: [blockscout]` until its
database is ready. If the spec still references `$ENV:DB_ADMIN_PASSWORD`, keep
that variable defined in the env file: generic environment resolution still
requires it, even though no database connection is made at this stage. This does
not make the generated Blockscout configuration ready to deploy.

`frontend.externalUrls.l1Rpc` and `l1Explorer` are projected into frontend
configuration; they are not unused fields. They can remain illustrative while
testing chain preparation, but must be reviewed before enabling the frontend.
`l1Rpc` also feeds contract verification when that optional configuration is
selected. Neither field replaces `dogecoin.externalRpc.url` for Bridge RPC calls.

### Configure proof storage once

```yaml
proofArtifacts:
  s3:
    bucket: replace-with-unique-proof-bucket
    keyPrefix: dogeos-devnet/proofs
    # region: us-east-1  # optional; defaults to infrastructure.aws.region
```

Coordinator, Withdrawal Processor, topology compiler and proof AWS preparation
consume this one store. The generated service configurations still contain their
required storage fields; the source spec does not repeat them. Do not set
`proofCoordinator.artifactStore.bucket/region/keyPrefix/endpointUrl/forcePathStyle`,
`proofTopology.active.artifactStore.bucket/region/keyPrefix/endpointUrl/forcePathStyle`,
or `proofTopology.deployment.artifactKeyPrefix`. These are rejected even if they
match the canonical store. For nonstandard S3 services, set `endpointUrl` and
`forcePathStyle` once under `proofArtifacts.s3`. Normal AWS S3 endpoint and access
style are derived automatically. Consumer tuning such as `maxReadBodyBytes`
remains separate from storage coordinates.

External file paths in `preparation` are relative to the **output deployment
directory**. With the layout above, `../inputs/...` resolves to the correct sibling
directory. Absolute paths are also supported. Plan needs read access to the official
GitHub proof release; optional `GH_TOKEN` / `GITHUB_TOKEN` supports private
repository access and authenticated API limits. Keep tokens outside source control.
Descriptor files may
arrive later; apply waits when a declared file is missing. Missing environment
credentials also produce an actionable wait.

## Select the CubeSigner TEE identity

Set `signing.cubesigner.identity.roleId` to the existing role ID. If the role has
more than one key, also select `keyId`. Authenticate the `cs` CLI before planning.
Plan queries role membership and key metadata, converts the public key to valid
compressed SEC1 secp256k1 bytes and freezes both the role metadata and Bridge TEE
public key. Apply reuses that resolved identity without querying CubeSigner again.
No private key is exported, and no session is copied into the spec.

The normal example omits `bridge.teePubkey` and `signing.cubesigner.roles`. An
explicit public key remains an advanced input; if combined with an identity
lookup it must match the queried key. Explicit full `roles` and `identity` are
mutually exclusive. Creating the hosted key and authorizing runtime signing
sessions remain CubeSigner owner operations.

## Prepare the Bridge keys

The production spec selects a KMS key for the Dogecoin Bridge sequencer and
imports an independently managed local fee-wallet key. These are distinct from
the L2 sequencers' AWS KMS keys and are not derived from a helper seed.
Decide who controls each key before running plan:

| Identity | How to obtain the public input | Private material |
| --- | --- | --- |
| Dogecoin Bridge sequencer | Set `preparation.bridge.production.sequencerKms: {action: create}`; apply reads and pins its public key. | The private key stays in AWS KMS. |
| Dogecoin fee wallet | Apply derives and pins its public key and funding address; no spec fields are needed. | Put its compressed WIF in `DOGECOIN_FEE_WALLET_KEY` in the private environment file. |
| Three recovery signers | Each custodian creates or selects their own key and supplies only its compressed public key. Fill the three `recoveryPublicKeys` entries in the agreed order. | Each custodian retains their private key and backup; do not collect these into the deployment env file. |
| CubeSigner TEE | Provide the role/key reference described above; plan resolves the public key. | The hosted private key stays in CubeSigner. |
| Three attestation signers | Copy each approved Governance record's paired public keys into `attestationSigners`. | Each partner retains their signer credentials. These are separate from the recovery keys. |

With `sequencerKms: {action: create}`, apply creates or reuses
`alias/dogeos/<metadata.name>/<eksClusterName>/bridge-sequencer`. It adds signing
permissions to the existing proof AWS withdrawal role, preserving proof access,
and derives the sequencer funding address from the pinned KMS public key.
For an existing key use `sequencerKms: {action: reuse, keyId: alias/EXISTING_KEY}`;
its existing workload role must already permit `kms:GetPublicKey` and `kms:Sign`.
The role defaults to the proof AWS withdrawal role; `roleArn` selects another
existing role only when it does not conflict with proof access. Region defaults
to `infrastructure.aws.region`. No sequencer WIF or public-key transcription is
needed. The local alternative is `sequencerPublicKey` plus `sequencerKeyEnv`;
do not combine those fields with `sequencerKms`.

Recovery custodians do **not** need a Dogecoin node. Give each custodian the
[offline recovery-key guide](../partner-kit/recovery-key/README.md). With a CLI
build containing `helper recovery-key`, each runs this on their own machine:

```bash
scrollsdk helper recovery-key --network testnet --output "$HOME/.dogeos-recovery-key"
```

Each custodian retains `recovery-key.private.json` and sends only
`recovery-key.public.json`. Copy the `publicKey` from each of the three public
files into `preparation.bridge.production.recoveryPublicKeys` in the agreed
order. Check that the network matches and all three public keys are distinct.
The command uses local cryptographic randomness and needs no RPC, node, AWS,
CubeSigner account or deployment spec. A repeated create refuses to overwrite
the directory; `--action inspect` verifies the saved key or restored backup.
This software-key helper is for rehearsal; it does not implement hardware custody
or the emergency recovery transaction signing workflow. Production custody must
also demonstrate signing the actual Bridge recovery script and preserve its
public configuration, key order and timelock.

For the local fee wallet (and the optional local sequencer backend), one option is Dogecoin Core with
wallet support enabled, plus `dogecoin-cli` and `jq`. Use a wallet you control,
with local RPC authentication already configured. A public RPC provider cannot
create or export your private wallet keys. If you have no wallet yet, initialize
and back up an operator-owned Dogecoin Core wallet first; the example below
assumes it is running. Use `-regtest` for regtest, or omit `-testnet` for mainnet.

For a **new** deployment, obtain a fee-wallet address:

```bash
bridge_fee_address=$(dogecoin-cli -testnet getnewaddress)
```

There is no fee-wallet public key to transcribe into the spec. Apply derives it
and the funding address from the WIF below. Record the address in your private deployment records.
When resuming an existing deployment, use its recorded addresses instead of
calling `getnewaddress` again.

Export the fee-wallet key to a private file. If the wallet is
encrypted, unlock it using your wallet's normal secure procedure first. The
commands below create a fresh private directory under your home directory and
redirect WIF output into files, without printing private keys:

```bash
umask 077
bridge_key_dir=$(mktemp -d "$HOME/.dogeos-bridge-keys.XXXXXX")
dogecoin-cli -testnet dumpprivkey "$bridge_fee_address" > "$bridge_key_dir/fee-wallet.wif"
```

Check that the export succeeded. Using a private editor, put its contents
into `DOGECOIN_FEE_WALLET_KEY` in your existing `deployment.env`, preserving
the other entries. Keep that file mode `0600` and outside version control.
Do not paste the WIF into the spec, shell commands, chat or logs. Retain the
wallet backup; apply validates the WIF and selected network, then pins only its
public key and address in `.data/bridge-fee-wallet.json`. Resume refuses a changed
fee-wallet identity. Creating this key sends no transaction;
wait for apply's funding instructions before making payments.

Custodians who already use Dogecoin Core can alternatively obtain their recovery
public key with `getnewaddress` / `validateaddress`. They do not export their
private key to the operator. Do not reuse the sequencer, fee-wallet or
attestation signing keys for recovery.

The wallet commands above follow Dogecoin Core's
[getnewaddress implementation](https://github.com/dogecoin/dogecoin/blob/v1.14.9/src/wallet/rpcwallet.cpp),
[validateaddress implementation](https://github.com/dogecoin/dogecoin/blob/v1.14.9/src/rpc/misc.cpp),
and [dumpprivkey implementation](https://github.com/dogecoin/dogecoin/blob/v1.14.9/src/wallet/rpcdump.cpp).

## Plan, apply and fund

```bash
scrollsdk setup plan \
  --spec /private/instance/deployment-spec.yaml \
  --env-file /private/instance/deployment.env \
  --output /private/instance/deployment \
  --sdk-dir /path/to/scroll-sdk

scrollsdk setup apply --dir /private/instance/deployment
```

Plan validates and records the chosen inputs without provisioning resources or
sending transactions. Apply prepares identities and genesis, then waits for
confirmed sequencer and fee-wallet outpoints. It displays both required addresses,
amounts, the input file and a JSON input template. Using your external wallet, make the payments and record
only the actual outpoints in:

```text
/private/instance/deployment/.scrollsdk/inputs/bridge-funding.json
```

No funding file is needed while writing the spec or running plan. Apply creates
the file as `{}` at the funding step and prints a template for the required
entries; replace its placeholder txids and output indices with actual facts. Populate the `sequencer` and `feeWallet` objects with
`txid` and `vout`, then rerun the same apply command. The CLI checks network,
unspent status, transaction bytes, scripts, amounts and confirmations before
using the sequencer outpoint to generate the final Bridge address.

Keep the existing wallet entries when adding the Bridge entry. The next pause requests Bridge funding. This transaction must contain the required
zero-value OP_RETURN funding marker; an ordinary payment is insufficient. Use the
full marker script printed by apply. Add the confirmed `bridge` outpoint to the
same JSON file and rerun apply. Do not edit generated TOML to supply funding facts.

The Bridge portion, starting without funding, normally takes one plan plus three
apply invocations.
If the independent wallets are already funded and their outpoints are supplied
before the first apply, it takes one plan plus two apply invocations. Completed
steps and identities are preserved across these normal resumptions. Real proof
material and partner handoffs can require additional work; these counts are not
a guarantee that enforcing preparation finishes in four commands.

Successful completion reports `prepared`: service configuration, genesis, Bridge
artifacts, Secrets and signer policy are prepared. It does not mean Helm releases
have been installed or that a running chain has passed acceptance. Owner-managed
CubeSigner authorization/session material remains operator-owned. Partner policy
approval is a required handoff that apply waits for and imports before completion.

## Other deployment choices

The example already selects KMS identity creation for eth-da-submitter, fee-oracle
and both sequencers.
The example also selects `proofAws.action: create`. Optional `archive`,
`databases` and `secretUpload` operations authorize further resource changes during
apply. See the matching CLI's `docs/spec-preparation.md` for their input contracts
and required destinations. Use the standard AWS credential provider chain for
selected KMS operations; do not put cloud credentials in the spec.

## Real proof generation and completion limits

The operator selects `preparation.proofRelease.version`, for example
`v0.3.0-beta.6`. Plan reads the official `DogeOS69/dogeos-core` release
`proof-release-<version>`, downloads `dogeos-proof-release-v1.json` and its
published `.sha256`, verifies the checksum and schema, and caches the verified
manifest by digest. The immutable plan records the manifest path, checksum and
compiler/Worker image digests; apply uses these pins without selecting a newer
release. The checksum verifies the artifact against the publisher's release; it
is not an independent publisher signature. No operator-generated hash is needed.

**Release dependency:** the publishing workflow is in
[dogeos-core PR #1335](https://github.com/DogeOS69/dogeos-core/pull/1335), still open
at this update (2026-10-09). Neither `proof-release-v0.3.0-beta.6` nor
`v0.3.0-beta.6` was available through GitHub Release lookup. The core release owner
must land the workflow and publish the compatible proof artifacts. Plan fails
clearly when the release/assets are unavailable; it does not ask operators to
invent a manifest or silently substitute mock proofs. Thus this starter expresses
the intended version but cannot currently complete online planning for beta.6.

For an offline/private release handoff only, replace `version` with
`manifest: /private/approved/dogeos-proof-release-v1.json` and `sha256` from the
release owner's accompanying checksum. Supply both; do not combine them with
`version`. This is an advanced override, not the normal first step.

After generating this deployment's `.data/protocol_context.json`, apply:

1. Runs the pinned `proof-preparation-producer` through `proof-image-tools
   --action prepare-real`. This generates the deployment-bound
   `bridge/worker-identity-bundle.json`, Bridge program and preparation receipt
   under `.data/proof-release-preparation/`.
2. Exports Chunk/Batch materializers from the matching coordinator image and
   checks the CUDA Worker image against the baked identities without a GPU.
3. Imports the validated real material into `.data/proof-materials/`, builds the
   full real topology and prepares the service configuration.
4. Publishes the verified program bundle using the selected release and generated
   proof-store receipt, then exports the enforcing signer-policy bundle.

The legacy coordinator chunk/batch/bundle collection timers are removed: they
belong to retired Scroll services, not beta.6 Proof Coordinator. Native proof
materialization policy remains owned by the pinned core compiler/templates.

Apply then pauses at `signer-receipts` and writes
`.scrollsdk/inputs/signer-receipts/request.json`. Send `signer-policy-bundle/` to
the partners. Each partner validates their final enforce configuration against
the selected release and returns a `dogeos/attestation-signer-policy-validation/v1`
receipt from that verification. The beta.6 signer itself does not emit this
receipt; the partner validation process must produce it. See the matching CLI
`docs/proof-config-transactions.md` for its required bindings. The request file maps signer IDs to numbered receipt filenames. Save the
returned files there and rerun the same `setup apply` command.

Apply computes the hashes and verifies the active signer set, keys, bundle hash,
core revision, enforce policy mode, passed result and validation timestamp before
copying accepted evidence into `.data/signer-policy-validation/`. It then
regenerates the configuration with the publication receipt and runs the final
check. Wrong or stale evidence is rejected; completed AWS/proving/publication
steps are not replayed. Do not edit generated TOML or the saved plan.

This integration is covered by synthetic receipt tests. It does not establish
acceptance by real partner operators. External CUDA Worker startup, actual proving
and deployment acceptance remain separate operations. No proof mode is silently
downgraded to mock or observe.

## Validation

Validation uses disposable inputs in a private temporary directory. Checks cover
placeholder rejection, one-domain endpoint derivation, omitted coordinator fields,
release-derived image pins, real/enforce selection, planned resource effects,
finalized-anchor persistence and Vast.ai environment-key handling.

The previously recorded rc.4/beta.6 container rehearsal used a
`disabled / mock / observe`, local-identity variant. It does not establish real
proof generation, live KMS, program publication or partner enforcing-policy
acceptance for this revised example. See the
[validation record](../docs/spec-configuration-validation.md) for exact scope.
