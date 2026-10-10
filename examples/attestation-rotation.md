# Attestation key rotation for bridge operators

The CLI implements an attestation-only rotation workflow against the current
core rules. Every target attestation public key must be different from every
current one. Operators may change from A/B/C to A/B/D, but A and B must generate
fresh identities in separate directories. TEE, namespace and ordered recovery
keys/threshold are inherited from the validated current bridge script. This
workflow does not rotate TEE, recovery keys or the L2 sequencer signer.

Run commands in your existing operator deployment directory, outside either
public repository. The conventional files are `deployment-spec.yaml`,
`deployment.env` and `runtime/`. Keep each rotation in its own directory,
selected by `--rotation-dir`; its intent is `rotation-spec.yaml` inside that directory. When already inside a
runtime directory, the CLI also supports its `.data/` and `values/` directly.
An existing `deployment/` is a final fallback; select the actual installed
runtime with `--dir` if your layout differs. Kubernetes context is pinned from
an explicit `--context`, the spec AWS cluster, or the current kubectl context.
Namespace follows the spec or `--namespace`, defaulting to `default`.

## Prerequisites and execution boundaries

Use a CLI checkout containing `bridge rotation` commands and its corresponding
SDK partner kit. The operator needs access to the WP Kubernetes pod, Helm,
make, and the external Dogecoin RPC credentials already saved with the
deployment. The runtime adapter uses the standard `withdrawal-processor-0`
pod/container, SQLite databases under `/app/data/`, mounted
`/app/protocol_context.json`, and the image's `sqlite3` tool. HTTP requests use a temporary loopback-only
`kubectl port-forward`, closed after each request; no curl binary in the WP
image is required.

This runtime adapter reads WP's replay and durable intent records using
**read-only SQLite queries through kubectl**,
checks the replay protocol opening against the local/mounted context, checks
the manifest's validated canonical head, and verifies the current script's
HASH160. It never substitutes the genesis bridge script after a rotation.

`plan` reads the cluster and writes only local proposal files. `stage` changes
runtime registration files and upgrades the WP release. `apply` is the only
command that submits the durable on-chain rotation intent. `status` is
read-only apart from its local status record. No command deletes old keys,
instances, databases or historical requests.

## 1. Collect target public identities and write the intent

Ask all target operators to generate fresh attestation and transport identities
with the [standalone key initialization tool](../partner-kit/attestation-signer/docs/key-initialization.md).
They send only their name and two public keys through your authenticated
Governance/operator channel. Private keys remain with each operator.

Copy [rotation-spec.example.yaml](rotation-spec.example.yaml) into your
private `rotations/attestation-rotation-002/` directory as
`rotation-spec.yaml`, then replace the public-key placeholders. Choose a new
directory for each rotation; keep previous directories for audit and recovery. Do not put TEE/recovery keys, redeem scripts, addresses, request
IDs or credentials into the intent.

The default timelock policy preserves the current absolute Dogecoin recovery
height. If it no longer leaves core's required 259200 blocks, `plan` refuses
and asks you to choose `timelock.policy: refresh`. Refresh calculates a height
using the greater of live tip and committed anchor, with a default review
margin of 10000 blocks, and never shortens the old height. It changes recovery
availability, script hash and bridge address: all signers must review it.
The fixed result is never silently recalculated at submission time.

## 2. Freeze and distribute the proposal

```bash
scrollsdk bridge rotation plan --rotation-dir rotations/attestation-rotation-002
```

The command writes `proposal.json`, `summary.md`, and
`rotation-policy.toml` in the selected directory. It reports previous-overlap status but permits preparing
materials before that overlap expires. The proposal contains complete old and
new scripts, public member pairs, threshold, inherited policy, computed bridge
address, exact timelock and grace. Its canonical SHA-256 binds every field.

Distribute those **three public files**, together with the independently
confirmed current key hash and proposal digest, to the current operators.
Follow their authenticated approval channel. Do not send the whole rotation
directory: later staging backups and logs may contain deployment credentials.

A name identifies one frozen proposal. If a target, timelock, or authoritative
baseline changes, use a new name and repeat review. Normal WF progress alone
does not change an already frozen proposal. Hashes identify content; they do
not prove the sender's identity or replace operator authorization.

## 3. Register and start the new group

```bash
scrollsdk bridge rotation stage --rotation-dir rotations/attestation-rotation-002
```

This merges new public registrations into the current TSO directory, preserves
old registrations, enables `rotate_key_v2`, upgrades the existing WP release
using the deployment Makefile, and waits for rollout. It exports the usual
signer deployment bundle to `<rotation-dir>/signer-deployment/`. A private
backup and stage log remain in the rotation directory. A rerun merges the same
identities without duplication; conflicting name/key bindings are refused.

Send each target operator that deployment bundle and the public proposal.
Operators follow the [partner handoff guide](../partner-kit/attestation-signer/docs/bridge-handoff.md)
and start independent containers/databases. The deployment bundle retains the
immutable genesis protocol context; `rotation-reference.json` identifies this
rotation's current/target keys. It never authorizes a rotation or overwrites
signer-owned RPC trust and rotation policies.

