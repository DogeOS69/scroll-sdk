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

Do not copy image digests, VK hashes, commitments, or release-relative paths
into that file by hand. The command reads a release-producer
`dogeos/proof-release/v1` manifest, verifies every referenced release file,
combines it with `.data/proof-aws.json` and deployment facts, writes complete
dormant mock and production blocks, and preflights both before committing the
configuration. DeploymentSpec `proofTopology` remains an alternative source,
but both sources must never be present at the same time.

Both forms stage mock and production resources while one `mode` field selects
the active topology. `prep-charts` passes the selected source to the
digest-pinned dogeos-core compiler and installs its strict mode-specific output
into the deployment tree. Changing `mode` therefore regenerates low-level
configuration; it does not require operators to edit WP, PC, Worker, or
submitter fields by hand.

The generated deployment uses the following conventional paths:

```text
.data/
├── generated/proof-topology/                 (versioned compiler bundle)
├── proof-aws.json                            (prepared non-secret AWS facts)
├── proof-deployment.json                     (single K8s install contract)
├── proof-release-v1.json                     (release-producer input)
└── protocol_context.json                     (external Worker input)

proof-artifacts/
├── batch/
│   ├── app.vmexe
│   └── openvm.toml
├── bin/scroll-runtime-materializer
├── bridge/
│   ├── batch-aggregation-openvm.toml
│   ├── batch-aggregation.vmexe
│   ├── bridge-state.vmexe
│   └── openvm.toml
├── chunk/
│   ├── app.vmexe
│   └── openvm.toml
├── keys/agg-verifying-key.bin
└── witnesses/

proof-coordinator/
└── ProofCoordinator.toml                     (base replaced by compiler output)

withdrawal-processor/
└── WithdrawalProcessor.toml                  (native app config; TOML-owned)

values/
├── proof-coordinator-production.yaml
├── prover-worker-production.yaml
├── tso-service-production.yaml
└── withdrawal-processor-production.yaml      (K8s shape + secrets + switch only)

prover-worker-<selected-mode>/
└── docker-compose/                            (only for compiler-selected external Worker)
```

Copy `Makefile.example` into the deployment root as `Makefile`. No
DeploymentSpec is required for this flow. Obtain the release-producer
manifest corresponding exactly to the dogeos-core service release and place it
at `.data/proof-release-v1.json`. The file
`.data/proof-release-v1.json.example` documents its strict shape but contains
placeholders and is not deployable. Prepare proof AWS resources and release
materials, then initialize the topology:

```bash
scrollsdk setup proof-aws-init \
  --aws-region us-west-2 \
  --eks-cluster dogeos-testnet \
  --network-alias testnet
scrollsdk setup doge-config --proof-topology
```

The initializer asks only for the initial mode, artifact resource source,
production Worker placement, release material/PVC location, witness source,
and any external endpoint it cannot derive. It derives and writes service
addresses, mount paths, secret references, image digests, proof identities,
and both dormant profiles. When doge-config already exists, the command enters
a proof-only flow and does not ask the ordinary Dogecoin/DA questions again.
New deployments default to `mode = "disabled"`.
After initialization, prepare and validate the disabled-mode configuration,
then install it through Make:

```bash
cp Makefile.example Makefile
# Complete the normal bridge-init and local/KMS service-signer setup first.
scrollsdk setup prep-charts -N
scrollsdk setup proof-config-check --deployment-dir .
make install-proof-stack
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

For a deployment that will later use mock or production, provision the shared
resources and complete both dormant profile blocks during initial preparation.
The compiler validates only the selected block, so a disabled deployment can
stage resources without starting proof execution. The proof topology
initializer preflights both dormant profiles before it writes the source. An
explicit production preflight can be rerun before scheduling a GPU:

```bash
scrollsdk setup proof-aws-init \
  --aws-region <region> \
  --eks-cluster <cluster> \
  --network-alias <network> \
  --namespace <namespace>
scrollsdk setup prep-charts -N
scrollsdk setup proof-topology-compile --preflight production
scrollsdk setup proof-config-check --deployment-dir .
make install-proof-stack
```

After selecting `production` with `workerLaunch: external` and rerunning
`prep-charts`, run `scrollsdk setup proof-worker --deployment-dir .` to hydrate
the generated external bundle before `proof-config-check` and deployment on the
GPU host. Preflight itself never creates or hydrates an installable bundle.

`install-proof-submitter-projection`, `install-withdrawal-processor`,
`install-proof-coordinator`, and `install-prover-worker` call the
mode-agnostic `scrollsdk helper proof-helm` adapter. It reads values and
`--set-file` bindings only from `.data/proof-deployment.json`; the Makefile
does not choose mock/production manifests or repeat proof paths. Disabled mode
skips PC and Worker automatically. Production/external skips the local Worker
and uses the compiler-derived Compose bundle on the GPU host.

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
