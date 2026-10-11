# DeploymentSpec configuration coverage audit

> Current contracts default (2026-10-10): `dogeos-v0.3.0-rc.5`
> (`be94674ec64383c1cea61770e64d3b1586bd298e`). The rc.4 references below
> retain the original audit and rehearsal baseline; they do not certify an rc.5
> container rehearsal. Current image selections are in [the examples](../examples/README.md).

Audit date: 2026-10-09. Scope: a new deployment using core beta.6 and contracts
rc.4, with explicit local/KMS and proof disabled/active, mock/real,
observe/enforce choices. Existing-bridge upgrades are a separate lifecycle.

Confirmed deployment policy: **30,000,000 gas and a 2,000 ms block interval**.
The operator confirmed these targets during this audit. The SDK example's
1,400 ms payload build window is recorded separately as an existing example
setting; it is not an additional operator confirmation.

**Finding: DeploymentSpec is a working bootstrap input, but is not yet a
complete alternative to the individual setup commands.** Some declared inputs
are lost, some operational choices have no spec representation, and the values
generator does not select the same defaults as the maintained SDK examples.
Successful YAML/TOML generation does not establish service startup readiness.

This is a service-level configuration contract and input-coverage audit. Rows
group related runtime fields; it is not a claim that every internal tuning
field, migration, or provider backend has been exhaustively tested. Explicit
unverified boundaries are listed below rather than counted as coverage.

## Baselines and source precedence

| Component | Audited baseline | Meaning |
| --- | --- | --- |
| dogeos-core | `v0.3.0-beta.6`, `56007d3c413ad07f33d0e08b272004089c911f78` | Runtime input authority for core services and the topology compiler. |
| scroll-sdk | `c8f7871b6f6ad0d19504342558d96b7e39608d4d` | Examples, chart wiring, partner kit and Makefile. |
| scroll-sdk-cli | merged #77, `4355e19e91db8433d28a8727e71fdb4fe1704232` | Spec schema, generators and setup commands. Probes ran on `4dc29829f7ccbf7b575dbe842867e380645088a0`, whose Git tree is identical to the merge. |
| scroll-contracts | `dogeos-v0.3.0-rc.4`, `b34129ae776f8608193f1641de7041adcbdbf32d` | Contracts configuration and genesis generation contract. The sibling checkout's `main` is older and was not used as this authority. |
| Reth / rollup-node | No immutable image is selected in the SDK examples or the spec fallback (`TODO_TAG_TO_REPLACE`). | Chart/CLI projection inspected; binary-version compatibility remains unverified. Do not substitute an arbitrary local checkout for the eventual deployed image. |
| dstack | SDK chart defaults: `0.21.5`, digest `sha256:a502b38014dc9730ad712f60c067b84a00a4cf091982b81f9982fdc60ac6852b` | Controller chart and CLI contract inspected. Native backend/provider behavior was not exercised. |

Use the selected binary's parsing, defaults, validation and file dependencies
as the runtime authority. Next inspect chart templates and entrypoints to see
what reaches the binary. Examples and handbooks describe deployment policy;
they are not substitutes for either check. The command path is also subject to
this audit and is not assumed correct merely because it is interactive.

CLI source map, pinned to the merged revision: [DeploymentSpec types][cli-spec],
[bootstrap command][cli-bootstrap], [shared TOML generation][cli-generator],
[direct values generation][cli-values], [chart reconciliation][cli-prep],
[identity preparation][cli-keystore], [descriptor import][cli-attestation],
[proof source selection][cli-proof-intent], and [Bridge initialization][cli-bridge].
These distinguish a field's declaration from its actual consumer and handoff.

The supplied [production service input inventory at `2830668`][upstream-inventory]
is a useful checklist, but is **not a beta.6 specification**. Its commit and
beta.6 diverge from a common ancestor; this is not a simple latest-versus-old
documentation comparison. The file is absent from the beta.6 tree.

| Inventory item at `2830668` | beta.6 authority / correction |
| --- | --- |
| WP signer table describes singular `role` and a service `uri`. | [WP config][core-wp] requires `roles` with one role; `delivery`, `transport_pubkey` and an optional URI distinguish push/pull. External attestation pull entries have no URI. |
| Attestation `[tso]` lists `url` only. | [Signer public parser][core-signer-cli] also accepts `delivery` and `transport_key_file`; the pull identity includes a separate transport public key. |
| Submitter `segmentation_sidecar.s3` is a boolean sharing the DA archive. | [Submitter config][core-da] uses a separate S3 table with bucket, region, prefix and optional endpoint/path-style settings. The old boolean is invalid. |
| Network guidance describes mutual reachability without the signed pull edge. | External partners dial the TSO; they do not supply a public inbound signing endpoint. Internal CubeSigner remains push. See [beta.6 rollout notes](../examples/core-beta6-configuration.md). |
| Startup dependency and field inventories for other services. | Use as a checklist, then check each beta.6 consumer. Agreement in a selected config file does not certify every surrounding execution path. |