Each target must verify its identity, authenticated TSO connectivity, and
`AdvanceL1`/`AdvanceL2` production capabilities. Do not require a future rotation
allowlist merely to make the global `/ready` endpoint green.

## 4. Collect approvals and readiness records

Current operators follow the [independent inspect/approve guide](../partner-kit/attestation-signer/docs/rotation.md).
They inspect both complete scripts, approve the exact target locally, restart
and verify their existing signer, then return an approval receipt. The script
preserves old keys, databases, RPC policies and sequencer-rotation policy.

Save verified receipt files under `<rotation-dir>/receipts/`. The normal
workflow requires **every current operator's approval** and **every target
operator's readiness**, even though on-chain signing uses the configured
threshold. No automatic degraded 2-of-3 workflow is provided.

Approval receipt format (normally produced by the signer tool):

```json
{
  "schema": "dogeos/rotation-approval/v1",
  "proposalSha256": "REPLACE_WITH_REVIEWED_DIGEST",
  "signerAttestationPubkey": "REPLACE_WITH_CURRENT_PUBLIC_KEY",
  "targetKeyHash": "0xREPLACE_WITH_APPROVED_TARGET_HASH",
  "approvedAt": "2026-01-01T00:00:00Z"
}
```

Target readiness record:

```json
{
  "schema": "dogeos/rotation-readiness/v1",
  "proposalSha256": "REPLACE_WITH_REVIEWED_DIGEST",
  "signerAttestationPubkey": "REPLACE_WITH_TARGET_PUBLIC_KEY",
  "transportPubkey": "REPLACE_WITH_TARGET_TRANSPORT_PUBLIC_KEY",
  "advanceL1": true,
  "advanceL2": true,
  "tsoConnected": true,
  "checkedAt": "2026-01-01T00:00:00Z"
}
```

The signer-side `rotation.sh ready` command produces this record after checking
local identity and AdvanceL1/AdvanceL2 capabilities; it requires
`--acknowledge-tso-connected` because local health alone cannot establish an
authenticated TSO session. See the partner guide for the full command.

Record readiness only after the operator actually observes those conditions.
These records are **not cryptographic signatures**. Governance integration is
not implemented; receive and authenticate them using your existing channel.
Do not treat an arbitrary uploaded JSON file as identity proof. Receipt-source
verification is part of the operator handoff; apply requires no additional
command-line acknowledgement and does not claim to authenticate the sender.

## 5. Submit and monitor

```bash
scrollsdk bridge rotation apply --rotation-dir rotations/attestation-rotation-002
```

Before the first submission, the CLI checks all records, staged files, current
bridge/context, overlap expiry and frozen timelock. It calls the non-durable
`/protocol-actions/rotate-key/build` preview, then submits the frozen payload
to `/protocol-actions/rotate-key/propose`. Default access is pod-local through
kubectl; `--wp-url` accepts an explicit HTTPS or loopback endpoint.

Before network IO, it saves the exact request and stable idempotency key in
`submission.json`. A lost response or HTTP 503 can mean the WP has already
stored the intent. Keep all signers running. Use:

```bash
scrollsdk bridge rotation status --rotation-dir rotations/attestation-rotation-002
scrollsdk bridge rotation apply --rotation-dir rotations/attestation-rotation-002
```

`status` never submits. With `--rotation-dir`, it reads the frozen proposal
without depending on an editable spec, so preparing another rotation does not
change historical status queries. Re-running `apply` reconciles the original durable
intent and, when necessary, retries the **same payload and idempotency key**.
It never makes a replacement intent automatically. A terminal failure or
superseded intent requires investigation before creating a new proposal.

`apply` follows progress for 600 seconds by default (`--wait-seconds` overrides
this; zero returns after submission). It exits with code 2 when waiting or when
automated activation checks have passed but new-signer signature evidence still
requires manual verification. It does not return workflow success solely from
a subsequent Replay WF. A terminal failure exits with code 1. The `status`
command may return code 0 for a successful read; that is not workflow completion. Intent/job status, TSO transaction ID,
Dogecoin signed transaction ID, activation/deprecation WF and validated replay
progress are recorded without PSBTs or callback tokens.

The current implementation reports `activated` when the intent completed and
Replay uses the target key. It also reports a subsequent validated WF, but
**does not claim that this alone proves new-signer handoff**. Inspect target
signers' request/decision records and the corresponding transaction to verify
that the new set actually signed the follow-up WF. Automated collection of
that final per-signer evidence is not yet implemented. Status explicitly reports
`acceptance.rotationWorkflowComplete: false` and
`acceptance.newSignerSignatures: manual_verification_required`; the tool does
not mark full acceptance complete on the operator’s behalf.

After activation, publish the new deposit address through the deployment's
normal frontend/Governance update process. The rotation command does not
rewrite genesis context or automatically restart frontend services. Keep old
instances until the WF overlap has expired, old bridge funds are handled and
in-flight requests are resolved; retirement is intentionally separate.
