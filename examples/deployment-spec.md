# Prepare from a complete DeploymentSpec

Supported public applications use [existing ALB references](existing-alb.md) on AWS. Add
`infrastructure.aws.alb` for exposed endpoints before final chart preparation;
application Helm releases must not own the ALB lifecycle.

Choose [deployment-spec.testnet.example.yaml](deployment-spec.testnet.example.yaml) or
[deployment-spec.mainnet.example.yaml](deployment-spec.mainnet.example.yaml), together with
[deployment.env.example](deployment.env.example). The spec selects deployment
intent for `scrollsdk setup plan` / `setup apply`.
Operator inputs, automatically generated artifacts and external approval handoffs
are described below. Enforcing-policy evidence remains a separate integration
boundary; see the completion limits before using this starter.

For the ordered command sequence and handoff checklist, see
[Bridge operator deployment sequence](bridge-operator-deployment.md).

## Selected scope

Both examples prepare a deployment with the beta.6 production Bridge
outpoint flow, two Reth sequencers, two bootnodes, AWS KMS signing identities for
eth-da-submitter, fee-oracle, both L2 sequencers and the Dogecoin Bridge sequencer,
and a SQLite dstack controller
with imported Vast.ai credentials. P2P nodekeys remain local. Both the
attestation and recovery cohorts use 2-of-3; Bridge funding requires 6 confirmations.
It selects `active / real / enforce` proofs. The approved release producer
generates this deployment's Bridge-bound compiler identity; no hand-written
compiler identity or mock proof hashes are accepted.

| Setting | Testnet example | Mainnet example |
| --- | --- | --- |
| Instance / environment | `dogeos-testnet` / `testnet` | `dogeos-mainnet` / `mainnet` |
| Kubernetes namespace | `default` | `default` |
| Dogecoin network | `testnet` | `mainnet` |
| Ethereum DA chain / chain ID | `sepolia` / `11155111` | `mainnet` / `1` |
| Pending blob transactions (CLI default) | `10` | `8` |
| L2 chain ID | `221122`; review for your chain | `1122005` |
| CubeSigner mode | `production_verifier_key_policy` | `production_verifier_key_policy` |
| Deposit / withdrawal fee | 1 DOGE / 0.1 DOGE | 1 DOGE / 0.1 DOGE |