## What counts as a complete spec path

The following are legitimate dependencies, not missing spec fields:

- External facts: existing RPCs, signer descriptors, resource IDs and confirmed
  funding inputs. Their references and ownership must be explicit.
- Generated state: persistent identities, KMS public-key-derived addresses,
  deployment salt/seed and initialization results. Re-running generation must
  preserve the selected identity.
- Derived artifacts: genesis, protocol context, proof materials, compiled
  topology, policy bundles and publication receipts.
- Deliberate defaults: ports, internal service discovery or other supported
  policy defaults that need not be exposed as independent user choices.

A complete spec path can use multiple commands. It must not need an extra
interactive answer, an undocumented file edit, or an unrecorded choice to
recover an intent already supplied in the spec. Provider mutations, chain
transactions and publication remain explicit execution stages.

The trace to audit is:

```text
service input and required condition
  <- native config / env / argument / mounted artifact
  <- renderer + recorded identities/resource facts/artifacts
  <- spec intent or an explicit external-input reference
```

## Service inventory and configuration coverage

Status: **mapped** means a concrete projection exists, not that production
startup was tested; **staged** means an explicit later artifact/resource step is
required; **gap** means declared intent is lost or a necessary choice lacks a
spec route; **external** means another operator/system owns the input;
**unverified** marks a version or execution boundary not established here.

### Network, chain identity and contracts

| Runtime input / condition | Spec intent or other authority | Production path and command counterpart | Status / issue |
| --- | --- | --- | --- |
| Dogecoin network; L2 and Ethereum DA chain identities | `dogecoin.network`, `network.l2ChainId`, `ethereumDa.chain/chainId`; synthetic L1 ID is distinct | [TOML generator][cli-generator] -> protocol seed and config; `setup doge-config` -> same deployment state; context later binds identities | Mapped; final context still required. |
| Operator Dogecoin RPC and credentials | `dogecoin.externalRpc`; secret references | `.data/doge-config.toml.rpc`, `setup_defaults.toml`; `setup doge-config` / `setup domains` | Mapped. Public/operator and cluster-local RPCs have different consumers. |
| In-cluster Dogecoin credentials and service discovery | `dogecoin.clusterRpc`, `dogecoin.kubernetes.*` | Direct values generation vs doge-config-driven `prep-charts` | **Gap F03:** custom service/port reaches direct values but not generated doge-config. |
| Public hosts, HTTP/HTTPS, external RPC/explorer links | `frontend.baseDomain`, `hosts`, `subdomains`, `externalUrls`, `protocol` | `config.toml` ingress/frontend -> values; `setup domains` | Basic host projection verified; TLS/ALB/certificate policy is a separate deployment input. |
| Deployer, owner, fee-oracle writer; initial allocations and fees | `accounts.*`, `genesis.*`, `bridge.fees`, `bridge.feeRecipient`, `contracts.gasOracle` | `config.toml` -> rc.4 contracts generator; `gen-keystore`, `gen-l2-artifacts` | Staged. An owner address is not evidence of control; private material stays outside tracked files. |
| Genesis sequencer signer address | Persisted index-0 Reth signer identity | `gen-l2-artifacts` synchronizes the compatibility signer address from doge-config before contracts generation | Staged; spec metadata does not replace creating/importing the actual signer. |
| Genesis gas limit, timestamp, L2 base fee overhead | rc.4 [template][contracts-template] and [configuration reader][contracts-reader]; SDK launch policy | Contracts supports these inputs; spec `GenesisConfig` and generation do not project gas limit/base fee overhead | **Gap F08:** SDK launch values cannot be fully expressed. Omission is not itself a parser failure; rc.4 has fallback behavior. Timestamp can use rc.4's deterministic default. |
| `genesis.json`, contract addresses, generated frontend contract data | Contracts image/revision + complete inputs above | `gen-l2-artifacts` -> `values/genesis.yaml` and generated config; Bridge preparation extracts `.data/genesis.json` | Staged. No genesis is produced by `generate-from-spec` itself. |
| Dogecoin full node or external provider | Network/RPC intent; node operational values | SDK Dogecoin chart / existing provider; bootstrap through `setup domains` where applicable | Partial. Storage, sizing, networking and node lifecycle still rely on chart values/provider setup. |
| Ethereum execution/beacon source or local devnet | `ethereumDa.chain`, `l1RpcUrl`, `beaconRpcUrl`, image overrides | Direct devnet values and downstream DA RPC settings | Mapped basic wiring; actual chain/RPC reachability remains external. |

