# Scroll SDK Helper Scripts

This directory contains helper files examples and scripts for managing and interacting with your Scroll SDK deployment.

For additional, more robust helper scripts, checkout the [scroll-sdk-cli](https://github.com/scroll-tech/scroll-sdk-cli).

## Example Files
1. `Makefile.example`: A basic makefile for quickly installing and deleting the charts necessary for the Scroll SDK.
2. `config.toml.example`: A template config.toml file for new deployments. A good starting point for filling out chain-specific details or using the Scroll SDK CLI tool.

Production service overlays are intentionally operator-readable and repeat all
runtime-affecting chart values. See the
[production values contract](../docs/production-values.md) before adapting the
files under `examples/values/`.

For the seven DogeOS core services, see the
[source-aligned example review and operator steps](core-service-review.md),
including secret ownership, native-config generation and local validation.

## Scripts

1. `l2-generate-txs.sh`: Generates transactions on the L2 network to produce more blocks.
2. `l1-generate-txs.sh`: Generates transactions on the L1 network to produce more blocks.
3. `clear-stuck-txs.sh`: Replaces transactions stuck in the mempool, useful when CCC gets overloaded.
4. `anvil-fund-accounts.sh`: Funds default L1 accounts from the prefunded local L1 devnet account.

## Dependencies

These scripts require the following dependencies:

1. [**yq**](https://mikefarah.gitbook.io/yq/): A lightweight command-line YAML processor.
   ```
   brew install yq
   ```

2. [**Foundry**](https://book.getfoundry.sh/): A toolkit for Ethereum application development.
   ```
   brew install foundry
   ```

## Usage

1. Ensure you have installed the required dependencies.
2. Make sure the scripts are executable:
   ```
   chmod +x examples/*.sh
   ```
3. Run a script from the repo root directory, for example:
   ```
   ./examples/l2-generate-txs.sh
   ```

Note: These scripts must be run from the root directory of the repository to ensure proper path resolution for the configuration file.

## Configuration

These scripts read configuration values from the `charts/scroll-sdk/config.toml` file. Ensure this file is present and properly configured before running the scripts.

## Notes

- The `clear-stuck-txs.sh` script may need manual nonce setting in some cases.
- Always review and understand a script before running it, especially when it involves sending transactions or modifying account balances.

For more information on Scroll SDK, refer to the main README in the root directory of this repository.

## Proof helper interface

`scrollsdk setup prep-charts` prepares and validates proof configuration. The
example Makefile only installs or removes the generated Kubernetes releases;
it does not provide a second proof setup interface. The normal non-DeploymentSpec
path is generated interactively into `.data/doge-config.toml`:

```bash
scrollsdk setup doge-config --proof-topology
```

Do not copy VK hashes or commitments into that file by hand. First,
`setup proof-materials` imports producer-generated artifact metadata and the
allow-listed identity environment, validates and copies the files, and records
the digest-pinned compiler and Worker images. `doge-config --proof-topology`
then combines that receipt with `.data/proof-aws.json` and deployment facts.
DeploymentSpec `proofTopology` is an advanced alternative source; both sources
must never be present at the same time.

DogeOS proof operation has three explicit fields: `mode = disabled|active`,
`generation = mock|real`, and `enforcement = observe|enforce`. The normal
rollout is `disabled/mock/observe`, then `active/mock/observe`, then
`active/real/observe`, and only after real proof health is confirmed,
`active/real/enforce`. `prep-charts` passes this source to the digest-pinned
dogeos-core compiler and installs its strict service-specific output.

The generated deployment uses the following conventional paths:

```text
.data/
├── generated/proof-topology/                 (versioned compiler bundle)
├── proof-aws.json                            (prepared non-secret AWS facts)
├── proof-deployment.json                     (single K8s install contract)
├── proof-materials-v1.json                   (validated import receipt)
├── proof-materials/                          (immutable imported files)
└── protocol_context.json                     (external Worker input)

proof-coordinator/
└── ProofCoordinator.toml                     (base replaced by compiler output)

withdrawal-processor/
└── WithdrawalProcessor.toml                  (native app config; TOML-owned)

values/
├── proof-coordinator-production.yaml
├── prover-worker-production.yaml
├── tso-service-production.yaml
└── withdrawal-processor-production.yaml      (K8s shape + secrets + switch only)

prover-worker-active/
└── docker-compose/                            (only for compiler-selected external Worker)
```

`bridge-init` records the complete genesis sequencer transaction in its
generated bridge output. `prep-charts` verifies that the decoded transaction
matches `protocol_context.json` and projects it into
`withdrawal-processor/WithdrawalProcessor.toml`; operators do not enter or
copy `genesis_sequencer_tx_hex` manually.

Copy `Makefile.example` into the deployment root as `Makefile`. No
DeploymentSpec is required for this flow. Prepare the artifact store,
import producer outputs and immutable image references, then initialize the
topology:

```bash
scrollsdk setup proof-aws-init
scrollsdk setup proof-materials
scrollsdk setup doge-config --proof-topology
```

`proof-materials` prompts for the producer manifest, identity environment,
materializer binaries, and digest-pinned image references when flags are not
provided. It validates hashes and canonical identity encodings; it does not
reimplement the Rust/OpenVM calculations. `doge-config` prompts for the three
switches and deployment-owned endpoints. New deployments default to
`disabled/mock/observe`.
After initialization, prepare and validate the disabled-mode configuration,
then install it through Make:

```bash
cp Makefile.example Makefile
# Complete the normal bridge-init and local/KMS service-signer setup first.
scrollsdk setup prep-charts -N
scrollsdk setup proof-config-check --deployment-dir .
make reconcile-proof-services
```

Before bridge genesis, give each external signer operator the complete
`partner-kit/attestation-signer/` directory, collect the descriptor produced by
their `scrollsdk signer init`, and import the descriptors with
`scrollsdk setup attestation-signer`. After genesis, send every partner the
complete `signer-policy-bundle/` produced by
`scrollsdk setup export-signer-policy`. Current dogeos-core requires canonical
protocol context in every signer mode, so partners start the service and run
`signer preflight` only after installing that bundle. Production partners use
`--require-production-ready` and keep their own RPC source sets and rotation
allowlists in the generated `attestation-signer.toml`.

For a deployment that will later use real proving, import the software
identities and Bridge-bound material before selecting `generation = real`.
Disabled mode still stores the active profile. PC remains deployed with its
minimal idle `dev_dummy`/local-filesystem chart configuration, while Worker is
not started and WP does not publish proof work.
An explicit real-generation preflight can be run before scheduling a GPU:

```bash
scrollsdk setup proof-aws-init \
  --aws-region <region> \
  --eks-cluster <cluster> \
  --deployment-alias <unique-deployment-instance> \
  --namespace <namespace>
scrollsdk setup proof-materials
scrollsdk setup doge-config --proof-topology
scrollsdk setup prep-charts -N
scrollsdk setup proof-topology-compile --preflight real
scrollsdk setup proof-config-check --deployment-dir .
make reconcile-proof-services
```

After selecting `mode = active`, `generation = real`, and
`workerLaunch = external`, rerun `prep-charts`, then run `scrollsdk setup
proof-worker --deployment-dir .` to hydrate the generated external bundle for
the GPU host. Preflight never creates or hydrates an installable bundle.

`prep-charts` embeds the compiler-rendered WP/PC native TOML and generated
program manifests into the final Helm values. `proof-config-check` validates
those self-contained values and the schema-v7 deployment contract once before
deployment. The Makefile then invokes ordinary, visible `helm upgrade -i`
commands; it does not call back into scrollsdk or reconstruct compiler paths.
Disabled mode keeps PC at one idle replica and projects Worker to zero replicas.
Real/external also keeps the local Worker at zero and uses the compiler-derived
Compose bundle on the GPU host. Active compilation replaces PC's idle config
with the complete compiler-rendered topology without scaling PC.

The default installation check blocks proof-owned managed-block or manifest
drift, while ordinary WP/TSO values and shared native-config drift are warnings.
Use `scrollsdk setup proof-config-check` for byte-for-byte immutable
CI artifacts.

The remaining proof-related Makefile variables are only Kubernetes deployment
overrides: `NAMESPACE`, `PROOF_COORDINATOR_CHART`,
`PROOF_COORDINATOR_CHART_VERSION`, `ETH_DA_SUBMITTER_CHART`,
`ETH_DA_SUBMITTER_CHART_VERSION`, `PROVER_WORKER_CHART`,
`PROVER_WORKER_CHART_VERSION`, `WITHDRAWAL_PROCESSOR_CHART`, and
`WITHDRAWAL_PROCESSOR_CHART_VERSION`.

For the authoritative end-to-end order, partner descriptor/policy handoff,
activation gates, mock-versus-production behavior, and lifecycle acceptance,
follow the
[DogeOS proof system operator runbook](https://github.com/DogeOS69/scroll-sdk-cli/blob/main/docs/proof-operator-runbook.md).
