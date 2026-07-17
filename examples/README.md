# Scroll SDK Helper Scripts

This directory contains helper files examples and scripts for managing and interacting with your Scroll SDK deployment.

For additional, more robust helper scripts, checkout the [scroll-sdk-cli](https://github.com/scroll-tech/scroll-sdk-cli).

## Example Files
1. `Makefile.example`: A basic makefile for quickly installing and deleting the charts necessary for the Scroll SDK.
2. `config.toml.example`: A template config.toml file for new deployments. A good starting point for filling out chain-specific details or using the Scroll SDK CLI tool.

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

The example Makefile and `scrollsdk` share the following conventional paths.
Using this layout avoids per-file path flags:

```text
proof-artifacts/
├── release.json
└── manifests/
    ├── scroll-chunk.json
    ├── scroll-batch.json
    └── bridge-transition.json

proof-coordinator/
└── ProofCoordinator.toml

withdrawal-processor/
└── WithdrawalProcessor.toml                  (native app config; TOML-owned)

values/
├── proof-coordinator-production.yaml
├── tso-service-production.yaml
└── withdrawal-processor-production.yaml      (K8s shape + secrets + switch only)

prover-worker-mock/
└── docker-compose/                            (generated only in mock mode)
```

The proof-related Makefile variables are:

| variable | purpose |
|---|---|
| `PROVING_MODE` | `production` or the e2e-harness-compatible `mock` lane |
| `PROOF_ARTIFACT_BASE_URL` | credential-free HTTP(S) GET root used by proof consumers |
| `PROOF_CONFIG_FLAGS` | optional extra `scrollsdk setup proof-config` flags |
| `AWS_REGION`, `EKS_CLUSTER`, `NETWORK_ALIAS` | required AWS/EKS inputs for `proof-aws-init` |
| `PROOF_AWS_INIT_FLAGS` | optional extra `proof-aws-init` flags |
| `PROOF_COORDINATOR_CONFIG` | native coordinator TOML passed to Helm with `--set-file` |
| `WITHDRAWAL_PROCESSOR_CONFIG` | native withdrawal-processor TOML passed to Helm with `--set-file` |

The corresponding targets are `make proof-aws-init`, `make proof-config`,
`make install-withdrawal-processor`, `make install-proof-coordinator`, and
`make install-tso`. The Makefile is the executable chart interface; it is not
the deployment runbook.

For the authoritative end-to-end order, partner descriptor/policy handoff,
activation gates, mock-versus-production behavior, and lifecycle acceptance,
follow the
[DogeOS proof system operator runbook](https://github.com/DogeOS69/scroll-sdk-cli/blob/main/docs/proof-operator-runbook.md).