### Reth, DA submission, L1 Interface and fee oracle

| Runtime input / condition | Spec intent or other authority | Production path and command counterpart | Status / issue |
| --- | --- | --- | --- |
| Reth role, instance count and chain | `infrastructure.sequencerCount/bootnodeCount`, `network.l2ChainId` | `gen-keystore --from-spec` reads counts; Reth setup state -> indexed `prep-charts` values | Staged. Direct values generator emits base role files, not prepared identities for all instances. |
| Reth nodekey and local/KMS block signer | Persistent secret/identity references; backend choice | `gen-keystore --service sequencer-reth` / `bootnode-reth`, Reth setup helpers | **Gap F02:** current spec cannot declare the complete per-service backend/import plan. |
| Reth genesis, L1 RPC, trusted peers, public bootnode address | Generated genesis; known service rules; node identities/LB facts | [Reth chart](../charts/l2-reth/values.yaml); `prep-charts`, `bootnode-public-p2p`, `gen-rpc-package` | Staged/external. Public endpoint discovery must occur after infrastructure exists. |
| Reth image, builder gas limit, block interval, payload budget, resources/PVC | `images.services.l2*`; otherwise hardcoded values/example policy | [Values generator][cli-values] vs maintained SDK examples | **F01/F08:** unspecified image and divergent launch defaults; generic spec lacks these operational overrides. Binary acceptance unverified. |
| Submitter protocol context, genesis schedule, L2 and Ethereum RPC | Generated artifacts; `ethereumDa.l1RpcUrl/l2RpcUrl` | [Submitter][core-da]; generator then `prep-charts` mounts context/genesis | **F04:** custom L2 RPC is emitted directly but prep derives its RPC from `config.toml.general.L2_RPC_ENDPOINT`. |
| Submitter local/KMS identity; WP expected batcher | `accounts.l1CommitSender` only covers local/public account input; actual backend/facts belong to signer state | `gen-keystore --service eth-da-submitter` -> signer state -> submitter env / WP `expected_batchers` | **F02**, staged identity propagation. These two consumers must agree on the address. |
| Submitter confirmations, finalization, fees, fetch limits, DB paths | `ethereumDa.confirmationDepth`, `finalizationDepth`, `maxFeePerGasWei`, etc. | Direct values generator vs default TOML path | **Gap F04:** sampled overrides change direct values but none of the four TOMLs. |
| Submitter batch cutover and publication budgets | `ethereumDa.batch`, `publish`, `l2StartBlockNumber` | Persisted into doge-config; prep reconciles supported fields; genesis supplies fresh-chain roots | Mapped/staged. New-bridge and continuation intent must not be combined. |
| Raw blob archive, reader URL, prefix, IAM writer | `ethereumDa.blobArchive.s3` + provider facts | `setup eth-da-submitter`, optional `artifact-access`; DA writer and WP/L1I/PC readers | Mapped location; provisioning/permissions are separate. **F09** for missing bucket separation validation. |
| Segmentation sidecar target | Proof store/topology, distinct from raw blob archive | Compiler/reconciler -> beta.6 `segmentation_sidecar.s3.*`; PC must read matching bucket/prefix | Staged. A direct archive setting alone does not configure the complete proof sidecar path. |
| L1I context, genesis, private replay/application DB, replay initialization | Bridge outputs; `bridge.freshGenesisInit`; service-owned persistent volumes | [L1I config][core-l1i], `bridge-init` -> `prep-charts` | Mapped/staged; replay and DB contents are state, not interchangeable generated files. |
| L1I Dogecoin indexer height, confirmations, Ethereum/blob sources | `bridge.confirmationsRequired`, derived heights, DA inputs | Direct values / doge-config -> `prep-charts` | Partial. Discovery handoff is F03; generated placeholder/default heights must be replaced with actual initialization facts. |
| Fee oracle L2 RPC/chain, deployed oracle address, authorized writer | `network`, generated contract addresses, `accounts.l2GasOracleSender` | [Fee config][core-fee]; `gen-keystore --service fee-oracle`, `prep-charts`, secrets | Staged; KMS selection gap F02. |
| Fee oracle live writes, quote quorum/freshness, gas-price/update policy | SDK production example versus binary defaults | Example explicitly selects `contract_write_mode=live`; values generator only adds DA RPC and generic fee settings | **Gap F08:** spec has no fee-oracle operational policy block; direct generation omits live selection. Binary default is `dry_run` absent another override. |

