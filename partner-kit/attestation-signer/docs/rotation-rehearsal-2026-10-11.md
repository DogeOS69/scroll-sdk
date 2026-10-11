# Local-key rotation preparation rehearsal — 2026-10-11

Scope: act as the bridge operator, all three current signer operators and all
three replacement signer operators. Stop before any WP RotateKey build/propose
POST. The existing bridge is a testnet shadowfork deployment; this is not
production acceptance or evidence of completed key rotation.

Code was developed on `feat/rotation-operator-workflow` in both repositories.
Bases: SDK `842c9c287545c03a9a95220a4008eca7da36d9e9`; CLI
`210af597141ba80514b3b9a4eaa2c087e77bcf64`. The capacity-manager branches were
not changed. The companion [walkthrough](rotation-walkthrough.md) is the
operator-facing procedure; this record explains what actually happened.

## Environment and boundaries

- Private, mode-0700 rehearsal root outside either Git checkout; separate bridge,
  current-operator and new A/B/C directories. Keys and runtime logs remain there.
- Existing devnet EKS deployment, default namespace; WP chart `0.1.24` and image
  `dogeos69/withdrawal-processor:v0.3.0-beta.6-kms` were retained during staging.
- Current live identities belonged to the existing A/B/D rotation-2 instances.
  They were identified from live state and Docker mounts, not from stale directory
  names. Three entirely new identities were generated for the next set.
- New signer image:
  `dogeos69/attestation-signer@sha256:b69b503511837cfa80eb427b41fcefc5e47dbc8f2cfece5a04437ef83653359b`
  (beta.6a, release `0.3.0`, Git commit
  `20746174e993a64e7edb132b9ecdbd989788d864`, policy version `1`).
- Initial replay observation: WF 266, no active deprecating bridge key. The
  existing recovery height permitted the `preserve` timelock intent.
- No AWS/KMS keys or infrastructure were created. Existing private network/RPC
  arrangements were reused. Shadowfork URLs do not establish independent trust
  domains; no stronger production trust claim is made here.
- Governance was simulated by authenticated local role-to-role file handoff.
  No Governance website/API integration was exercised.

In the command descriptions below, `$KIT` is the reviewed SDK partner kit,
`$CLI` the locally built CLI, `$ROOT` the private rehearsal root, `$PROPOSAL` the
frozen proposal, and `$DIGEST` / `$CURRENT_HASH` independently reviewed public
inputs. These stand-ins keep private host configuration out of the public record.

## Commands, observations and corrections

### 1. Identify the currently active generation

Read WP's validated replay state through the rotation runtime, inspect current
signer identity/capabilities and inspect Docker bind paths without printing
environment values. Confirm the old A/B/D instances correspond to the current
script. Retained earlier generations were left untouched.

**Input source:** the existing deployment directory, Kubernetes context and live
replay. Operators must not infer active membership from an arbitrary old Compose
folder. The frozen plan later records that verified current identity.

### 2. Create three new private workspaces and local key pairs

For each of A, B and C, run:

```bash
bash "$KIT/scripts/init-keys.sh" --name signer-a-rehearsal \
  --network testnet --out "$ROOT/signer-a"
```

Repeat with the corresponding B/C name and directory. The existing Docker helper
created a WIF, an independent transport secret and a public helper record. Files
were private and no old key was modified. At this point the helper still emitted
beta.6 binary pins; these were explicitly corrected to the selected beta.6a
release in the private files before startup.

**Permanent correction:** the helper now accepts the complete explicit release,
Git-commit and signing-policy pin set. Conflicting reruns fail while preserving
both keys. The final walkthrough uses this option instead of a manual edit.

### 3. Export identities with the real core image

Pull the reviewed image, then for each new directory:

```bash
bash "$KIT/scripts/identity.sh" "$SIGNER_IMAGE" "$ROOT/signer-a" \
  > "$ROOT/signer-a/identity.json"
```

The native binary's attestation and transport public keys matched the generated
pairs. Export ran offline and did not start a service. Only this public JSON
crossed the role boundary; no private environment file was handed to the bridge.

**Permanent correction:** provide this Docker wrapper so the signer operator
needs neither an installed CLI nor a host binary or manually assembled flags.
Core's `publicKey` schema is distinguished from the helper's `attestationPubkey`.

### 4. Initialize and freeze one rotation intent

The bridge role copied the existing deployment into its private rehearsal
workspace, retaining the needed private configuration. From that bridge directory:

```bash
node "$CLI/bin/run.js" bridge rotation init \
  --rotation-dir rotations/operator-rehearsal-001 \
  --identity signer-a-rehearsal=../signer-a/identity.json \
  --identity signer-b-rehearsal=../signer-b/identity.json \
  --identity signer-c-rehearsal=../signer-c/identity.json
node "$CLI/bin/run.js" bridge rotation plan \
  --rotation-dir rotations/operator-rehearsal-001
```

Threshold stayed 2-of-3. The entire attestation set changed; namespace, TEE and
ordered recovery keys/threshold were inherited. Recovery height was preserved.
The proposal was frozen in this rotation-specific directory.

**Permanent correction:** `init` imports authenticated core public records so
operators do not have to transcribe key pairs or re-enter recovery/TEE keys.

### 5. Exercise an incomplete pre-submit check

Run `bridge rotation check` with the same directory. It correctly reported
missing staging and six operator receipts; live admission and absence of a prior
submission passed. No build/propose request was made.

