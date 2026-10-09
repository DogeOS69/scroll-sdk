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
eth-da-submitter, fee-oracle and both sequencers, and a SQLite dstack controller
with imported Vast.ai credentials. P2P nodekeys remain local. Both the
attestation and recovery cohorts use 2-of-3; Bridge funding requires 6 confirmations.
It selects `active / real / enforce` proofs. The approved release producer
generates this deployment's Bridge-bound compiler identity; no hand-written
compiler identity or mock proof hashes are accepted. This is a testnet policy;
CubeSigner remains explicitly `transport_only`.

`network.l1ChainId` must match the fixed Dogecoin network mapping: mainnet `1`,
testnet `111111`, regtest `5555555`. The CLI rejects mismatches. This is separate
from `ethereumDa.chainId`, which is `11155111` for Sepolia.

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

Core service images are beta.6, the CLI genesis default is contracts rc.4, and
fresh-chain defaults are 30,000,000 gas, 2-second blocks and a 1,400 ms build window.
Reth has its own release lineage; its tag must be selected explicitly. The SDK
commit in `templates.sdkRevision` is the reviewed template baseline. The current
CLI still requires that field; automatic selection of SDK HEAD is not implemented.

Use a CLI build containing `setup plan` and `setup apply`. Check `scrollsdk setup
plan --help` before starting. AWS, Kubernetes, PostgreSQL and the external RPCs
referenced here already exist. Apply creates the four declared AWS KMS signing identities
and their IAM/IRSA resources using the configured region, EKS cluster and
namespace. It also publishes the real proof program bundle to the existing proof
bucket. It selects no bucket creation or Secret upload operations. Plan itself
does not provision resources;
generated configuration does not establish runtime access.

## Prepare the private inputs

Create an operator-owned directory outside both source repositories. Keep the
future `deployment/` directory absent or empty for `plan`:

```text
private-instance/
  deployment-spec.yaml
  deployment.env
  inputs/
    partner-a/descriptor.json
    partner-b/descriptor.json
    partner-c/descriptor.json
    proof/
      proof-aws.json
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
| Environment file | Fill the six base spec variables, both `DOGECOIN_*_KEY` wallet variables and `VASTAI_API_KEY`. The KMS-signer/SQLite example does not use `SEQUENCER_SIGNING_KEY` or `DSTACK_DATABASE_URL`; remove those optional entries. |
| Owner and deployment salt | Select the owner address and a unique deployment salt. Apply creates the deployer account unless the spec explicitly imports one. |
| Reth image tags | Replace all three `TODO_APPROVED_RETH_TAG` values with the reviewed compatible Reth release. |
| Bridge public keys | Supply the TEE public key, independently managed sequencer/fee-wallet public keys and three distinct recovery public keys. Wallet keys in the env file must match their declared public keys. Do not derive recovery/TEE keys from a helper seed. |
| Bridge policy | Replace `timelock: 100` with a reviewed future Dogecoin block height below 500,000,000. Attestation and recovery each select 2-of-3; funding requires 6 confirmations. Review these policies and funding budgets. The initial sequencer amount remains exactly 42,069,000 satoshis. |
| Ethereum anchor | Keep `ethereumAnchor.blockTag: finalized` for a fresh deployment. Apply resolves and saves the finalized block hash/height with transaction index 0 before DA starts. An explicit historical `blockNumber` and `transactionIndex` pair is available for reviewed overrides; do not combine it with `blockTag`. |
| Partner descriptor | Obtain three public beta.6 descriptors and place them at `inputs/partner-a/descriptor.json`, `inputs/partner-b/descriptor.json` and `inputs/partner-c/descriptor.json`. Their actual signer IDs must match `bridge.initialAttestationKeyset.signerIds`; update the sample IDs if necessary. Descriptors include signing/transport public keys; no publicly reachable signer endpoint is required. |
| Proof software release | Keep `preparation.proofRelease.version: v0.3.0-beta.6` or select the reviewed compatible version. Plan retrieves the official release manifest and checksum, validates them and freezes image pins. No manifest file or SHA256 is an operator input. If the release is missing, plan reports a core release dependency before resource creation. |
| Existing proof store | Supply the actual `proof-aws.json` receipt for the existing bucket/IRSA configuration. Its bucket, region, key prefix and service accounts must match the spec. Supply matching role ARNs in `proofCoordinator`. This is a resource-provisioning receipt, not an identity file to invent. |
| dstack credentials | Set `VASTAI_API_KEY` in the private environment file. `vastaiApiKeyEnv` names that variable; no extra key file is needed. The alternative `vastaiApiKeyFile` remains supported; choose only one. Importing credentials does not rent GPUs. |
| Blob/proof buckets | Select two distinct existing buckets. Keep `proofArtifacts.s3` and `proofTopology.active.artifactStore` on the proof bucket, and `ethereumDa.blobArchive.s3` on the blob bucket. For AWS S3, omit `publicBaseUrl` to derive `https://<bucket>.s3.<region>.amazonaws.com`. Set it for a different HTTP read origin, such as a CDN or gateway; it must serve the same blob objects. Keep `keyPrefix` separate. Deriving a URL does not configure public-read permissions. Separate prefixes in one bucket are insufficient. |