### Bridge, TSO and signing

| Runtime input / condition | Spec intent or other authority | Production path and command counterpart | Status / issue |
| --- | --- | --- | --- |
| Bridge fee/recovery inputs, timelock, seed and funding targets | `bridge.*`; supplied secret reference | Generated setup defaults; `bridge-init` stages | Partial/staged. Defaults contain funding UTXO placeholders; real confirmed UTXOs are an external input, not a computable default. |
| Initial attestation cohort and threshold | `bridge.initialAttestationKeyset` | Actual descriptor import uses `setup attestation-signer --active-signer-ids/--threshold` | **Gap F05:** spec keyset changes have no effect on generated files; impossible threshold is accepted by spec validation. |
| Attestation public/transport identities | Partner-generated descriptor, not a private key in the operator spec | `signer init`, binary `--print-identity`, `setup attestation-signer` | External/staged. Spec has no descriptor-source binding; explicitly importing public descriptors is legitimate, but selection must preserve spec intent. |
| Canonical Bridge script/context, genesis outpoint/transaction, replay heights | Actual initialization output | `bridge-init` prepare/setup/info/fund/context -> WP/L1I/DA/signers/proof | Staged and stateful. Setup/fund may broadcast transactions; config regeneration must not repeat them. |
| TSO network, WP URL, port, durable journal | Network and service discovery defaults | [TSO args][core-tso] -> generated values/volume | Basic mapping. Persistence and restart behavior require runtime verification. |
| Custom TSO URL | `signing.tsoServiceUrl` | Generated values use other/default URLs; partner URL derivation is separate | **Gap F06:** the declared field has no effect on generated files. Public TSO host derivation and internal push URL remain valid separate concepts. |
| WP signer overlay: role, public key, transport key, push/pull, internal URI | Imported descriptor/CubeSigner roles and network | `prep-charts` -> `tsoSigners` -> [chart TOML](../charts/withdrawal-processor/templates/configmap-tso-signers.yaml) | Mapped/staged on the command path; beta.6 image mismatch is F01 on direct values. |
| Partner signer RPC trust sets, allowlists, local/KMS key, transport secret, local DB | Partner-owned reviewed config and identity | [Public signer parser][core-signer-cli], partner-kit, `signer init` / exported policy handoff | External by design. Operator spec should reference public descriptor/policy handoff, not absorb partner credentials or trust decisions. |
| Partner policy context, artifact origins, proof identities/materials, approved release | Selected proof contract and receipts, partner approvals | `export-signer-policy` -> partner Phase B; preflight afterwards | Staged; fresh Phase A directory permission defect was reproduced in the earlier rehearsal (F11). |
| CubeSigner role/key/session, TSO, context and writable session cache | `signing.cubesigner.roles`; external login/session | `cubesigner-init`, `cubesigner-refresh`, `gen-secrets`, `prep-charts` | Partial/staged. Spec can import public role/key metadata; it does not provision an authenticated session. |
| CubeSigner Wasm policy, attachment, receipt and live evidence | `signing.cubesigner.mode`, `policyReceipts`, `productionPolicy` | [Server configuration][core-cube], policy build/deploy and prep | Staged. Transport-only readiness does not establish production verification. |

### Withdrawal and proof services

