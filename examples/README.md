# Scroll SDK Helper Scripts

This directory contains helper files examples and scripts for managing and interacting with your Scroll SDK deployment.

For additional, more robust helper scripts, checkout the [scroll-sdk-cli](https://github.com/scroll-tech/scroll-sdk-cli).

## Example Files
1. `Makefile.example`: A basic makefile for quickly installing and deleting the charts necessary for the Scroll SDK.
2. `config.toml.example`: A template config.toml file for new deployments. A good starting point for filling out chain-specific details or using the Scroll SDK CLI tool.

For the CLI spec `plan`/`apply` workflow, use the complete
[deployment-spec.example.yaml](deployment-spec.example.yaml), the companion
[deployment.env.example](deployment.env.example), and the
[step-by-step operator guide](deployment-spec.md). Copy the YAML and env file
outside the checkout, fill the marked deployment inputs, and pass them to
`setup plan --spec ... --env-file ...`. The example selects testnet production-Bridge preparation with active/real/enforce
proof intent; the guide records the outstanding partner-evidence handoff. Comments identify base
variables, wallet keys and optional signer/database imports. Keep completed inputs
private; the output deployment directory starts empty.

Production service overlays are intentionally operator-readable and repeat all
runtime-affecting chart values. See the
[production values contract](../docs/production-values.md) before adapting the
files under `examples/values/`.

For sequencer CPU, memory, storage, and block-production settings, see the
[sequencer sizing recommendations](../docs/sequencer-sizing.md), including
measured transfer and full-gas workload results from the devnet test.

For the eight DogeOS core services, see the
[source-aligned example review and operator steps](core-service-review.md),
including secret ownership, native-config generation and local validation.
The follow-up [startup command decision](core-service-review.md#startup-command-decision)
keeps fee-oracle and TSO's normal startup in the chart/image instead of
duplicating command/args in their environment overlays.

For monitoring inputs, see the [scroll-monitor generation contract](scroll-monitor-configuration.md)
and [production values example](values/scroll-monitor-production.yaml). They
identify the public signer addresses, RPC URLs, expected chain IDs, optional
Secret keys and ServiceMonitor ownership that must follow the deployment.

For the beta.6/rc.4 configuration sources, DeploymentSpec coverage and known
differences from individual setup commands, see the
[spec configuration audit](../docs/spec-configuration-audit.md). It includes
a diagnostic probe and separates generated configuration from deployment
acceptance.

### Keep deployment fixes and examples synchronized

When a deployment exposes a missing or incorrect service setting, update both
its local `values/<service>-production.yaml` and the matching example here.
Use placeholders for instance-specific domain names, IAM roles, buckets and
secret references; never copy credentials or generated proof identities.
If the CLI/compiler owns the field, repair its source/template and regenerate
the local values, then update the example's input/wiring or instructions rather
than keeping a second hand-maintained generated configuration. Keep intentional
environment differences explicit (for example, a shorter DA MAX_OPEN_L2_TIME
for a development network than the 2h production target). Validate Helm rendering and the
native config, record manual steps in the CLI handbook, and commit each fix.

## Fee parameters selected on 2026-09-29

The production examples apply the targets from `dogeos-fee-20260929.md`.
These are launch targets; use a rollup-node release with the matching fee
constants from the start of a fresh mainnet deployment.

| Setting | Target | Example / authority |
| --- | --- | --- |
| Block interval / payload build window | 2000 / 1400 ms | `values/l2-reth-sequencer-production.yaml` |
| Empty blocks / fee recipient | enabled / `0x5300000000000000000000000000000000000005` | Sequencer values; CLI derives recipient from `contracts.overrides.L2_TX_FEE_VAULT` |
| Builder / genesis gas limit | 30,000,000 | Reth values set the builder; `genesis.GAS_LIMIT` sets the genesis header |
| L2 base fee overhead | 420,000,000,000 wei | `contracts.L2_BASE_FEE_OVERHEAD`, applied during L2 contract initialization |
| RPC `--gpo.maxprice` | 420,000,000,000,000 wei | Internal and public RPC `reth.extraArgs` |
| Commit / blob scalar | 600,000,000 / 7,400,000,000 | `config.toml.example` (scaled by 10^9: 0.6 / 7.4) |
| Penalty factor | 10,000 | `config.toml.example` |
| Ethereum priority fee | 100,000,000 wei | Submitter and fee-oracle values |
| DA batch | `auto`, 2h, 512 blocks/chunk, 64 chunks/batch | Submitter values |
| DA chunk limits | 30,000,001 gas; 122,880 uncompressed bytes | Submitter values |
| DA publish | target/max 6 blobs; batch wait/liveness delay 1h | Submitter values; fee-oracle target also 6 |
| Fee-oracle writes | `live` | Fee-oracle values |
| Withdrawal fee rate | 1,000,000 sat/kvB | `withdrawal-processor/WithdrawalProcessor.toml` |

For a fresh chain, copy `config.toml.example` to the deployment's `config.toml`.
`scrollsdk setup gen-l2-artifacts` passes that file to the contracts image;
`GenerateGenesis` reads it to produce genesis. The contracts repository's
`docker/templates/config.toml` carries the same initial fee parameters.

- **Gas limit:** `genesis.GAS_LIMIT = 30000000` is written into the genesis
  header. The builder value remains a separate runtime setting and matches it.
- **Oracle storage:** `contracts.COMMIT_SCALAR`, `BLOB_SCALAR` and
  `PENALTY_FACTOR` are written directly into genesis storage at the oracle
  predeploy. Initial contract deployment uses the same inputs and sets the
  penalty factor before the scalars.
- **L2 overhead:** `contracts.L2_BASE_FEE_OVERHEAD = 420000000000` is applied by
  `DeployScroll.initializeL2SystemConfig()` during initial L2 deployment, before
  ownership transfer and public launch. L2SystemConfig is a subsequently
  deployed proxy, not a predeploy populated by `GenerateGenesis`. The initial
  header value `genesis.BASE_FEE_PER_GAS` remains a separate bootstrap input;
  it also feeds the synthetic L1 interface and does not set the L2 floor.

These new gas-limit and overhead inputs require **rebuilt gen-configs and deploy
images containing the corresponding scroll-contracts changes**. Use the matching
images listed in [Contracts images](#contracts-images) below.
Merely adding keys while using an older image will not
activate them. Check the generated genesis gas limit and the initialized
`L2SystemConfig.baseFeeOverhead` before launch.

**Node constants remain a separate release requirement:** D48 / E10 and a
420,000 gwei cap require a compatible dogeos-reth/rollup-node binary. The source
document marks D48 and the cap as proposed; E10 is decided. Both
`MAX_L2_BASE_FEE` and `DOGEOS_MAXIMUM_BASE_FEE` must be `420000000000000`, with
Feynman `BaseFeeParams::new(48, 10)`. Neither genesis input nor RPC
`--gpo.maxprice` changes these compiled constants. Do not change zk guest pins
for this parameter update.

For an existing network, apply the submitter's gas-per-chunk limit **before**
raising the builder gas limit, upgrade every validating node **before** setting
420 gwei overhead, and lower the overhead to at most 10 gwei **before** rolling
back to an old node binary.

`scrollsdk setup prep-charts` preserves template-owned batch/publish/fee policies,
Reth timing/gas settings and `reth.extraArgs`; it fills deployment facts such as
RPC URLs, signer references and the fee-vault recipient. Keep these policies in
`values/` when using the normal example-based flow. The optional
`generate-from-spec --with-values` / `--values-only` path regenerates files from
DeploymentSpec and does not merge existing values. Keep using the full production
templates for runtime policy. In particular, `max_open_l2_time` and
`max_uncompressed_chunk_bytes_size` belong only in the submitter values; the CLI
does not model or generate them. Legacy spec fields can still supply explicit
overrides, but the CLI does not fill missing batch, publish or minimum-priority-fee
policy with its own defaults.

## Core release configuration

The core service examples target **v0.3.0-beta.6**. Follow the
[beta.6 configuration checklist](core-beta6-configuration.md) for the signer
format, independent S3 targets, binary approval pins and proof identities.
Update the generated deployment configuration together with the images;
changing only the tags is not sufficient.

The [beta.5c upgrade checklist](core-beta5c-configuration.md) describes the
historical beta.5b-to-beta.5c transition only. Its statements about retaining
proof identities do not apply to beta.6. See the
[fresh deployment checklist](../docs/fresh-deployment-known-issues.md) for
owner access, Bridge funding, CubeSigner binding, retained L2 runtime
configuration and dstack bootstrap/monitoring. Copy the hidden `.scrollsdkignore`
when starting from these examples.

The [beta.5a configuration notes](core-beta5a-configuration.md) remain a historical
reference for native settings and memory diagnostics; their in-place upgrade
instructions describe beta.5 to beta.5a only.

## Contracts images

Use the matching `dogeos69/scroll-stack-contracts` rc.4 images for the three
contracts operations:

| Operation | Image tag |
| --- | --- |
| Generate L2 genesis and configuration with the CLI | `gen-configs-dogeos-v0.3.0-rc.4` |
| Deploy contracts using `values/contracts-production.yaml` | `deploy-dogeos-v0.3.0-rc.4` |
| Verify contracts with the CLI | `verify-dogeos-v0.3.0-rc.4` |

The deployment example pins `image.tag`. The CLI selects the generation and
verification images separately; use a CLI release configured for rc.4 or supply
the matching explicit `--image-tag` to `setup gen-l2-artifacts` and
`setup verify-contracts`.

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
its Phase A script (`signer init`, `--print-identity`, then `signer init --identity`),
and import the descriptors with
`scrollsdk setup attestation-signer`. After genesis, send every partner the
complete `signer-policy-bundle/` produced by
`scrollsdk setup export-signer-policy`. Current dogeos-core requires canonical
protocol context in every signer mode, so partners start the service and run
`signer preflight` only after installing that bundle. Production partners use
`--require-production-ready` and keep their own RPC source sets and rotation
allowlists in the generated `attestation-signer.toml`.
External signers initiate signed polling and callbacks to TSO; they do not
provide a reachable signer endpoint. The kit publishes local preflight and
metrics ports only on host loopback by default.

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
