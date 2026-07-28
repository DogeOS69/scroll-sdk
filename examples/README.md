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
└── ProofCoordinator.toml                      (mock/production only)

withdrawal-processor/
└── WithdrawalProcessor.toml                  (native app config; TOML-owned)

values/
├── proof-coordinator-production.yaml          (mock/production only)
├── tso-service-production.yaml
└── withdrawal-processor-production.yaml      (K8s shape + secrets + switch only)

prover-worker-mock/
└── docker-compose/                            (generated only in mock mode)
```

The proof posture is selected once during setup, not in Make:

```bash
# Proof system off; attestation-signer uses direct-sign/dev_permissive policy.
scrollsdk setup proof-config --deployment-dir . --mode disabled

# Complete deterministic mock proof lifecycle.
scrollsdk setup proof-config --deployment-dir . --mode mock \
  --proof-artifact-base-url https://proofs.example.com/proof-topology

# Production-enforced proof lifecycle (supported, but validate separately).
scrollsdk setup proof-config --deployment-dir . --mode production \
  --proof-artifact-base-url https://proofs.example.com/proof-topology
```

Setup persists the chosen mode in `.data/doge-config.toml` and writes
`.data/proof-deployment.json`. That contract records the enabled components,
values files, dynamic Helm `--set-file` bindings, checksums, signer posture,
and mock-worker bundle identity. The Makefile does not interpret proof modes;
its install targets validate and consume the contract through `scrollsdk`.

The remaining proof-related Makefile variables are:

| variable | purpose |
|---|---|
| `AWS_REGION`, `EKS_CLUSTER`, `NETWORK_ALIAS` | required AWS/EKS inputs for `proof-aws-init` |
| `PROOF_AWS_INIT_FLAGS` | optional extra `proof-aws-init` flags |
| `PROOF_COORDINATOR_CHART`, `PROOF_COORDINATOR_CHART_VERSION` | proof-coordinator chart selection |
| `WITHDRAWAL_PROCESSOR_CHART`, `WITHDRAWAL_PROCESSOR_CHART_VERSION` | withdrawal-processor chart selection |

The corresponding targets are `make proof-aws-init`, `make proof-config`,
`make check-proof-deployment`, `make install-withdrawal-processor`,
`make install-proof-coordinator`, and `make install-tso`. `make proof-config`
is only a convenience wrapper that reuses the mode already persisted by setup;
`install-all` deliberately does not rerun setup. In disabled mode the Helm
adapter installs the withdrawal processor with proof runtime disabled and
skips proof-coordinator cleanly.

For the authoritative end-to-end order, partner descriptor/policy handoff,
three-state behavior, partner handoff, and lifecycle acceptance,
follow the
[DogeOS proof system operator runbook](https://github.com/DogeOS69/scroll-sdk-cli/blob/main/docs/proof-operator-runbook.md).
