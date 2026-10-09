# Prepare from a complete DeploymentSpec

Use [deployment-spec.example.yaml](deployment-spec.example.yaml) together with
[deployment.env.example](deployment.env.example). The spec contains every section
needed by the current `scrollsdk setup plan` / `setup apply` workflow; it does not
require assembling YAML fragments from the CLI documentation.

## Selected scope

This example prepares a **testnet deployment** with the beta.6 production Bridge
outpoint flow, one Reth sequencer, one bootnode, local service signing identities,
and a SQLite dstack controller with imported Vast.ai credentials. It selects
`disabled / mock / observe` proofs and imports an existing public compiler identity.
It does not demonstrate mainnet quorum policy or real/enforce proving.

Core service images are beta.6, the CLI genesis default is contracts rc.4, and
fresh-chain defaults are 30,000,000 gas, 2-second blocks and a 1,400 ms build window.
Reth has its own release lineage; its tag must be selected explicitly. The SDK
commit in `templates.sdkRevision` is the reviewed template baseline. The current
CLI still requires that field; automatic selection of SDK HEAD is not implemented.

Use a CLI build containing `setup plan` and `setup apply`. Check `scrollsdk setup
plan --help` before starting. AWS, Kubernetes, PostgreSQL and the external RPCs
referenced here already exist. The example selects no cloud provisioning or Secret
upload operations; generated configuration does not establish runtime access.

## Prepare the private inputs

Create an operator-owned directory outside both source repositories. Keep the
future `deployment/` directory absent or empty for `plan`:

```text
private-instance/
  deployment-spec.yaml
  deployment.env
  inputs/
    partner-a/descriptor.json
    compiler-identity.json
    vastai-api-key
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
| Infrastructure, endpoints and domains | Select the existing cluster/namespace, PostgreSQL host/user, Dogecoin testnet RPC and Ethereum Sepolia execution/beacon RPC. Set reachable service domains. |
| Environment file | Fill the six base spec variables and both `DOGECOIN_*_KEY` wallet variables. The local-create/SQLite example does not use `SEQUENCER_SIGNING_KEY` or `DSTACK_DATABASE_URL`; remove those optional entries. |
| Owner and deployment salt | Select the owner address and a unique deployment salt. Apply creates the deployer account unless the spec explicitly imports one. |
| Reth image tags | Replace all three `TODO_APPROVED_RETH_TAG` values with the reviewed compatible Reth release. |
| Bridge public keys | Supply the TEE public key, independently managed sequencer/fee-wallet public keys and recovery public key. Wallet keys in the env file must match their declared public keys. Do not derive recovery/TEE keys from a helper seed. |
| Bridge policy | Replace `timelock: 100` with a reviewed future Dogecoin block height below 500,000,000. Review quorum, confirmation depth and funding budgets. The initial sequencer amount remains exactly 42,069,000 satoshis. |
| Ethereum anchor | Select the real Ethereum DA starting block/index. The illustrative block 0 is not a deployment recommendation. Apply checks it against the chosen RPC. |
| Partner descriptor | Obtain the public beta.6 descriptor from the signer operator and place it at `inputs/partner-a/descriptor.json`. Its signer ID must match `bridge.initialAttestationKeyset.signerIds`. It includes signing/transport public keys, not a publicly reachable signer endpoint. |
| Compiler identity | Obtain the matching release's public compiler identity JSON and place it at `inputs/compiler-identity.json`. This must be an actual tool-produced identity compatible with the selected compiler, not invented hashes. |
| dstack credentials | Put the provider key in the private `inputs/vastai-api-key` file. Importing it prepares configuration; it does not validate provider access or rent GPUs. |
| Blob/proof buckets | Select two distinct existing buckets. Keep `proofArtifacts.s3` and `proofTopology.active.artifactStore` on the proof bucket, and `ethereumDa.blobArchive.s3` on the blob bucket. Set the blob archive public readback URL in `publicBaseUrl` to the actual bucket/gateway. Separate prefixes in one bucket are insufficient. |

External file paths in `preparation` are relative to the **output deployment
directory**. With the layout above, `../inputs/...` resolves to the correct sibling
directory. Absolute paths are also supported. Descriptor and compiler/provider
input files can arrive later: apply waits when a declared file is missing.

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
confirmed sequencer and fee-wallet outpoints. It displays the required address,
amount and input file. Using your external wallet, make the payments and record
only the actual outpoints in:

```text
/private/instance/deployment/.scrollsdk/inputs/bridge-funding.json
```

The file starts as `{}`. Populate the `sequencer` and `feeWallet` objects with
`txid` and `vout`, then rerun the same apply command. The CLI checks network,
unspent status, transaction bytes, scripts, amounts and confirmations before
using the sequencer outpoint to generate the final Bridge address.

The next pause requests Bridge funding. This transaction must contain the required
zero-value OP_RETURN funding marker; an ordinary payment is insufficient. Use the
full marker script printed by apply. Add the confirmed `bridge` outpoint to the
same JSON file and rerun apply. Do not edit generated TOML to supply funding facts.

Starting without funding normally takes one plan plus three apply invocations.
If the independent wallets are already funded and their outpoints are supplied
before the first apply, it takes one plan plus two apply invocations. Completed
steps and identities are preserved across these normal resumptions.

Successful completion reports `prepared`: service configuration, genesis, Bridge
artifacts, Secrets and signer policy are prepared. It does not mean Helm releases
have been installed or that a running chain has passed acceptance. Owner-managed
CubeSigner authorization/session material and partner policy approval are separate
runtime prerequisites. This example intentionally does not fabricate them.

## Other deployment choices

The CLI supports additional explicit preparation operations (`archive`, `proofAws`,
`databases`, `secretUpload`) and KMS identity intent. Adding them authorizes resource
changes during apply. See the matching CLI's `docs/spec-preparation.md` for their
input contracts and required destinations; the complete example above leaves them
unselected so copying it does not implicitly request cloud resource creation.

For real/enforce proving, use the deployment-bound real material receipts,
materializers, production Worker image, publication evidence and hosted signer
policy required by the chosen release. Merely changing three proof mode flags in
this mock example does not supply those inputs. This example's validation is not
evidence for that separate production proof path.

## Validation

The example is checked with the CLI in a temporary directory after replacing
operator placeholders with disposable test inputs. Unedited placeholders must
fail planning. The container rehearsal uses actual rc.4 / beta.6 tools with a
synthetic local chain RPC and disposable identities; no live funding, cloud
provisioning, provider access or Kubernetes deployment is implied.

The checked example passed field validation and produced all 17 planned steps
with disposable replacement inputs. Using that filled example as the baseline,
the CLI's `scripts/test-preparation-e2e.mjs` completed both funding waits,
resumed to `prepared`, and completed a further apply without repeating finished
steps. The CLI preparation/identity regression selection also passed 24 tests
from the normal repository directory after the working-copy migration.
