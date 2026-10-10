# Approving an attestation key rotation

An attestation rotation replaces the entire attestation public-key set under
core's current rules. Operators A and B can remain operators, but they must
create fresh identities: `{A1, B1, C1}` becomes `{A2, B2, D1}`. Keeping A1 and B1
public keys while replacing only C1 is rejected. Keep every old identity and
its database running during handoff and the old-key overlap period.

This guide covers the **current signer operator's independent inspection and
approval**. It requires Bash and Docker, not scroll-sdk-cli, host Python,
OpenSSL, or a Dogecoin node. Docker downloads a pinned Python Official Image
on first use. Inspection and configuration editing run with networking
disabled. Runtime checks join only the explicitly selected signer's network
namespace; the Docker socket is never mounted into the tool container.

## Materials and responsibilities

The bridge operator produces a frozen `proposal.json` with schema
`dogeos/attestation-rotation/v1` and its SHA-256 digest. Obtain that digest via
your agreed authenticated Governance/operator channel. Independently confirm
the **current bridge key hash** for your deployment. A self-consistent hash
inside a downloaded proposal does not establish who authorized it.

The envelope contains `proposal` and `sha256`; the digest is SHA-256 of UTF-8
JSON for `proposal` with recursively sorted object keys and no insignificant
whitespace. The proposed current and target scripts, member public identities,
network, deployment context digest, timelock and overlap policy are covered.

The bridge operator sends current operators the same full proposal. New
operators also receive the usual deployment/policy bundle to start their
fresh independent instances. The deployment bundle never authorizes a
rotation or overwrites a current operator's local allowlist.

## Inspect before approving

Use paths in a private operator workspace outside this public checkout:

```bash
bash /path/to/scroll-sdk/partner-kit/attestation-signer/scripts/rotation.sh \
  inspect ./proposal.json \
  --expected-sha256 '<digest-from-approved-channel>' \
  --current-key-hash '0x<independently-confirmed-current-bridge-hash>'
```

Inspection prints the old and new parsed scripts, public members, target
address, deployment context digest and overlap duration. It independently
verifies the full redeem-script structure and script hashes, namespace,
unchanged TEE key, unchanged ordered recovery keys and threshold, disjoint
attestation sets, valid curve points, target members and threshold, network
address, and the proposal's recovery delay at its recorded anchor.

Review timelock changes explicitly: they change recovery availability and the
script hash. Review the attestation threshold as well as membership. The
current tool approves attestation rotation only; it does not approve a TEE,
recovery, or L2 sequencer-key change. Offline inspection cannot establish the
latest chain height, replay state, remaining overlap or network availability;
the bridge operator and WP must recheck those before submission.

## Approve and load the exact target

Run this only after your team has approved the reviewed proposal:

```bash
bash /path/to/scroll-sdk/partner-kit/attestation-signer/scripts/rotation.sh \
  approve ./proposal.json \
  --expected-sha256 '<same-reviewed-digest>' \
  --current-key-hash '0x<same-confirmed-current-bridge-hash>' \
  --config ./docker-compose/attestation-signer.toml \
  --container '<your-existing-signer-container-name>' \
  --signer-public-key '<your-current-attestation-public-key>'
```

The command requires an existing container that selects this exact TOML file
with `-c` or `--config` and mounts it as a single-file bind mount, as in this
kit's Compose example. It rejects environment or command-line overrides of
`allowed_next_bridge_script_hashes`. For another layout, review the generated
policy fragment and manage the configuration/restart yourself; do not assume
that editing an unrelated host file changes the running signer.

The tool checks that the running signer matches your current public key and
network and operates in `enforce`. It then:

1. Revalidates the proposal and your membership in the current signer set.
2. Backs up the TOML beside the original with mode `0600`.
3. Adds only the exact target to `allowed_next_bridge_script_hashes`, preserving
   existing targets, `allowed_next_sequencer_signers`, RPC policies and other
   settings. Unsupported ambiguous TOML edits fail without writing.
4. Updates the file in place to preserve existing Docker bind mounts. It does
   not touch keys, databases or deployment bundles.
5. Restarts only the named container and checks its identity, `enforce` mode
   and `rotate_key` production capability on `/policy`.
6. Writes `rotation-approval-<proposal-digest>.json` beside the TOML.

`--port` defaults to the signer's **internal** HTTP port `4040`; use it only
when that listener differs. No public port or host port-forward is needed.
`/ready` may still reject unrelated unconfigured operations; the tool checks
the requested RotateKey capability instead of requiring every capability.