External file paths in `preparation` are relative to the **output deployment
directory**. With the layout above, `../inputs/...` resolves to the correct sibling
directory. Absolute paths are also supported. Plan needs read access to the official
GitHub proof release; optional `GH_TOKEN` / `GITHUB_TOKEN` supports private
repository access and authenticated API limits. Keep tokens outside source control.
Descriptor and existing proof-store receipt files may
arrive later; apply waits when a declared file is missing. Missing environment
credentials also produce an actionable wait.

## Obtain the TEE public key

`bridge.teePubkey` is the compressed SEC1 secp256k1 public key of the single
CubeSigner TEE signing key: 33 bytes, encoded as 66 hex characters starting with
`02` or `03`. Bridge construction consumes these bytes. A CubeSigner role ID
identifies the authorization role; a key ID identifies the provider key. Neither
is a substitute for the public key.

For an existing configured CubeSigner role, the CLI's separate
`setup cubesigner-init --roles <role-name> --doge-config <private-doge-config>`
command queries the role and its key, normalizes the provider's public key, and
writes `tee_pubkey` to `.data/setup_defaults.toml` under the current working
directory. Use that public value
in the spec. Run this command in the private CubeSigner preparation workspace
before planning a fresh deployment. The role must select the single intended
TEE key. `--roles` takes a role **name**, not a role ID.

If the CubeSigner operator provides the key instead, ask for its compressed
public key and the matching role/key references. The existing CLI uses
`cs role get --role-id=...` and `cs key get --key-id=... --role-id=...` to retrieve
provider metadata. Provider output may contain an uncompressed `04...` public
key; use the normalized `tee_pubkey` from `cubesigner-init` for this production
spec. No private key needs to be exported.

The current `plan/apply` flow requires the public key up front. It does not yet
resolve a role/key ID through CubeSigner or provision a hosted session. Runtime
role/session configuration and hosted signer policy approval remain required.

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
CubeSigner authorization/session material and partner policy approval are separate
runtime prerequisites. This example intentionally does not fabricate them.

## Other deployment choices

The example already selects KMS identity creation for eth-da-submitter, fee-oracle
and both sequencers.
The CLI supports additional explicit preparation operations (`archive`, `proofAws`,
`databases`, `secretUpload`). Adding them authorizes further resource changes during apply. See the matching CLI's `docs/spec-preparation.md` for their
input contracts and required destinations; the complete example above leaves them
unselected. Use the standard AWS credential provider chain for the selected KMS
operations; do not put cloud credentials in the spec.

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
4. Publishes the verified program bundle using the selected release and existing
   proof-store receipt, then exports the enforcing signer-policy bundle.

The legacy coordinator chunk/batch/bundle collection timers are removed: they
belong to retired Scroll services, not beta.6 Proof Coordinator. Native proof
materialization policy remains owned by the pinned core compiler/templates.

**Current completion limit:** partner operators must validate the exported
policy and return real signer-validation receipts. The current plan/apply flow
exports that bundle but does not yet import the returned validation references
and regenerate their bound configuration. Without this evidence, the final
`proof-config-check` rejects `enforce`; this example must not be presented as a
verified unattended path to `prepared`. The matching CLI
`docs/proof-config-transactions.md` describes that evidence and generation handoff.
External CUDA Worker startup, actual proving and deployment acceptance are also
separate operations. No proof mode is silently downgraded to mock or observe.

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
