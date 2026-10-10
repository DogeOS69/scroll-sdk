# Bridge operator deployment sequence

This is the current spec-based AWS/testnet workflow. It separates preparation,
external handoffs, installation, and acceptance. `setup apply` does not install
Helm releases or rent GPUs. A `waiting` result or healthy Pods is not acceptance.
Use the matching SDK and CLI revisions; the monitor external-store path requires
scroll-monitor 0.1.44-dogeos to be published, or a build of the matching local chart.

## 1. Fill the operator inputs

Create a private working directory outside both source repositories, then copy
`examples/deployment-spec.example.yaml` and `examples/deployment.env.example`
there as `deployment-spec.yaml` and `deployment.env`. Keep permissions private.

| Location | What the bridge operator supplies |
| --- | --- |
| spec: infrastructure | Instance name, AWS account/region, existing EKS cluster, namespace, two distinct blob/proof bucket names, create/reuse choices |
| spec: network and endpoints | Dogecoin network, reachable external RPC and matching internal Kubernetes route, L2 chain ID, base domain/DNS, reviewed compatible Reth images; review Sepolia RPC defaults for actual blob-broadcast support |
| spec: identities and custody | KMS create/reuse intent, CubeSigner role/key reference, three paired attestation/transport public identities from Governance, three recovery public keys |
| spec: bridge and contracts | Future block-height timelock, thresholds, fees, unique deployment salt, independent Dogecoin fee-vault recipient address |
| deployment.env | Owner public address, external/internal Dogecoin RPC credentials, local fee-wallet WIF, Vast.ai API key; database password only when referenced, optional Slack webhook |
| Existing tools/accounts | AWS profile, kube context, Docker, CLI/SDK, authenticated CubeSigner CLI, GitHub release access; EKS, ingress/DNS/certificate and External Secrets Operator infrastructure |

Do not hand-fill KMS-derived addresses/public keys, fee-wallet public key,
compiler identity, proof manifest checksum, genesis, or generated resource ARN
records. Apply derives them. Grafana needs no initial password input: it generates
one and puts it through the same external-secret-store flow as Dogecoin.
See [the spec reference](deployment-spec.md) for field semantics and key custody.

Run `plan` and `apply` from your private working directory. Keep the SDK checkout
as its sibling `../scroll-sdk`, or override `--sdk-dir` once when planning. Set `AWS_PROFILE`,
`AWS_REGION`, `KUBE_CONTEXT`, `NAMESPACE` and `SECRET_PREFIX` to the reviewed spec
values. Do not source deployment.env: the CLI parses it as literal data.
Set `DSTACK_NAMESPACE` to `dstackController.monitoring.namespace`, whose default
is `dstack-system`. This may differ from the business-service `NAMESPACE`.

## 2. Plan once; resume apply at external waits

```bash
scrollsdk setup plan
scrollsdk setup apply
```

The conventional paths are relative to the current working directory:

| Input/output | Default | Optional override |
| --- | --- | --- |
| Spec | `deployment-spec.yaml` | `plan --spec <file>` |
| Private environment | `deployment.env`, when present | `plan --env-file <file>` |
| SDK checkout | `../scroll-sdk` | `plan --sdk-dir <directory>` |
| Preparation output | `deployment/` | `plan --output <directory>` |
| Saved plan to apply | `deployment/` | `apply --dir <directory>` (also `--deployment-dir`) |

Apply reuses the environment file recorded by plan. If the default file is absent,
export the required variables in the process environment. An explicitly selected
missing environment file is an error. Paths do not need to be repeated on resume.

Review the plan's selected AWS operations before apply. Production mode does not
sign or broadcast funding payments on the operator's behalf.

1. At the wallet-funding wait, use the printed addresses and amounts. Fund the
   initial sequencer with exactly 0.42069 DOGE **at output vout 0**. Fund the fee
   wallet separately or place it later in that transaction. Keep change after the
   sequencer output. Inspect the final signed transaction before broadcasting;
   wallet output reordering is not an acceptable substitute for verification.
   Record real `sequencer` and `feeWallet` txid/vout pairs in the generated
   `.scrollsdk/inputs/bridge-funding.json` and wait for the required confirmations.