| Runtime input / condition | Spec intent or other authority | Production path and command counterpart | Status / issue |
| --- | --- | --- | --- |
| WP network/RPC/indexers, native contract addresses, fees, TSO, Bridge script and signing secrets | Shared spec inputs + actual genesis/Bridge outputs | [WP parser][core-wp], `prep-charts` and `gen-secrets` | Partial/staged; native base config, identity and Bridge inputs must exist. Direct values alone are not a complete WP configuration. |
| WP proof-work API/auth, verifier identities, artifact transport, materializers and activation | `proofTopology`, proof materials and publication receipts | [Core topology source][core-topology] -> compiler -> WP native config / values | Staged, with source-handoff gap F07. Keep real/enforce validation separate from mock/observe evidence. |
| WP private replay/indexer/control-plane databases and fresh initialization | Bridge lifecycle plus explicit persistent volumes | Example defaults/native config, `bridge-init` recorded lifecycle, prep | Mapped basic lifecycle; storage ownership/sizing outside generic spec is F10. |
| Proof mode/generation/enforcement and observe deadline | `proofTopology.mode/generation/enforcement/observeRealProofDeadlineMs` | Explicit `prep-charts --spec`, conventional spec discovery, or doge-config `[proof_topology]` | Mapped only while the intent source is retained. **F07:** custom external spec/output path has no automatic handoff. |
| Proof compiler, identity input and release/worker images | `proofTopology.compiler`, `deployment.*Image`, materials receipts | `proof-release-prepare`, `proof-materials`, topology compiler, `proof-config prepare` | Staged. Immutable image references do not by themselves provide matching local material files. |
| PC WP URL, service ID, API auth, artifact store, service accounts | `proofCoordinator.*`, `proofArtifacts.s3`, topology | [PC service parser][core-pc], `proof-aws-init`, compiler/reconciler | Partial/staged. Cross-store agreement is checked in prep; worker reachability and IAM need integration checks. |
| PC real materializers, verification keys, protocol context and blob/RPC inputs | Generated/baked artifacts and runtime facts | Compiler writes native `ProofCoordinator.toml` and mounts | Staged. Direct values generator does not bootstrap this native file. |
| Worker family identities, vmexe/VK/context, coordinator token, launch backend and resources | `proofTopology.active.realScroll`, `deployment.*`, worker image receipt | [Worker config][core-worker], compiler, `proof-worker`, generated K8s or Compose bundle | Staged. No Worker is expected for in-process mock generation; image/GPU compatibility still requires validation. |
| Eager materializer service loop, S3, L2 RPC/genesis, statement namespace and scratch state | `proofTopology.deployment.eagerMaterializer`, compiled proof store/materials | [Eager config][core-eager], compiler -> optional generated values | Staged/conditional; not an always-required direct values output. |
| Proof program publication and authenticated/anonymous readback | Prepared publication plan, temporary external credentials | `proof-config publish --apply` / `proof-bundle-publish`, receipt binding | Execution stage. A generated config is not a successful publication or readback. |
| Capacity manager policy, limits, provider, worker command/image/token and durable state | Independently supplied capacity policy and provider setup | [Capacity args/config][core-capacity] | Optional **coverage gap F10**: no corresponding DeploymentSpec block or standard SDK release generation. Installing dstack is not installing/configuring capacity management. |

### Platform, monitoring and companion services

| Runtime input / condition | Spec intent or other authority | Production path and command counterpart | Status / issue |
| --- | --- | --- | --- |
| S3/IRSA and secret backend identity | `infrastructure.provider/aws/gcp/local`, store coordinates, explicit account facts | Direct ExternalSecret generation; `proof-aws-init`, signer provisioning, `push-secrets` | Partial. Infrastructure metadata does not automatically become a complete provisioning/identity plan (F02). |
| Snapshot location and continuation inputs | `snapshots.s3`, explicit restored state and continuation intent | doge-config preserves snapshot location; restore orchestration is separate | Location mapped; restore correctness is outside this new-bridge audit. |
| Application databases, admin connection and generated service credentials | `database.admin`; chosen DB services | `db-init` -> local config/secrets; `gen-secrets`/publication | Staged. DB initialization changes external state. Old `database.credentials/databases` fields are not a general database lifecycle spec. |
| dstack controller image, DB type, Secret refs, ingress, resources and storage | `dstackController.*` | [Controller contract](../charts/dstack-controller/README.md), spec generator and `prep-charts --dstack-only` | Mapped; probe confirms controller values and monitor overlay are emitted. |
| dstack native backends/project, provider credentials, encryption/admin state | Existing Secret references or `dstack-config` private input files/state | `dstack-config --spec` can update references; DB/Secret generation and push follow | External/staged. Current spec references the resulting native config rather than modelling a provider/fleet provisioning plan. |
| Base scroll-monitor, scrape targets, balance accounts/RPCs, Grafana credentials | Existing SDK monitor template + generated public identities; doge-config monitoring state | `prep-charts` reconciles existing monitor values; dstack produces an overlay | **Gap F10:** spec generation emits no base `scroll-monitor-production.yaml`, even with dstack enabled. |
| Alerts, notification destinations, status page, probes, independent monitoring | Operator policy, private Secret references, dedicated CLI setup | SDK monitoring examples and `setup status-page`, TLS and related tooling | Optional external/partial coverage. No complete generic spec policy block. |
| Frontends, Blockscout, contract deploy/verify jobs | `frontend`, `network`, `contracts`, DB outputs, images | Direct values, contracts-generated frontend data, `db-init`, `verify-contracts` | Mapped/staged; native application startup and external explorer behavior not exercised here. |
| Metrics exporter, activity helper, optional legacy charts | SDK selected service scope and templates | Makefile and examples | Not all are direct spec outputs. Legacy Blockbook/retired charts are not requirements merely because files/targets remain. |
| Namespace, PVC sizing/class, node placement, replicas, TLS/Ingress/ALB/WAF | Explicit installation/operational policy; selective dstack/proof spec fields | Chart values, Makefile variables and dedicated setup commands | **F10:** coverage is selective, not a generic per-service deployment policy model. Template pins and ownership must be explicit. |