**Permanent correction:** the new `check` command provides a useful rehearsal
stop point; receipt errors identify the missing current keys and new members
instead of only reporting a filesystem error or the first missing participant.

### 6. Stage existing and target registrations together

```bash
node "$CLI/bin/run.js" bridge rotation stage \
  --rotation-dir rotations/operator-rehearsal-001
```

Added three target registrations while retaining the existing registrations.
WP rolled out successfully using the same chart and image; `stage.json` recorded
`applied`. This was a real live configuration change, not a dry run. It did not
submit a rotation. Private backups/logs were retained.

The stage was initially applied from the rehearsal copy. After confirming the
original deployment's files still matched pre-stage backups, the two changed
registry/Helm-values files were synchronized back to the original runtime.
The native WP TOML was already identical. No second Helm rollout was needed.
The full rotation proposal/receipts remain in the private rehearsal directory.

**Permanent corrections:** `stage` reports the bundle manifest digest and a
clear handoff instruction. Newly generated bundles include rotation-specific
startup notes and manifest coverage for `rotation-reference.json`. The first
live bundle predated that documentation correction; it was retained unchanged.
The updated packaging was separately regenerated and Docker-verified against a
real new identity without redeploying WP or altering the shared live bundle.

### 7. Verify each new operator's handoff and start isolated services

For each new signer, run `verify-handoff.sh` using its identity and the bridge's
authenticated manifest digest. All three memberships and bundle hashes passed.
Install the policy context/AggVK and env file, copy the Compose template, select
the immutable image and set a distinct Compose project with loopback ports `0`.
Run `docker compose config --quiet` followed by `docker compose up -d`.

Each new instance obtained a separate SQLite volume. Old instances remained
running. The Compose host-port overrides prevented collisions on a shared host.

Initial capability checks exposed an operator input gap: copying the old TOML
was insufficient because that deployment's three RPC source sets were in its
private environment. Only the selected trust-source variables were transferred
from each existing operator to its replacement, without copying old WIFs,
transport secrets or databases. `docker compose up -d` recreated the new
containers with their added environment. All three then served AdvanceL1/L2.

**Permanent corrections:** the standalone template now documents required RPC
policy fields; the guide identifies the environment-based sources as well as
TOML. New-key generation must never be followed by blindly copying an old env.

### 8. Current operators inspect, approve and restart sequentially

For each current instance, export its existing public identity without generating
new keys, independently inspect the proposal, then run:

```bash
bash "$KIT/scripts/rotation.sh" approve "$PROPOSAL" \
  --expected-sha256 "$DIGEST" --current-key-hash "$CURRENT_HASH" \
  --config "$CURRENT_CONFIG" --container "$CURRENT_CONTAINER" \
  --identity "$CURRENT_IDENTITY"
```

All three retained their keys and database. Exact-target allowlists were added
with private backups and inode-preserving edits, one restart at a time. The
wrapper checked the actual bind mount (including the host path alias) and
verified the running RotateKey capability. Three approval receipts were collected.

**Permanent correction:** `--identity` replaces error-prone manual public-key
arguments. The current hash and authenticated proposal digest intentionally
remain independent review inputs.

### 9. Observe authenticated TSO polls and collect new readiness receipts

A temporary loopback port-forward to `service/tso-service:3000` exposed `/metrics`
for inspection. All three target public keys had recent authenticated poll
metrics; recorded sample ages were about 11, 25 and 15 seconds. Healthy Docker
status alone was not used as evidence of connection.

Each new operator ran:

```bash
bash "$KIT/scripts/rotation.sh" ready "$PROPOSAL" \
  --expected-sha256 "$DIGEST" --current-key-hash "$CURRENT_HASH" \
  --container "$NEW_CONTAINER" --identity ./identity.json \
  --acknowledge-tso-connected
```

All three passed identity, enforce mode and AdvanceL1/L2 checks. Their future
rotation capabilities remained unapproved; no invented allowlist was added to
make global readiness green. Receipts were copied to distinct `new-a/b/c.json`
files alongside the three current approvals.

### 10. Recheck admission and stop before WP submission

Run the final `bridge rotation check` against the live deployment, with the
runtime's `post` function instrumented to throw if invoked. All four checks
passed: stage, operator receipts, live admission and not-submitted. The final
code was rebuilt and the same guarded check passed again after documentation
and packaging fixes.

```json
{
  "readyForSubmissionChecks": true,
  "submitted": false,
  "wpPreviewPerformed": false
}
```

No submission journal or corresponding durable intent was present. `apply` was
not run; neither `/rotate-key/build` nor `/rotate-key/propose` was invoked by this
rehearsal. Three current instances and three healthy new instances were retained.

## Validation and remaining acceptance

Regression validation covers identity import and network/pair validation,
manifest binding, private key preservation, explicit binary pins, and a command
boundary test that makes any WP POST fail. Docker tests exercise the actual key
generator/core identity export and disposable approval/readiness containers.
The final guide and helper commands also have the live evidence above.

Remaining work requires a separate actual submission: verify activation, WF
progress and signatures from the new set, then retire old instances only after
the protocol overlap boundary. This rehearsal does not validate those steps,
KMS custody, Governance authentication/API integration, or independent production
RPC trust. Binary/release approvals and authenticated receipt transfer remain
explicit human responsibilities.