The mainnet spec is a preparation template, not a claim of production readiness.
The mainnet L2 chain ID is `1122005`. Set mainnet Dogecoin identities/RPC.
Each spec already includes public execution and beacon URLs for its DA network;
Fee Oracle samples Ethereum mainnet in both examples.
Both examples use CubeSigner `production_verifier_key_policy`. After the protocol
context and policy artifacts exist, complete publication, Council approval and
attachment through the governance flow on both testnet and mainnet. During staged
preparation, `setup proof-materials` pauses at `charts` and creates
`deployment/.scrollsdk/inputs/cubesigner-policy/receipts.json`. Complete that
input with the governed receipt references, then rerun `setup proof-materials`;
do not edit the frozen spec or managed `doge-config.toml`. The CLI fills the
protocol-context reference and imports verified evidence before `prep-charts`.
For standalone generation without a saved preparation plan, supply
`signing.cubesigner.policyReceipts` in the spec instead. Receipts include `release`,
`attachment` and `protocolContext` file references (`path` and `sha256`) plus the
CubeSigner `environment` and `organization`; obtain them from the completed
workflow, not from invented hashes. See the CLI's
[CubeSigner evidence handoff](https://github.com/DogeOS69/scroll-sdk-cli/blob/v0.3.0/docs/proof-config-transactions.md#cubesigner-receipts-and-external-signer-evidence)
for the receipt contract.

Select only `dogecoin.network`: `mainnet`, `testnet` or `regtest`. The CLI derives
the fixed L1 chain ID (`1`, `111111` or `5555555`) for every generated consumer.
`network.l1ChainId` is not a spec input; remove it from older specs.
`network.l2ChainId` selects the L2 chain (`1122005` for mainnet). The Ethereum DA chain ID is
separate: `ethereumDa.chainId` is `11155111` for Sepolia or `1` for Ethereum mainnet.

The public endpoint defaults are listed directly in each spec:

| Endpoint | Mainnet spec | Testnet spec |
| --- | --- | --- |
| Ethereum execution | `https://ethereum-rpc.publicnode.com` | `https://ethereum-sepolia-rpc.publicnode.com` |
| Ethereum beacon | `https://ethereum-beacon-api.publicnode.com` | `https://ethereum-sepolia-beacon-api.publicnode.com` |
| Fee Oracle sampling | `https://ethereum-rpc.publicnode.com` | `https://ethereum-rpc.publicnode.com` |

These credential-free URLs come from [PublicNode](https://ethereum.publicnode.com/).
Review provider limits and blob-broadcast support for your workload.
For authenticated endpoints, replace the corresponding spec value with
`$ENV:ETHEREUM_RPC_URL`, `$ENV:ETHEREUM_BEACON_RPC_URL` or
`$ENV:FEE_ORACLE_ETHEREUM_RPC_URL`, and fill the matching optional entry in private
`deployment.env`. Store the complete URL, including any API key, only in that env
file. An env entry alone does not override a literal URL in the spec.
Fee Oracle sampling is independent of DA publication and does not change its L2
transaction destination.

The matching CLI exports these URLs to private `secrets/*.env`, uploads them with
`push-secrets`, and projects ExternalSecret references into the service values.
eth-da-submitter, l1-interface, withdrawal-processor and fee-oracle receive URLs
from their existing service Secret flow. The proof coordinator uses the separate
`proof-coordinator-rpc-env` Secret for its bridge and scroll-batch materializers.
Only materializer/provider sections present in the compiled configuration receive
RPC overrides; absent or mock-only materializers do not acquire partial tables.
Compiler-owned proof tokens stay in their existing store. The scroll-monitor
balance exporter uses `scroll-monitor-balance-env`. KMS signing does not remove these RPC Secrets.
Keep provider URLs out of ConfigMaps, Helm values, shared plans and deployment
reports. A frontend/browser RPC is visible to its users and must use an endpoint
intended for public clients; this server-side secret flow does not conceal it.
External attestation-signer RPC configuration is managed separately.

For spec deployments, the default AWS Secrets Manager prefix is
`dogeos/<eksClusterName>/<namespace>/<metadata.name>`. This separates instances in
different clusters or namespaces without another required input. The CLI saves
that choice in the private deployment configuration; generated ExternalSecrets,
`apply` uploads and a later standalone `push-secrets` use the same prefix. Do not
repeat it as a command-line flag in the normal workflow.

To reuse an existing store layout, set `infrastructure.aws.secretsPrefix` explicitly.
An explicit `preparation.secretUpload.awsPrefix` is also honored; if both fields
are set, they must agree or generation fails before upload. Explicit prefixes
remain operator-owned, including nested paths. Reusing an explicit prefix across
deployments intentionally shares those secret names; automatic isolation applies
to the default prefix, not an explicit override.

After changing an endpoint, regenerate and upload the service secrets. External
Secrets refreshes the Kubernetes Secret, but running processes keep their old
environment until their Pods restart. Update the release values to remove any old
plaintext RPC entries, wait for ExternalSecret readiness, and restart the affected
workloads as part of the endpoint change. A Helm upgrade alone may not restart a
Pod when only an external secret's contents changed.

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

Core service images, including the KMS-enabled withdrawal-processor, use
`v0.3.0-beta.7`. See [the release pins and publication prerequisites](core-beta7-images.md).
That image supports KMS sequencing; its fee wallet still uses a local key.
The contracts deployment example uses rc.7. Select the matching rc.7 genesis
and verification images explicitly when using a CLI release whose defaults are
older; see [Contracts images](README.md#contracts-images). Fresh-chain defaults
are 30,000,000 gas, 2-second blocks and a 1,400 ms build window.
Empty blocks are disabled by default (`reth.sequencer.allowEmptyBlocks: false`);
the block interval does not require producing a block when there is no eligible work.
Reth has its own release lineage; its tag must be selected explicitly. Both
starters pin `templates.sdkRevision` to `58acf6b9b64adf59f2e0d4a095010958d4e16472`,
the reviewed application-owned ALB/NLB charts in [SDK PR #175](https://github.com/DogeOS69/scroll-sdk/pull/175).
Fetch that commit into the SDK checkout used by `--sdk-dir` before planning:

```bash
git -C /path/to/scroll-sdk fetch origin 58acf6b9b64adf59f2e0d4a095010958d4e16472
```

The pin selects committed templates and matching chart versions; working-tree
edits do not affect it. After #175 merges, a newer reviewed revision containing
that support can replace the pin. Install the matching published chart versions,
or build and use the charts from that exact SDK revision locally. Plan checks
selected binding support before querying CubeSigner or resolving proof releases.
Apply keeps the frozen revision even if the checkout advances.

Use a CLI build containing `setup plan` and `setup apply`. Check `scrollsdk setup
plan --help` before starting. AWS, Kubernetes and the external RPCs
referenced here already exist. PostgreSQL is needed when deploying Blockscout,
or when explicitly selecting PostgreSQL for dstack. The SQLite example does not
select Blockscout database initialization; PostgreSQL can be deferred while
preparing the chain. Apply creates the five declared AWS KMS signing identities
and their IAM/IRSA resources using the configured region, EKS cluster and
namespace. It also creates/reconciles the declared proof bucket, its workload
roles and token Secret, and publishes the real proof program bundle. Secret
upload is a separate operator step in this example. The selected archive step creates the blob bucket and applies its reviewed public-read policy. Plan itself
does not provision resources;
generated configuration does not establish runtime access.

## Public application ALBs and other ingresses

Both starters explicitly select `infrastructure.aws.alb.mode: existing`. Before
`setup plan`, fill the three ALB/HTTPS-443 listener pairs and all seven HTTP/IP
target groups. Resources must belong to the configured AWS account, region and
EKS VPC. Set `infrastructure.kubeContext` to that EKS cluster. The TSO and Proof
Coordinator must use separate ALBs; the other public applications may share the
`public` ALB. Each binding uses a distinct target group. `serviceRef` names and
ports match the pinned templates and Makefile release names; review them if you
change a release name or Service override.

ALBs, ACM certificates, DNS, security groups and forwarding rules are externally
managed. Application Helm releases own only their TargetGroupBindings. Generation
disables the selected Kubernetes Ingresses and retains their host/path metadata
for verification. Do not enable those Ingresses or use their certificate/group
annotations to configure the external ALBs. Other applications, such as dstack
and an enabled Grafana ingress, retain their ordinary ingress configuration.

Configure the external HTTPS listener certificates for the generated hostnames.
HTTP RPC (`rpc.<baseDomain>`) and WebSocket RPC (`ws-rpc.<baseDomain>`) need
separate host rules and target groups. Blockscout `/api` and `/api/*` rules must
precede its frontend `/*` rule. TSO exposes only `/health`, `/signer` and
`/signer/*`; do not forward its private management routes. Proof Coordinator
requires an ALB idle timeout of at least 120 seconds. Target-group health checks
must match the retained application values, including success codes.

Set the chosen TSO ALB subnet CIDRs in
`values/tso-service-production.yaml` under `networkPolicy.allowFrom.edge` before
final render. Keep `preparation.tsoAlbEdge` disabled for existing ALBs. The
remaining internal peer restrictions and CNI enforcement still apply.

Run these read-only checks from the generated deployment directory:

```bash
scrollsdk setup alb
# After application installation:
scrollsdk setup alb --require-services
scrollsdk test ingress --config config.toml
```

Final AWS chart preparation rejects enabled public application ingresses without
an existing binding. To omit a public endpoint, remove its binding and explicitly
disable its corresponding ingress in operator values; remove any stale binding
and `existingAlbBinding` marker when migrating an already generated deployment.
See the [pinned existing-ALB guide](https://github.com/DogeOS69/scroll-sdk/blob/58acf6b9b64adf59f2e0d4a095010958d4e16472/examples/existing-alb.md)
for routing, NetworkPolicy and lifecycle checks. Bootnode TCP P2P NLBs remain
separate. These templates and checks do not establish live deployment acceptance.

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
# Choose ONE spec; use deployment-spec.mainnet.example.yaml for mainnet.
install -m 600 examples/deployment-spec.testnet.example.yaml /private/instance/deployment-spec.yaml
install -m 600 examples/deployment.env.example /private/instance/deployment.env
```

Create `/private/instance` first, using your own writable location with private
permissions. Edit the copies. Every `REPLACE_WITH_*`, `TODO_*`, `*.example.invalid`
and marked numeric value is an operator input. These are deliberately unusable
placeholders, not working identities or credentials.

| Input | Required action |
| --- | --- |
| Infrastructure, endpoints and domains | Fill the existing ALB/listener/target-group references and EKS kubeContext as described above. Select the existing cluster/namespace, PostgreSQL host/user and the matching Dogecoin RPC. Review the public execution/beacon URLs in the selected spec; use private `deployment.env` references for authenticated providers. Select Fee Oracle Ethereum sampling independently. Set `frontend.baseDomain` once. The proof URL derives from its `proofCoordinator` subdomain and dstack ingress defaults to `dstack.<baseDomain>`; explicit endpoint overrides remain supported. |
| Environment file | Fill the referenced environment variables, `DOGECOIN_FEE_WALLET_KEY` and `VASTAI_API_KEY`; review the three Ethereum endpoint defaults in the spec. The KMS/SQLite example does not use `DOGECOIN_SEQUENCER_KEY`, `SEQUENCER_SIGNING_KEY` or `DSTACK_DATABASE_URL`. |
| Owner, fee-vault recipient and deployment salt | Select the owner address, an independently controlled Dogecoin P2PKH fee-vault recipient, and a unique deployment salt. Apply creates the deployer account unless the spec explicitly imports one. |
| Reth image tags | Replace all three `TODO_APPROVED_RETH_TAG` values with the reviewed compatible Reth release. |
| Bridge public keys | Select the CubeSigner role ID (and key ID for a multi-key role); plan queries the TEE public key. Apply obtains the Bridge sequencer public key from KMS and derives the fee-wallet public key from its environment WIF. Supply three recovery public keys using [Prepare the Bridge keys](#prepare-the-bridge-keys). |
| Bridge policy | Replace `timelock: 100` with a reviewed future Dogecoin block height below 500,000,000. Attestation and recovery each select 2-of-3; funding requires 6 confirmations. Review these policies and funding budgets. The initial sequencer amount remains exactly 42,069,000 satoshis. |
| Ethereum anchor | Keep `ethereumAnchor.blockTag: finalized` for a fresh deployment. Apply resolves and saves the finalized block hash/height with transaction index 0 before DA starts. An explicit historical `blockNumber` and `transactionIndex` pair is available for reviewed overrides; do not combine it with `blockTag`. |
| Attestation identities | Fill `attestationSigners` from approved Governance records: one `name`, `attestationPubkey` and `transportPubkey` per signer. Selected names must match `bridge.initialAttestationKeyset.signerIds`. No descriptor files or publicly reachable signer endpoints are required. |
| Proof software release | Keep `preparation.proofRelease.version: v0.3.0-beta.7` or select the reviewed compatible version. Plan retrieves the official release manifest and checksum, validates them and freezes image pins. No manifest file or SHA256 is an operator input. If the release is missing, plan reports a core release dependency before resource creation. |
| Proof resources | The example selects `preparation.proofAws.action: create`; apply provisions/reconciles the proof bucket, IAM/IRSA roles and token Secret, then writes `proof-aws.json`. For existing resources use `action: reuse` with `existing-public-s3` or `existing-gateway`. Optional role names and Secret name select nonstandard resources; ARNs are queried. Reuse makes no AWS changes and verifies account, bucket region, EKS trust and current Secret metadata. Access/readback still needs validation during publication. |
| dstack credentials | Set `VASTAI_API_KEY` in the private environment file. `vastaiApiKeyEnv` names that variable; no extra key file is needed. The alternative `vastaiApiKeyFile` remains supported; choose only one. Importing credentials does not rent GPUs. |
| Blob/proof buckets | Select two distinct bucket names; apply prepares the blob bucket as selected by `archive` and the proof bucket as selected by `proofAws`. Configure proof storage only at `proofArtifacts.s3`, and blob storage at `ethereumDa.blobArchive.s3`. The CLI derives Coordinator and Topology bucket/region/prefix/endpoint settings; repeating those fields in the spec is rejected. Proof region defaults to `infrastructure.aws.region`; set `proofArtifacts.s3.region` only for a different region. For AWS S3, omit `publicBaseUrl` to derive `https://<bucket>.s3.<region>.amazonaws.com`. Set it for a different HTTP read origin, such as a CDN or gateway; it must serve the same blob objects. Keep `keyPrefix` separate. Deriving a URL does not configure public-read permissions. Separate prefixes in one bucket are insufficient. |

`bridge.timelock` is an absolute Dogecoin block height chosen for this deployment,
not a duration or a fixed release constant. Core beta.6 separately defines
[`MIN_RECOVERY_DELAY_BLOCKS = 259200`](https://github.com/DogeOS69/dogeos-core/blob/v0.3.0-beta.6/crates/bridge_script_utils/src/types.rs)
and enforces `new timelock >= CLTV anchor height + 259200` when admitting and
verifying a RotateKey transition. The bridge-generation tool accepts the supplied
absolute height; it does not automatically add this delay. A future height that
passes initial preparation does not by itself satisfy later rotation policy.
Review the recovery horizon for production, and do not copy the builder's
`525600` default as a live-network absolute height. Once funded, changing the
script's timelock changes the Bridge address and requires the protocol's reviewed
rotation process; editing the deployed spec does not update an existing Bridge.

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
External receipts may arrive later; apply waits when a required receipt is missing. Missing environment
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

### Generate genesis first and stop

When later service or Bridge inputs are not ready, start with a genesis-only plan:

```bash
scrollsdk setup plan --until genesis
scrollsdk setup apply
```

The plan records the stopping boundary, so apply stops automatically even if
`--until` is omitted. It prepares the real deployer account, primary L2 sequencer
identity and Fee Oracle identity, then invokes the contracts generator and exports
`deployment/.data/genesis.json` alongside `deployment/values/genesis.yaml`.
The result is `status: paused` with exit code 0, not a completed deployment.
An existing full plan can also be stopped with `scrollsdk setup apply --until genesis`.

Genesis-only planning validates chain/network, genesis economics, owner and
contract recipients, deployment salt, and the necessary identity intents. It does
not query CubeSigner or download a proof release, and does not require signer
public keys, recovery keys, Dogecoin RPC credentials, fee-wallet WIF, PostgreSQL,
Vast credentials, ingress certificates, or runtime image tags. It needs a local
SDK checkout and Docker for the contracts generator (or the explicit local
contracts backend). KMS identities still require AWS access: apply may create or
reuse the primary sequencer and Fee Oracle KMS keys and their IAM/IRSA resources.
It does not provision archive/proof buckets, prepare dstack, fund wallets,
initialize the Bridge, or install services at this boundary.

After reviewing genesis, complete the remaining fields in the original spec and
run the regular commands:

```bash
scrollsdk setup plan
scrollsdk setup apply
```

Plan expands the saved genesis-only plan after full validation. It requires the
same genesis inputs and pinned SDK revision, verifies the saved artifacts, and
preserves all completed genesis steps and identities. Changed genesis inputs or
modified artifacts are rejected; do not delete the deployment directory to work
around that check. Repeating a genesis-only apply is safe and does not advance.
For a full plan paused by an apply flag alone, resume with `setup apply` without
the flag; no new plan is needed. Plans created by an older CLI workflow still
require their original CLI version.

## Plan, apply and fund

```bash
cd /private/instance
scrollsdk setup plan
scrollsdk setup apply
```

The defaults are `deployment-spec.yaml`, optional `deployment.env`, preparation
output `deployment/` and SDK checkout `../scroll-sdk`, relative to this working
directory. If the SDK is elsewhere, pass `--sdk-dir /path/to/scroll-sdk` to plan.
Custom paths remain optional overrides; apply uses the saved environment-file
reference. See the [operator guide](bridge-operator-deployment.md) for the table.

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
`txid` and `vout`, then rerun the same apply command. For new deployments the
sequencer payment must be output **0**; construct it first, put fee-wallet/change
outputs after it, and decode the funded transaction before broadcasting. A wallet
may reorder outputs or insert change, so verify the final signed transaction too.
Nonzero sequencer outputs are rejected. Do not change an existing outpoint index
to pretend it is zero: an existing nonzero deployment requires a reviewed recovery
or migration, not this fresh-deployment procedure. The CLI checks network,
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
artifacts, Secrets and the signer deployment kit are prepared. It does not mean Helm releases
have been installed or that a running chain has passed acceptance. Owner-managed
CubeSigner authorization/session material remains operator-owned. Apply waits
for the deployment kit's publication to be recorded before completion.

## Install the frontend and monitoring releases

`setup apply` prepares files; it does not run Helm. From the generated deployment
directory, install these two releases explicitly after reviewing their values
and uploading the referenced Secrets:

The SDK monitor template enables public status-page automation by default in
`values/scroll-monitor-production.yaml`; it is not a second switch in the spec.
Before installing monitoring, complete the
[status-page setup](../docs/status-page-automation.md): choose the public environment
and effective source files, configure component health deadlines and heartbeat,
restore or reconcile the existing Instatus page/component bindings, and install
the generated private webhook Secrets. Fill `INSTATUS_API_KEY` in the private
`deployment.env`; `setup status-page --plan/--apply` loads it automatically from
the saved preparation environment file, without an extra shell export.
`setup apply` prepares the deployment;
it does not perform the separate Instatus `setup status-page --apply` operation.
Keep private bindings across rebuilds so existing incidents can be evaluated and
recovered when fresh health evidence is available. Only set `statusPage.enabled`
to false when deliberately opting out; otherwise a rebuild can leave old public
incidents open with no service to update them.

```bash
make install-scroll-monitor KUBE_CONTEXT="$KUBE_CONTEXT" NAMESPACE="$NAMESPACE"
make install-frontends KUBE_CONTEXT="$KUBE_CONTEXT" NAMESPACE="$NAMESPACE"
```

`install-scroll-monitor` uses `values/scroll-monitor-production.yaml` and adds
`values/scroll-monitor-dstack.yaml` when present. Install monitoring early so
Prometheus Operator CRDs and service monitoring are available for the remaining
services. Ensure the Grafana admin Secret referenced by `grafana.admin` exists;
the matching CLI prepares its private credentials during the `secrets` step,
preserves them on resume, and generates `secrets/grafana-admin.env` for the
default reference. Use the same external-store upload as Dogecoin:

```bash
scrollsdk setup push-secrets -N --provider aws \
  --aws-region "$AWS_REGION" \
  --secret-file secrets/grafana-admin.env \
  --values-file values/scroll-monitor-production.yaml
```

A full `push-secrets` invocation already includes this file; the scoped command is
for updating monitoring alone. The remote AWS secret is
`<prefix>/grafana-admin-env`; the shared External Secrets integration creates
`grafana-admin` with `admin-user` and `admin-password` in the release namespace.
Vault uses the same ENV input and `--provider vault`. Configure External Secrets
Operator and its store authentication as for Dogecoin before installation.
Wait for the ExternalSecret to report Ready after installing scroll-monitor:

```bash
kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" wait \
  --for=condition=Ready externalsecret/grafana-admin --timeout=120s
```

Use the corresponding names if the template selects a custom admin Secret.
Do not apply a standalone Grafana admin Secret YAML. Credentials stay in private
local state and the external store; values contain references only. The generated
password is an initial admin credential, not a password-rotation mechanism for an
existing Grafana database. An existing direct Secret can be adopted only after
uploading its identical credentials and reviewing ExternalSecret ownership;
do not delete or regenerate the live password to migrate it.
This requires scroll-monitor chart **0.1.44-dogeos** (or the matching local chart).
The OCI chart must be published before the new Makefile version can be installed.

`install-frontends` consumes both `values/frontends-production.yaml` and
`values/frontends-config.yaml`. Install it after contract addresses and public
RPC endpoints are finalized. Verify the portal domain and TLS certificate;
frontend availability alone does not establish Bridge transaction acceptance.
The CLI generates the dynamic deposit endpoint and protocol identity from local
Bridge artifacts. Do not enter a static Bridge address in frontend values. See
[frontend configuration](frontend-configuration.md) for identity sources, readiness
requirements, cache handling and rotation behavior.
Blockscout/explorer links require a separately configured Blockscout deployment.
Blockscout and its contract verifier are excluded from `install-all`; after
preparing the database and values, opt in with `make install-blockscout`.

Grafana and Dogecoin ingress are disabled in the SDK example values. They remain
accessible inside the cluster, with local operator access through
`kubectl port-forward`. Their generated hostnames do not enable ingress.
An operator can explicitly enable the corresponding ingress in the values;
subsequent configuration generation preserves that choice.

The Makefile also includes both releases in `install-all` (monitoring through
`install-scroll-core`). Do not rerun `install-all` to add a missing release to an
existing deployment: it also invokes contract deployment and other initialization
steps. Use the individual targets above, then check each release's Pods and
public endpoint. See [monitoring configuration](scroll-monitor-configuration.md)
for collection and alerting details.

## Slack notification configuration

Declare notification intent in the spec and keep the webhook in the private env
file. There is one fixed environment variable; do not copy the webhook into YAML:

```yaml
monitoring:
  slack:
    enabled: true
```

```dotenv
SLACK_WEBHOOK_URL=REPLACE_WITH_SLACK_WEBHOOK_URL
```

Apply generates `secrets/scroll-monitor-slack.yaml` with private file permissions.
Generated monitor values reference this Secret and provision the `slack-alerts`
Grafana contact point. Missing or placeholder webhook inputs fail secret
preparation without printing their values. Reruns preserve the Grafana admin
identity. `monitoring.slack.enabled: false` removes only the spec-owned Slack
integration; unrelated contact points remain intact. The existing values template selects the alerting backend: Grafana uses a
Secret-backed contact point; Prometheus/Alertmanager uses its existing Slack
Secret reference and mounted webhook file. Policies, resource limits, storage,
channels and thresholds remain template-owned.

When `preparation.secretUpload` supplies an explicit `kubeContext`, apply uploads
Slack to Kubernetes; Grafana is uploaded to the selected external store by the
ordinary `push-secrets` step. Without automatic upload, use the dedicated command before installing
or upgrading scroll-monitor:

```bash
scrollsdk setup monitoring-secrets \
  --apply --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE"
make install-scroll-monitor KUBE_CONTEXT="$KUBE_CONTEXT" NAMESPACE="$NAMESPACE"
```

Run from the generated deployment directory. The environment file comes from the
saved plan, or `./deployment.env` when no environment file was recorded; override
with `--env-file` only when needed. The command also prepares Grafana
ENV credentials; upload those with `push-secrets` as described above. Its `--apply`
flag applies only the Slack Secret, never Grafana admin credentials. Enabling this integration enables
alert delivery after the monitor upgrade; no test message is sent by secret
preparation. A webhook change also requires a Grafana restart because the
provisioned URL is read from an environment variable at startup. Use
`kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" rollout restart deployment/grafana`
after updating that Secret on an existing installation.

## Other deployment choices

The starter uses Vast.ai workers and leaves dstack cloud SDK credentials disabled.
Running the controller on EKS does not require enabling AWS worker credentials.
For AWS workers authenticated through IRSA, chart 0.1.3 supports an explicit
`dstackController.defaultCredentialsEnabled: true` with the controller's
`serviceAccount.annotations.eks.amazonaws.com/role-arn`. The matching CLI emits
`AWS_EC2_METADATA_DISABLED=true` for this combination and preserves disabled
Kubernetes API token automount. Supply the native AWS backend (`creds.type:
default`) in the controller projects Secret and the appropriate IAM permissions;
this switch does not provision either. It also enables automatic backend
credential discovery. See the [controller guide](../charts/dstack-controller/README.md).

The example already selects KMS identity creation for eth-da-submitter, fee-oracle
and both sequencers.
The example also selects `proofAws.action: create`. Optional `archive`,
`databases` and `secretUpload` operations authorize further resource changes during
apply. See the matching CLI's `docs/spec-preparation.md` for their input contracts
and required destinations. Use the standard AWS credential provider chain for
selected KMS operations; do not put cloud credentials in the spec.

## Real proof generation and completion limits

The operator selects `preparation.proofRelease.version`, for example
`v0.3.0-beta.7`. Plan reads the official `DogeOS69/dogeos-core` release
`proof-release-<version>`, downloads `dogeos-proof-release-v1.json` and its
published `.sha256`, verifies the checksum and schema, and caches the verified
manifest by digest. The immutable plan records the manifest path, checksum and
compiler/Worker image digests; apply uses these pins without selecting a newer
release. The checksum verifies the artifact against the publisher's release; it
is not an independent publisher signature. No operator-generated hash is needed.

**Release dependency:** the beta.7 image workflow includes the proof release pipeline.
The example requires `proof-release-v0.3.0-beta.7` with its manifest and checksum;
a Git tag or successful service-image build alone is insufficient. At this update
(2026-10-15), the image workflow is still running and that proof release is not yet
available. Plan fails clearly until the required assets are published; do not
substitute the beta.6 proofexp release or invent a checksum. See
[beta.7 image update](core-beta7-images.md) for the validation boundary.

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
   proof-store receipt, then writes the signer deployment kit.

The legacy coordinator chunk/batch/bundle collection timers are removed: they
belong to retired Scroll services, not beta.6 Proof Coordinator. Native proof
materialization policy remains owned by the pinned core compiler/templates.

Apply then pauses for publication. Publish the kit directory (`deployment-kit-k-<12 hex>/`, or an archive of it)
unchanged at an immutable https URL and put the URL and manifest SHA-256 on the
deployment's Governance record. Save
`{"url": "<https URL>", "manifest_sha256": "<sha>"}` as
`.scrollsdk/inputs/deployment-kit/published.json` and rerun `setup apply`; it
records the publication and runs the final check. Signers import the kit with
that SHA-256 ([signer kit README](../partner-kit/attestation-signer/README.md)).
There are no signer receipts. After rollout, `scrollsdk setup proof-config-check
--live --kube-context <context> --namespace <namespace>` must pass: every
registered attestation signer polls the TSO. Completed
AWS/proving/publication steps are not replayed on resume. Do not edit generated
TOML or the saved plan.

A fresh TSO poll does not establish that a partner signer can sign real traffic. External CUDA Worker startup, actual proving
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

## Optional GPU capacity intent

`proofWorkers` declares bounded Vast.ai capacity for the already configured dstack
controller. The complete starter includes one RTX 3090, a two-hour run, $0.80 per
instance-hour ceiling and $3 rental admission budget. Preparation validates and
records this intent without renting a GPU. After deploying the coordinator and
controller, use `setup proof-workers plan` and `setup proof-workers apply` from
the generated runtime directory. See [GPU capacity and lifecycle](proof-workers.md)
for the eight-hour example, status, cancellation, recovery and billing boundaries.
The worker image and proof arguments come from the checked compiler contract.