## Reproduced findings and repair order

Priority describes configuration correctness, not a claim that a production
incident occurred. R = reproduced by this audit; S = confirmed by source
inspection; P = reproduced in the preceding local rehearsal.

| ID | Priority / evidence | Finding and consequence | Repair direction / acceptance |
| --- | --- | --- | --- |
| F01 | P1, R/P/S | Direct values fall back to WP/L1I beta.5c, CubeSigner beta.2, submitter `latest`, fee-oracle and Reth TODO tags. WP beta.5c cannot consume the beta.6 signer shape generated later. | One explicit release selection shared by both paths; reject unresolved image placeholders for a deployable plan. Reth must have its own pinned release. |
| F02 | P1, S | No complete spec block for managed signer backend, existing KMS key/role, import/create policy and per-node identity. `gen-keystore --from-spec` only reads node counts. | Add explicit identity intent and external secret/resource references; persist resolved facts and reuse them. Verify no unexpected key/backend replacement. |
| F03 | P1, R/S | `dogecoin.kubernetes.serviceName/rpcPort` affect direct values but are absent from generated doge-config. Prep resolves several consumers from doge-config. | Preserve discovery inputs in the shared model. Assert identical cluster RPC after generation and reconciliation, including a non-default namespace/service/port scenario. |
| F04 | P1, R/S | Six sampled DA overrides change direct values but leave all four generated TOMLs unchanged. Custom submitter L2 RPC is subsequently sourced from the fixed general RPC mapping by prep. | Persist supported DA intent once and share projections. Verify each overridden field survives the config-only and with-values paths plus prep. Do not claim all fields are overwritten; some simply remain template-dependent. |
| F05 | P1, R/S | Changing `initialAttestationKeyset` changes no generated file. A threshold of 99 for one selected signer passes spec validation. Descriptor import instead uses explicit command flags or its own default. | Bind descriptor sources and active-set selection to spec; validate membership, uniqueness and threshold; preserve selection through Bridge preparation. Never derive partner private keys from operator intent. |
| F06 | P2, R/S | Changing `signing.tsoServiceUrl` changes no generated file. | Implement clearly defined internal/public semantics, or reject/deprecate the unused field with actionable guidance. |
| F07 | P1, R/S | `generate-from-spec --spec /outside/intent.yaml --output deployment` does not copy/bind the spec or persist proof topology in doge-config. Implicit proof lookup in the output finds nothing. | Record a stable intent reference or persist normalized intent; include its digest/dependencies. Explicit `prep-charts --spec` or a conventional `deployment-spec.yaml` already works and is not a missing compiler feature. |
| F08 | P1, R/S | Direct Reth defaults are 10M gas / 3000 ms blocks / 800 ms build window; the confirmed target is 30M gas / 2000 ms blocks, and SDK examples use a 1400 ms build window. Spec lacks rc.4 genesis gas-limit/base-fee-overhead intent and fee-oracle live/update policy. | Make both paths default to the confirmed 30M gas / 2000 ms target, including matching genesis gas limit. Define a versioned preset and explicit supported overrides; record the build-window and fee policies separately. |
| F09 | P1, R/P | Spec validation accepts the same bucket for DA and proof once all required archive fields are supplied; prior prep rehearsal also accepted it. A misspelled DA field is accepted and ignored. | Enforce the requested distinct-bucket deployment policy and strict unknown-field validation. Distinguish SDK policy from what the core binary itself enforces. |
| F10 | P2, R/S | Values generation alone does not provide WP/PC native bases, monitor base, or every selected installation input. Generic resource/edge/capacity intent is incomplete. | Declare a pinned template/preset dependency and required service scope; bootstrap inputs or fail early with a complete missing-input list. Derived genesis/Worker files must be produced at their proper stages, not filled with dummy data. |
| F11 | P2, P | Fresh partner Phase A may leave `policy/` owned by root; a non-root Phase B cannot copy context. | Pre-create the bind directory as the operator in both SDK and CLI-generated instructions. This is a downstream installer defect, not a spec schema defect. |