2. Run the same `setup apply` again. It validates funding and derives the final
   Bridge address. Fund that address with the required amount and exact OP_RETURN
   marker printed by apply. Add the `bridge` outpoint to the same JSON file,
   preserving the wallet entries, then wait for confirmations.
3. Run the same `setup apply` again. It generates genesis and Bridge-bound real
   proof materials, publishes them, prepares Secrets and exports signer policy.
4. At `signer-receipts`, deliver the versioned public policy bundle to each
   selected operator. They keep their private keys and RPC policy, verify the
   bundle, run their signer and return genuine validation evidence. Resume the
   same apply after importing the returned files at its printed input paths.
   A restricted/rotation-denied signer is not a full-capability receipt.

The two wallet/Bridge funding waits normally mean **one plan plus three apply
invocations to reach the partner handoff**, then another apply for returned
receipts. There can be further waits. Do not count these as a guarantee of five
commands to deploy the chain. Preserve the saved plan; changed intent needs a
new reviewed plan, not edits to generated TOML or frozen state.

## 3. Prepare an installation directory and upload Secrets

Partner validation may require live RPC/TSO services before the final receipt
step can finish. After apply reaches `signer-receipts`, use a private runtime copy
for installation. This keeps contract-address updates and provider reconciliation
from modifying the preparation workflow's fingerprinted files. Create it only
once; do not overwrite an existing runtime directory on resume:

```bash
test ! -e runtime
cp -a deployment runtime
cd runtime
scrollsdk setup cubesigner-refresh -N --doge-config .data/doge-config.toml
export DSTACK_NAMESPACE=dstack-system # Use your override if configured in the spec.
kubectl --context "$KUBE_CONTEXT" create namespace "$DSTACK_NAMESPACE" \
  --dry-run=client -o yaml | kubectl --context "$KUBE_CONTEXT" apply -f -
scrollsdk setup push-secrets -N --provider aws \
  --aws-region "$AWS_REGION" --aws-prefix "$SECRET_PREFIX" \
  --kube-context "$KUBE_CONTEXT" --namespace "$DSTACK_NAMESPACE"
```

An authenticated CubeSigner owner authorizes the session. The command writes it
under `secrets/`; it is not a spec value. Full push includes Dogecoin RPC and
Grafana ENV credentials in AWS Secrets Manager. The chart's ExternalSecret
creates the corresponding Kubernetes Secret. Configure store authentication as
for Dogecoin. Dstack's generated controller credentials use its existing explicit
Kubernetes publication path, so the context/namespace flags are required.
For this combined upload, `--namespace` selects the dstack Secret destination;
the other service secrets go to the selected AWS/Vault store. Create the dstack
namespace before uploading, rather than waiting for the later Helm installation.
If `preparation.secretUpload` already completed, do not upload again needlessly.

If Slack is enabled, also run `scrollsdk setup monitoring-secrets --apply
--kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE"`. It reads the environment
file recorded in the copied plan. This applies the Slack Secret only; Grafana
still uses the store.

## 4. Install base services, then contracts, then bridge services

Run these from the private runtime directory. Exporting the destination also
passes it to each Makefile target. Check rollout/health at each stage and stop
on failure; do not run this sequence unattended past failed checks.

```bash
export KUBE_CONTEXT NAMESPACE DSTACK_NAMESPACE
make install-scroll-monitor
kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" wait \
  --for=condition=Ready externalsecret/grafana-admin --timeout=120s
make install-scroll-common
make install-l1-interface
make install-l2-reth-bootnode
make install-l2-reth-rpc
make install-l2-reth-sequencer
```