Core's `/policy` endpoint does **not** expose individual loaded allowlist
entries. This tool verifies the selected configuration mount, absence of the
supported overrides, explicit restart and capability. That is not a remote
cryptographic attestation of loaded targets or a guarantee that a future
request will pass all evidence checks.

Send the receipt to the bridge operator through the authenticated approval
channel. It identifies the proposal digest, current attestation public key,
approved target hash and approval time. **The receipt is an operator record,
not a transaction signature or a cryptographically signed certificate.**
A bridge tool must not treat an unauthenticated uploaded JSON receipt as
proof of approval.

If restart or verification fails, no new successful receipt is produced. The
new allowlist entry may already be on disk, and the prior backup remains.
Inspect the local service before retrying. Restoring a backup must preserve
the bound file's inode and be followed by a restart; do not delete the database
or replace either private key. Re-running approval for the same target is
idempotent at the configuration level.

## New signer readiness receipt

New operators initialize fresh keys with `init-keys.sh`, send their public
identity to the bridge operator, and receive the usual deployment bundle.
Configure independent RPC trust sources and start the new instance following
the existing onboarding guide. Do not copy the old instance's database or
replace the old identity in place.

After startup, verify authenticated long-poll/callback connectivity with the
registered transport identity in signer/TSO operational evidence. A successful
`/health` response does not establish TSO connectivity. Then run:

```bash
bash /path/to/scroll-sdk/partner-kit/attestation-signer/scripts/rotation.sh \
  ready ./proposal.json \
  --expected-sha256 '<reviewed-proposal-digest>' \
  --current-key-hash '0x<confirmed-current-bridge-hash>' \
  --config ./docker-compose/attestation-signer.toml \
  --container '<your-new-signer-container-name>' \
  --signer-public-key '<your-new-attestation-public-key>' \
  --transport-public-key '<your-new-transport-public-key>' \
  --acknowledge-tso-connected
```

The command verifies the public pair belongs to the proposal, checks the named
container/config mount, live attestation identity, network, `enforce` and both
`advance_l1`/`advance_l2` production capabilities. It does not require a
RotateKey allowlist in the new instance, edit its policy or restart it.
The TSO connectivity assertion is **explicitly the operator's acknowledgement
of observed authenticated connectivity**; the tool cannot derive it from
`/policy`. Likewise, match the supplied transport public key to your local
identity and TSO registration before acknowledging it.

Send `rotation-readiness-<proposal-digest>.json` to the bridge operator over
the authenticated channel. The two receipt formats are:

```json
{
  "schema": "dogeos/rotation-approval/v1",
  "proposalSha256": "<reviewed SHA-256>",
  "signerAttestationPubkey": "<old attestation public key>",
  "targetKeyHash": "0x<approved target hash>",
  "approvedAt": "<UTC timestamp>"
}
```

```json
{
  "schema": "dogeos/rotation-readiness/v1",
  "proposalSha256": "<reviewed SHA-256>",
  "signerAttestationPubkey": "<new attestation public key>",
  "transportPubkey": "<new transport public key>",
  "advanceL1": true,
  "advanceL2": true,
  "tsoConnected": true,
  "checkedAt": "<UTC timestamp>"
}
```

These examples show the generated fields, not files to fill with unchecked
claims. A readiness receipt is a preflight record, not evidence that the new
identity has already signed an actual bridge transaction. The bridge operator
must verify that after activation.

## Handoff and retirement

The bridge operator submits the frozen proposal to WP only after checking
current approvals and new-instance readiness. Current signers automatically
verify and sign the resulting requests; approval itself neither creates nor
broadcasts a transaction. New signers do not sign the rotation's old-bridge
inputs. Validate that the new group signs a subsequent WF transaction after
activation.

Keep old instances and keys until the bridge operator confirms that the old
key's WF deprecation boundary, remaining funds and in-flight work permit
retirement. Never wipe historical failed requests as part of this process.
Retain the approved proposal, receipt and local backup in private records;
configuration backups can contain RPC credentials and must not enter Git.

## Tool verification

Maintainers can run the disposable, synthetic-fixture tests with Python 3.11+
(no dependencies):

```bash
python3 -m unittest discover -s partner-kit/attestation-signer/tests -v
```

These tests cover script and hash tampering, disjointness, frozen TEE/recovery
configuration, timelock mismatch, safe TOML edits, preserved bind-mount inodes
and private backups. They do not claim a live-chain rotation was performed.

To exercise the full wrapper with a disposable fake signer, including Docker
restart and receipt generation, run:

```bash
RUN_DOCKER_ROTATION_TESTS=1 python3 -m unittest discover \
  -s partner-kit/attestation-signer/tests -v
```

The integration test removes only its own uniquely named test container.