Repair F01/F03/F04/F05/F08 first because they can change the meaning or
compatibility of generated configuration. In parallel design terms, F02/F07
define the identity/state handoff needed for a complete path. F09 should gate
both entrypoints. F10 should make template and operational-policy ownership
explicit; optional platform capabilities need not block a correctly scoped
core-only deployment. F11 can be fixed independently.

## Local remediation after the baseline audit

The findings and checked-in JSON below describe the pinned CLI baseline, not
the companion candidate on CLI branch `feat/spec-plan-apply` (see the
[validation record](spec-configuration-validation.md) for the exact commit).
The candidate currently addresses:

- F01: beta.6 fallback tags for core services; the independently released Reth
  image still requires an explicit approved tag.
- F02: explicit per-service and per-node create/import/reuse intent. Pure
  projection preserves intent without contacting AWS; `gen-keystore --plan`
  reports the selection and `gen-keystore` applies it, saving resolved identities
  for reuse. Key/backend replacement and conflicting flags are rejected.
- F03/F04/F05: Dogecoin discovery, submitter runtime parameters and the initial
  signer selection survive configuration generation and subsequent setup.
- F08: 30M genesis/builder gas, 2s block timing, initial fee overhead and
  explicit fee-oracle live/dry-run policy. Bootstrap retains other fee policies
  from a pinned SDK template. The default fee vault now enters both values and
  config TOML, including a minimal spec with no contract overrides.
- F07: proof topology and its deployment context are saved in doge-config, so
  custom source filenames and separate output directories no longer require
  keeping or rediscovering the original spec. Explicit `--spec` overrides the
  saved topology; otherwise saved doge-config precedes conventional spec lookup.
  Relative material paths still refer to the deployment directory; materials
  are not created or copied by this handoff.
- F06: the unused `signing.tsoServiceUrl` is explicitly rejected with guidance
  to configure `frontend.hosts.tso`. Internal WP/CubeSigner traffic retains the
  internal TSO service address.
- F09: spec validation, artifact-store readers, prep and archive setup
  reject reuse of the DA bucket for proof artifacts, including different-prefix
  configurations. A generated field table rejects unknown fields and malformed
  containers before normalization, including nested arrays, while preserving
  open dictionaries and existing retired-service migration rules. The build
  checks that the field table matches the TypeScript spec types.

- F10: `generate-from-spec --bootstrap --sdk-dir` reads a full pinned SDK
  commit, creates required native/monitoring bases, merges generated values with
  template policies and adapts Makefile node counts. It records template hashes
  and pending derived-artifact stages; missing bootstrap intent is rejected
  before writing. Optional capacity management and generic policy tuning remain
  explicitly owned by the template/operator, outside standard SDK releases.
- F11: both the SDK Phase A script and CLI-generated partner instructions create
  the policy bind directory as the operator before Docker can create it as root.
  Unwritable existing directories stop with recovery guidance.

The configuration-path findings F01–F11 now have implementations or explicit
validated scope boundaries in the candidate. This is not production acceptance.
The additional minimal-spec fee-vault omission was found and fixed during an
actual fresh-directory rehearsal. See [candidate validation](spec-configuration-validation.md)
for executed checks and their limits.

The original probe now reports `sameBucket.valid = false`,
`proofHandoff.dogeConfigHasProof = true` and
`proofHandoff.implicitSourceFound = true` against the candidate. The updated
probe also records `tsoUrl.valid = false` and `unknownField.valid = false`,
with generation rejected for both, and labels dirty CLI worktrees explicitly.
The unsupported AWS/GCP cluster-sizing fields have been removed from the full
example; cluster creation is still outside configuration generation. Its direct
generator calls intentionally bypass CLI validation; a successful direct render
is not acceptance of an invalid spec by the CLI. These results do not replace
the baseline JSON or establish cloud, compiler or runtime acceptance. See the
CLI's `docs/spec-projection.md` and `test/utils/spec-projection.test.ts` for the
candidate behavior and regression coverage.

## Evidence and reproduction

[Audit probe](../examples/tests/audit_spec_configuration.mjs) and
[sanitized results](spec-configuration-audit-evidence.json) accompany this
document. Use a built CLI checkout at the recorded revision:

```bash
node examples/tests/audit_spec_configuration.mjs /path/to/built/scroll-sdk-cli
```

The probe uses the checked-in minimal spec with nonfunctional placeholders,
does not load an operator deployment or dotenv file, and removes its private
temporary directory. It runs the actual CLI `generate-from-spec --with-values`
from an empty directory. Other probes compare the production generator outputs
and intent resolver directly. It neither creates cloud resources nor broadcasts
transactions, downloads images, compiles real proof materials or starts services.
The minimal disabled proof fixture tests source discovery only, not compiler
acceptance of complete real proof identities.

