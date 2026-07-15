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

## Proof release files

Production proof configuration uses a fixed working-directory layout shared by
the example Makefile and `scrollsdk setup proof-config`:

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
├── attestation-signer-production.yaml        (+ expanded -0.yaml, -1.yaml, ...)
├── proof-coordinator-production.yaml
└── withdrawal-processor-production.yaml      (K8s shape + secrets + switch only)
```

`withdrawal-processor/WithdrawalProcessor.toml` holds ALL application
configuration (no more DOGEOS_WITHDRAWAL_* env sprawl in values):
`scrollsdk setup prep-charts` merges config.toml-derived facts into its managed
deployment block — operator tuning of other keys inside the block survives —
and `scrollsdk setup proof-config` owns the proof block. Both install targets
pass the native TOML files to Helm via `--set-file`. Secrets and the
`withdrawalProof.enabled` activation switch remain in values/ENV.

After staging the released manifests, run
`make proof-config SIGNER_PROOF_ARTIFACT_BASE_URL=https://...`. The CLI
replaces only the marked verifier block in the native TOML and preserves all
manually maintained sections, and additionally projects the signer envelope
policy (`allowedProofTriples`, `maxProofArtifacts`, `proofArtifact.fetchMode`)
into the attestation-signer values template and every expanded instance file —
re-run `make install-attestation-signers` afterwards. Deployment passes the
coordinator TOML to Helm with
`--set-file proofCoordinator.config.content=proof-coordinator/ProofCoordinator.toml`.
Explicit path flags are only necessary for a non-standard layout.

Two opt-in flags extend the pass (`PROOF_CONFIG_FLAGS` in the Makefile):

- `--scaffold-coordinator-config` generates `proof-coordinator/ProofCoordinator.toml`
  from the prepared withdrawal-processor values when the file does not exist
  yet (never overwrites an existing config). Requires prep-charts to have
  resolved all RPC/chain-id/blob-source values first.
- `--enable-withdrawal-proof` flips `withdrawalProof.enabled: true` after
  staging. Without it the activation switch is preserved as-is; leave it off
  until coordinator readiness, S3 identity, released verifier artifacts, and an
  external prover worker have all passed their own preflight.
