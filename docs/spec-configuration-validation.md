# Spec configuration candidate validation

This records local validation of the candidate following the
[beta.6 input audit](spec-configuration-audit.md). The audit's original JSON
remains evidence for the old baseline, not the repaired candidate.

## Sources and scope

- CLI base: `4355e19e91db8433d28a8727e71fdb4fe1704232`.
- CLI candidate: [`2a1b0b3849ca965366556968d150c2060abca738`](https://github.com/DogeOS69/scroll-sdk-cli/commit/2a1b0b3849ca965366556968d150c2060abca738)
  on `feat/spec-plan-apply`.
- SDK template pin: `c8f7871b6f6ad0d19504342558d96b7e39608d4d`.
- Core beta.6: `56007d3c413ad07f33d0e08b272004089c911f78`.
- Contracts policy: `dogeos-v0.3.0-rc.4`, 30,000,000 gas, 2-second blocks.
- Reth `v0.3.0-beta.1c` was explicitly selected for a rendering rehearsal only;
  this does not approve it for the beta.6 production deployment.

The supported scope is configuration for SDK-managed services, with explicit
identity provisioning and derived-artifact stages. Optional capacity-manager
installation and arbitrary service tuning are outside the standard SDK service
set; pinned templates and reviewed operator values own those policies.

## Executed fresh-directory rehearsal

All generated configuration, disposable keys, logs and Docker state were kept in
private temporary directories outside the checkouts. No credential-bearing
artifacts are attached to this report.

| Check | Result and meaning |
| --- | --- |
| Actual `generate-from-spec --bootstrap --sdk-dir` | Passed with a custom external spec path and an empty output directory; read committed SDK templates, generated TOML/values, saved template provenance. |
| `gen-keystore --plan` | Passed without key creation or AWS calls. |
| Local service identities, two sequencers and one bootnode | Created with actual CLI commands; immediate rerun preserved saved identity state exactly. |
| Partner Phase A | Actual beta.6 signer container exported its identity; Phase A rerun succeeded; the policy directory remained owned by the non-root operator. |
| Descriptor import | Actual CLI imported the partner's public descriptor with saved initial signer selection. |
| `prep-charts`, then rerun | Passed after test Bridge prerequisites were supplied; consumed proof intent from doge-config. |
| Disabled/mock/observe topology | Actual pinned beta.6 compiler ran; `proof-config-check` passed. |
| `gen-secrets` | Completed in the private deployment directory. |
| Helm rendering | Passed for TSO, WP, PC, submitter, CubeSigner, fee-oracle, dstack and a Reth sequencer. |
| Active/mock/observe topology | Actual compiler and config check passed; exported signer policy successfully. |
| Separate S3 stores | Assertions verified the DA writers/readers use the blob store and WP/PC plus signer policy use the proof store. No AWS bucket was created or accessed. |

The rehearsal found a further omission: the minimal spec's Reth values defaulted
the fee recipient, while generated `config.toml` omitted the fee-vault override
required by prep. Both projections now share the same default; the repeated-prep
regression no longer supplies a manual override to mask the omission.

## Automated regression coverage

The full CLI suite completed with **928 passing and 17 pending** tests. After
the final identity flag, account-only scope and plan-output refinements, the
focused suites passed **65 tests**. Full lint and subsequent changed-file lint had zero errors
(existing/style-complexity warnings remain). SDK Makefile checks passed all
**8 tests**; shell syntax and both repositories' whitespace checks passed.

The CLI suites cover projection defaults/overrides, full field validation,
unknown containers, strict bucket separation, source-independent proof handoff,
initial signer selection, saved identity reuse, KMS adapter calls, conflicting
identity flags, pinned template reads and partner script behavior. KMS providers
are stubbed; their outputs are disposable test facts. The SDK Makefile context
suite checks recipe expansion without contacting a cluster. Phase A also passes
shell syntax validation.

Reproduce the automated checks in a built CLI checkout (set `OCLIF_TEST_ROOT`
to that checkout when running from a linked worktree):

```bash
npm run build
OCLIF_TEST_ROOT="$PWD" npm test
npm run lint
```

In the SDK checkout:

```bash
python3 examples/tests/test_makefile_context.py
bash -n partner-kit/attestation-signer/scripts/phase-a.sh
```

## Acceptance boundaries

Bridge transaction, protocol-context and proof-identity inputs in this local
rehearsal were explicitly synthetic fixtures. No chain transaction, genesis
launch, deposit, real proof, withdrawal or cloud resource creation was performed.
Mock/observe success is not evidence of real/enforce production readiness.

A production deployment must supply approved binary pins, provider credentials,
real funding and Bridge facts, generated genesis, matching proof materials and
partner policy approvals at their respective stages. `--bootstrap` records those
stages as pending rather than generating placeholders that pretend they are
complete. Local creation/reuse and mocked KMS calls establish configuration
handoff; live AWS/IRSA and runtime acceptance require the intended environment.

## Resumable production Bridge preparation

The same CLI candidate now exposes `setup plan --spec --output --sdk-dir` and
`setup apply --dir`. Its `docs/spec-preparation.md` defines the spec fields,
external funding handoff, immutable fresh-deployment plan, private environment
file and resume outcomes. This is preparation orchestration; Helm installation
and running-chain acceptance remain separate.

A further private rehearsal ran the production path from core beta.6's
`docs/bridge-genesis-deployment.md`. Unlike the earlier fixture-only Bridge
rehearsal, this run executed the actual rc.4 genesis container and the actual
beta.6 namespace, Bridge artifact and protocol-context tools. It used
`dogeos69/bridge-genesis-tools@sha256:27e646fd5d9c340926df82f47f7d352fd5333de4e6178c5a8c56aa9637769262`.
The Dogecoin/Ethereum RPC and funding transactions remained synthetic fixtures;
there was no transaction broadcast or live cloud provisioning.

The reproducible CLI driver is `scripts/test-preparation-e2e.mjs`. It verified:

- Planning did not provision identities, contact cloud providers or broadcast.
- The first apply created local identities, imported a public partner descriptor
  and private dummy dstack credentials, generated genesis, and waited for wallet
  outpoints. The private environment file was reloaded across CLI processes.
- Sequencer funding was exactly 42,069,000 satoshis. Verified funding facts drove
  the real core namespace and final Bridge address generation, followed by a
  second wait for marked Bridge funding.
- The final apply generated canonical protocol context, compiled mock/observe
  topology, prepared service values and private Secrets, exported signer policy,
  and passed the proof configuration check.
- A subsequent apply completed without rerunning completed steps. The RPC method
  record contained only read operations.

Regression coverage also rejects wrong-network or spent funding, wrong amounts,
insufficient confirmations, noncanonical block anchors, incorrect/multiple funding
markers, mutated prepared artifacts and concurrent apply. Ambiguous test-helper
broadcast failures remain blocked for reconciliation. Production mode excludes
helper broadcasts and omits the helper seed/funding placeholders.

This confirms production artifact construction and the configuration handoffs
against beta.6. It does not establish actual chain confirmation, live AWS/KMS or
Kubernetes permissions, real/enforce proving, partner policy approval, or full
bridge business-operation acceptance.

Final candidate verification for this addition: CLI build passed; the full suite
reported **945 passing, 17 pending**; lint reported **0 errors, 258 warnings**.
The 16 preparation regression cases cover state/resume, command boundaries,
private output handling, funding validation and early destination checks. The
container rehearsal above passed with the same candidate and a mock/observe
proof fixture. No chart defaults were changed by the preparation orchestration.

## Reviewed example defaults and S3 read URL follow-up

CLI follow-up [`05719d10009eef5302f26d3ee53ea15d5d675c34`](https://github.com/DogeOS69/scroll-sdk-cli/commit/05719d10009eef5302f26d3ee53ea15d5d675c34)
lets an enabled AWS blob archive omit `publicBaseUrl`: bucket and region determine
the default read origin, while an explicit CDN/gateway URL still takes precedence.
The generated doge-config and direct service values now agree. The SDK and CLI
spec fee examples also match the existing SDK policy: 0.1 DOGE withdrawal fee and
1 DOGE minimum, encoded using L2's 18 decimals.

The revised SDK starter selects two sequencers, two bootnodes, AWS KMS identities
for eth-da-submitter and fee-oracle, independent 2-of-3 attestation/recovery
cohorts, 6 funding confirmations and the CLI's existing Sepolia RPC defaults.
It includes all node identities, three descriptor paths and three recovery public
key placeholders. Sequencer signers remain local.

Validation of this follow-up passed:

- CLI build and 165 targeted configuration/projection/identity/preparation tests.
- Changed-file lint: 0 errors, 5 warnings.
- SDK example environment coverage, rejection of unfilled placeholders, filled
  schema validation and all 17 preparation steps. Only the identities step was
  classified as a cloud mutation; no broadcast step was selected.
- Assertions for both node counts, both KMS backends, the 2-of-3 attestation
  selection, three descriptor inputs, 6 confirmations and both withdrawal fees.

No apply against AWS or the three-signer cohort was run in this follow-up. The
container rehearsal above describes the earlier local-identity variant. The TEE
public key remains an operator input obtained from CubeSigner before planning;
role/key lookup and hosted session provisioning are not yet part of plan/apply.


## Intent input simplification and real/enforce example

CLI follow-up [`6bc68023cef6b7244084671a97acb958a1cf68a6`](https://github.com/DogeOS69/scroll-sdk-cli/commit/6bc68023cef6b7244084671a97acb958a1cf68a6)
derives proof/dstack endpoints from the base domain, removes retired coordinator
collection timers, imports Vast.ai credentials from a named environment variable,
and selects/persists the finalized Ethereum anchor without an operator-supplied
block height. Funding waits create the default input file and display wallet
addresses, amounts and outpoint templates.

The SDK starter now selects four AWS KMS signing identities (eth-da-submitter,
fee-oracle and both sequencers); P2P nodekeys remain local. Its `active/real/enforce`
intent selects a checksum-verified proof release manifest. Apply generates the
Bridge-bound identities, exports materializers and checks the release CUDA Worker
image before material import and publication. These orchestration changes were
tested with synthetic manifests and command adapters, not a live real release.
The subsequent CLI commit `953914a` lets the operator select only
`proofRelease.version`. It retrieves the official manifest/checksum and freezes
their pins; offline manifest/hash inputs remain an advanced alternative. The
release workflow is currently in open dogeos-core PR #1335. Missing release
artifacts are a publisher dependency, not a manual operator SHA256 input.

The deposit fee is now explicitly 1 DOGE (`depositFeeSats: "100000000"`), matching
the SDK's existing `config.toml.example` policy. The CLI converts satoshis to L2
wei for `contracts.DEPOSIT_FEE` instead of copying the number unchanged.
Withdrawal remains 0.1 DOGE, with a 1 DOGE minimum. Regression tests cover integer
precision, zero, one satoshi, invalid/overflowing inputs and legacy wei fields.

The Dogecoin network/chain-ID mapping remains enforced by the CLI. Both Ethereum
submitter depth fields remain supported: beta.6's `txmgr.rs` reads confirmation
and finalization depths in the transaction lifecycle, and its `.env.example`
selects 1/64. They are distinct from DA readers' safe/finalized block-tag checks.
Source baseline: dogeos-core `56007d3c413ad07f33d0e08b272004089c911f78`.

Validation for this candidate:

- CLI build and generated-field inventory check passed.
- Changed TypeScript files: lint passed with 0 errors and 22 warnings.
- Temporary SDK example validation passed: environment coverage, rejection of
  unfilled placeholders, schema validation, all four KMS selections, real/enforce
  intent, fee conversion, and all 22 planned steps. Only identities and proof
  publication select cloud mutations; no transaction-broadcast step is selected.
- Full suite at `6bc6802`: **960 passing, 15 pending, 1 failing**. The failure
  is the existing `setup bootnode-public-p2p` integration with the adjacent Reth
  chart: it emits the legacy public P2P shape rejected by the chart. The tested
  command, test and chart are unchanged from their respective base branches.
- The subsequent version-lookup change (`953914a`) passed build and **181 targeted
  tests**, including publication lookup, missing assets, checksum mismatch,
  immutable offline reuse, preparation state, projection and CLI spec workflow.
  Its changed-file lint passed with 0 errors and 9 warnings.

No live KMS provisioning, S3 publication, paid Worker launch, real proving or
partner policy acceptance was performed. The previous container rehearsal covers
the earlier local/mock variant. Importing returned partner validation references
and regenerating their bound configuration remains outside current plan/apply;
without that evidence the final enforcing proof check rejects completion.