Recorded observations:

- Host changes reach both config and values (positive control).
- Custom Dogecoin discovery reaches direct values but not doge-config.
- DA override changes are lost from the four-TOML path.
- Initial keyset and custom TSO URL changes leave all generated outputs equal.
- An impossible initial threshold, a typo, and a shared DA/proof bucket are
  accepted by validation.
- Explicit proof spec selection and conventional-name discovery both succeed;
  the unbound custom output directory has no implicit source.
- dstack produces its controller values and monitor overlay, but not the base
  monitor. Genesis and native WP/PC files are not bootstrap generator outputs.
- Image, fee-oracle policy and Reth/contract preset omissions match source review.

Earlier isolated rehearsal additionally exercised current SDK examples -> prep
-> secrets -> selected Helm renders, the actual beta.6 topology compiler in
disabled/mock/observe and active/mock/observe modes, and real signer/TSO signed
polling. That rehearsal used synthetic Bridge inputs and repaired a temporary
directory permission issue. It is supporting evidence for those components,
**not** a clean-spec production acceptance run. Its private generated files and
logs are deliberately not included here.

## Remaining acceptance work

1. After fixes, run both paths from independent empty directories with the same
   declared intent, explicit template revision, identical imported identities
   and external fact fixtures. Do not use interactive commands to supply missing
   spec choices. Compare normalized runtime configuration, ignoring only
   declared path/format differences.
2. Cover local and existing/new KMS intent, multiple Reth nodes, custom discovery,
   two separate S3 buckets, disabled/mock and active real/enforce, and optional
   dstack. Negative tests must reject invalid thresholds, unknown fields,
   mismatched protocol/material identities and absent required artifacts.
3. Render charts and load configurations with the exact selected binary versions.
   Inspect native config + environment + args together; a valid Helm document
   is not sufficient. Do not assume every binary exposes a config-check flag.
4. Test provider creation/reuse and permissions with disposable resources only
   in an explicitly selected integration environment; verify recorded resource
   facts, resume semantics and no identity replacement on rerun.
5. Exercise genesis and Bridge initialization, bake/publication and partner
   handoff with real instance inputs before claiming end-to-end deployment.
   Existing-bridge migration, transaction replay and production proving remain
   separate acceptance scopes.

This audit changes documentation and adds a diagnostic probe only. It does not
fix generators, change chart defaults, select a production Reth release, mutate
cloud resources, or certify a production deployment.

[upstream-inventory]: https://github.com/DogeOS69/dogeos-core/blob/2830668c00f24df3f78be3d6a1aa178949514929/docs/production-service-inputs-and-generation.md
[core-wp]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/withdrawal_processor/src/config.rs
[core-l1i]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/l1_interface/src/config.rs
[core-da]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/eth_da_submitter/src/service_config.rs
[core-fee]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/fee_oracle/src/config.rs
[core-tso]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/tso_service/src/main.rs
[core-signer-cli]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/attestation_signer/src/cli.rs
[core-cube]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/ts-packages/cubesigner-signer/src/server.ts
[core-topology]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/dogeos_proof_topology/src/source.rs
[core-pc]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/proof_coordinator/src/service.rs
[core-worker]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/prover_worker/src/prover_coordinator/service/config.rs
[core-eager]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/eager_materializer/src/config.rs
[core-capacity]: https://github.com/DogeOS69/dogeos-core/blob/56007d3c413ad07f33d0e08b272004089c911f78/crates/proof_coordinator/src/capacity_manager/args.rs
[cli-generator]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/utils/deployment-spec-generator.ts
[cli-values]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/utils/values-generator.ts
[cli-spec]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/types/deployment-spec.ts
[cli-bootstrap]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/commands/setup/generate-from-spec.ts
[cli-prep]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/commands/setup/prep-charts.ts
[cli-keystore]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/commands/setup/gen-keystore.ts
[cli-attestation]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/commands/setup/attestation-signer.ts
[cli-proof-intent]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/utils/proof-intent.ts
[cli-bridge]: https://github.com/DogeOS69/scroll-sdk-cli/blob/4355e19e91db8433d28a8727e71fdb4fe1704232/src/commands/setup/bridge-init.ts
[contracts-template]: https://github.com/DogeOS69/scroll-contracts/blob/b34129ae776f8608193f1641de7041adcbdbf32d/docker/templates/config.toml
[contracts-reader]: https://github.com/DogeOS69/scroll-contracts/blob/b34129ae776f8608193f1641de7041adcbdbf32d/scripts/deterministic/Configuration.sol