If the matching monitor chart has not been published yet, build its dependencies
and replace only the monitor installation command above with the local chart:

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm dependency build ../../scroll-sdk/charts/scroll-monitor
make install-scroll-monitor SCROLL_MONITOR_CHART=../../scroll-sdk/charts/scroll-monitor
```

If the spec uses an already-running shadowfork, use that selected service; do not
install another Dogecoin node and silently switch networks. If deploying a new
Dogecoin node, install/bootstrap it first using its dedicated guide.
Verify all nodes agree on block zero and the selected chain ID. Required genesis
predeploys must exist. Empty blocks remain disabled.

```bash
make install-contracts
```

Wait for transaction receipts and verify deployed contracts, owner assignments,
and bindings. A timed-out or interrupted deployment is a reconciliation task:
do not blindly repeat `install-contracts` or `install-all` after ownership moves.
Retain the deployment logs/broadcast records. After successful deployment, update
the runtime values from the actual contract output:

```bash
scrollsdk setup prep-charts -N
make install-tso
make install-cubesigner-signer
make install-withdrawal-processor
make install-proof-coordinator
make install-eager-materializer
make install-eth-da-submitter
make install-fee-oracle
make install-dstack-controller
make install-frontends
```

The eager target requires an enabled generated eager contract; omit it when not
selected. Provision transaction funds to the generated DA submitter address on
Sepolia and the fee-oracle address on L2 using the operator's wallet. This is
separate from Dogecoin Bridge funding. Start the three partner signers against
the exported policy and live TSO. After contracts and bridge services are verified:

```bash
make start-l1-sync
```

Blockscout is optional and requires its database. Do not use `install-all` for
this staged flow: it also installs optional components and invokes initialization.

## 5. Start the selected GPU worker and collect partner evidence

```bash
scrollsdk setup proof-worker
```

`proof-worker`, `proof-config-check` and `monitoring-secrets` default to the
current deployment directory (`.`); `--deployment-dir` is only an override.
Use the exact bundle path, bundle ID and resource paths reported by this command.
On a compatible GPU host, verify the transferred bundle, then use its launcher:

```bash
scrollsdk setup proof-worker-check --bundle-dir "$WORKER_BUNDLE_DIR" \
  --expected-bundle-id "$WORKER_BUNDLE_ID"
cd "$WORKER_BUNDLE_DIR"
./prover-worker-compose config --quiet
./prover-worker-compose up -d prover-worker
```

For dstack/Vast, keep running from this same `runtime/` directory:

```bash
scrollsdk setup proof-workers plan
scrollsdk setup proof-workers apply
scrollsdk setup proof-workers status
# Explicit cancellation; repeat until all owned fleets are terminated:
scrollsdk setup proof-workers destroy
```

`plan` reads the saved spec intent and compiled Worker contract, locks the exact
image/GPU/resources/limits, and shows the rental envelope without allocating.
Only the separate GPU `apply` submits billable resources, after first starting
an independent in-cluster cleanup watchdog. Closing the CLI does not remove that
watchdog. See [GPU capacity and lifecycle](proof-workers.md) for defaults,
an eight-hour example, safe recovery, and the limits of cost/deletion guarantees.
Do not destroy the controller/cluster before confirming all rented resources are gone.

Partner operators follow [the signer guide](../partner-kit/attestation-signer/README.md).
Return receipts against the exact exported policy bundle to the original
preparation directory. Return to the private working directory (`cd ..` from
`runtime/`), then run `scrollsdk setup apply` again. Regeneration with accepted
evidence does not automatically upgrade already installed runtime releases: review and reconcile the resulting runtime values.
Never fabricate a receipt to turn `waiting` into `prepared`.

## 6. Acceptance criteria

Check actual progress, not just Pod readiness: confirmed/finalized Ethereum DA
transactions, successful chunk/batch/bridge proofs, WP replay/AdvanceL1/AdvanceL2,
TSO signed transactions and Dogecoin confirmation, then a small deposit and
withdrawal with expected fees and final balances. Frontend/TLS, Grafana targets,
and selected notification delivery are separate checks.

The October rehearsal exposed two unresolved runtime blockers: ambiguous blob
broadcasts on the selected RPC, and a worker bridge-verifier genesis profile
mismatch for its existing vout-1 deployment. Fixes in SDK/CLI and vout-0 funding
validation do not by themselves prove these runtime issues are resolved. A fresh
end-to-end acceptance run remains required before declaring this path complete.
