# Attestation rotation: bridge and signer operator walkthrough

This walkthrough replaces all attestation identities on an existing bridge.
For three operators, A1/B1/C1 become A2/B2/C2 (or three new teams). Reusing an
old attestation public key in the target set is rejected by core. Each target
has a fresh signing key, transport key, workspace and database. Old instances
remain running throughout preparation and the subsequent overlap period.

This guide uses **local signing keys**, as exercised in the rehearsal. It
creates no AWS resources. Production teams choosing KMS need their own reviewed
KMS onboarding; do not interpret this rehearsal as approval of a custody model.
The stop point is a read-only submission check: **no WP build/propose request
and no RotateKey transaction**. A successful check is not completed rotation.

## Before starting: where inputs come from

The bridge coordinator distributes a rotation identifier and an authenticated
release record. Governance can carry the public records and review decisions;
these tools do not log in to Governance or authenticate its users. Authenticate
file transfers and receipt senders through the organization's agreed channel.

| Input | Who supplies or verifies it | Where used |
|---|---|---|
| SDK tool revision, signer image digest, release version, full Git commit and signing-policy version | Bridge release coordinator supplies the approved release; each signer team verifies it against the release/build evidence | SDK scripts, key initialization, runtime image and binary pins |
| CLI revision | Bridge tool maintainer; use a build including `bridge rotation init` and `check` | Bridge host only |
| Network | Existing deployment / approved Governance record; CLI also checks it against runtime configuration | New identity creation |
| New signer name | Operator and coordinator agree a unique name for this key generation, e.g. `team-a-r3` | Governance record and `init --identity NAME=FILE` |
| New public key pair | Signer generates keys locally and exports core `--print-identity` JSON | Governance, rotation intent and TSO registration |
| Current bridge key hash | Independently accepted deployment/last activation record, corroborated by the bridge operator's validated replay state | Current and new operator proposal inspection |
| Proposal digest | Approved frozen proposal revision, obtained through the authenticated channel | All operators inspect the same proposal |
| Bundle manifest digest | Bridge `stage` output, communicated through the authenticated channel | New operators verify their handoff bundle |
| RPC URLs, credentials and trust-domain names | Each signer's own infrastructure/provider contracts and existing trust configuration | Operator-owned TOML/environment; never bridge-owned authorization |
| TSO URL, artifact origin, protocol context and verifier | Generated from existing deployment and selected proof release | Verified signer bundle |
| Container identifier | `docker compose ps -q attestation-signer` in that instance's workspace | Local approval/readiness commands |
| TSO connection evidence | Bridge operator's TSO metrics for the new public key, after registration/startup | New readiness receipt |

Image labels are useful corroboration, not approval by themselves. The image's
runtime Git commit can differ from its tag name. Update image and binary pins
together. A new operator should not guess these values or copy the example
beta.6 defaults when a different image has been approved.

## 0. Obtain tools and create role-specific workspaces

Signer hosts need Bash, Docker Engine and Docker Compose. Git is needed only
to obtain the kit (an authenticated archive is also usable). No host Node.js,
Python, OpenSSL, Dogecoin node or `scrollsdk` is needed by the signer operator.
The SDK wrappers run pinned Node/Python helper images; Docker needs registry
access for their first download. Key creation and proposal verification run
offline after their images are available.

Obtain the reviewed `DogeOS69/scroll-sdk` revision from the coordinator. Set
`SDK` to that checkout and `KIT="$SDK/partner-kit/attestation-signer"`.
Keep all private operator workspaces **outside** the SDK checkout.

The bridge host additionally needs Node.js and Yarn 1.22 (the CLI repository
pins Yarn in `package.json`), the reviewed
`DogeOS69/scroll-sdk-cli` checkout, Make, Helm and kubectl, and access to the
existing deployment directory and cluster. In that CLI checkout run `yarn install --frozen-lockfile`
and `npm run build`. Define this shell function using its absolute path:

```bash
CLI=/absolute/path/to/scroll-sdk-cli
scrollsdk() { node "$CLI/bin/run.js" "$@"; }
scrollsdk bridge rotation init --help
scrollsdk bridge rotation check --help
```

Run subsequent bridge commands from the existing deployment directory containing
`runtime/` and `deployment.env`. Preserve its private configuration. Confirm the
kubectl context before running `plan` or `stage`; use `--context` and
`--namespace` if the saved deployment context is not the intended one.

## 1. Each NEW signer creates and publishes its public identity

The coordinator gives the operator `SIGNER_IMAGE`, `RELEASE_VERSION`,
`GIT_COMMIT`, `SIGNING_POLICY_VERSION`, `NETWORK` and its new `SIGNER_NAME` from
the table above. Set `WORKSPACE` to a new private directory, for example
`$HOME/dogeos-signers/team-a-r3`. Repeat independently for all three operators.

```bash
umask 077
bash "$KIT/scripts/init-keys.sh" --name "$SIGNER_NAME" --network "$NETWORK" \
  --out "$WORKSPACE" --release-version "$RELEASE_VERSION" \
  --git-commit "$GIT_COMMIT" --signing-policy-version "$SIGNING_POLICY_VERSION"
cd "$WORKSPACE"
docker pull "$SIGNER_IMAGE"
bash "$KIT/scripts/identity.sh" "$SIGNER_IMAGE" . > identity.json
```

The first command writes `attestation-signer.env` (local signing WIF),
`transport.key`, and `public-identity.json`. It prints only public information.
Both secrets are mode `0600`; reruns reuse the same complete identity and refuse
conflicting explicit pins without changing keys. This command is not an image
upgrade command. Do not delete a partial workspace and regenerate after sharing
its identity; restore it or coordinate a new identity with the bridge operator.

The second script invokes the **actual selected core binary** with
`--print-identity`. It emits core's public JSON schema with `publicKey` and
`transportPubkey`. This is distinct from the helper's `public-identity.json`
(which uses `attestationPubkey`). Publish the two public keys as a paired
Governance record under the agreed name; send `identity.json` through the same
authenticated handoff. Never send either private file, your environment file,
or your database. Governance need not accept file uploads: the coordinator can
save its authenticated public record in the same core JSON schema.

## 2. Bridge operator imports identities and freezes the proposal

Save the authenticated records as `incoming/team-a-r3.json`, `team-b-r3.json`
and `team-c-r3.json` in the private deployment workspace. Verify their owners
and pairing against Governance. Choose a **new directory for every rotation**:

```bash
ROTATION=rotations/rotation-003
scrollsdk bridge rotation init --rotation-dir "$ROTATION" \
  --identity team-a-r3=incoming/team-a-r3.json \
  --identity team-b-r3=incoming/team-b-r3.json \
  --identity team-c-r3=incoming/team-c-r3.json
scrollsdk bridge rotation plan --rotation-dir "$ROTATION"
```

`init` writes `rotation-spec.yaml` and refuses an existing directory. It checks
core identity schema, network, distinct key pairs and names. It does not create
keys or access the cluster. Review the intent before `plan`.

`plan` reads current validated bridge state and produces `proposal.json`,
`summary.md` and `rotation-policy.toml`. It inherits the threshold, namespace,
TEE key and ordered recovery keys/threshold. Operators do not manually re-enter
those keys. The default timelock intent is `preserve`; if the existing recovery
height is too close, explicitly review `--timelock refresh` when initializing
a new proposal. Never silently change the frozen proposal's timelock or keyset.

Review current/target members, quorum, recovery height, network, deployment
binding and overlap. Distribute the frozen proposal and its authenticated digest
to current and new operators. Give them an independently corroborated current
bridge hash. A digest simply copied out of the received proposal is not approval.
Do not advertise the future deposit address to users before activation.

## 3. Current operators inspect independently

Each CURRENT operator works in their existing instance's private directory.
Save the proposal as `proposal.json`. Set `PROPOSAL_SHA256` from the authenticated
review record and `CURRENT_KEY_HASH` from the independently confirmed current
bridge record, not merely from that proposal. Then run:

```bash
bash "$KIT/scripts/rotation.sh" inspect ./proposal.json \
  --expected-sha256 "$PROPOSAL_SHA256" --current-key-hash "$CURRENT_KEY_HASH"
```

Review the output and record the team's approval in Governance. Inspection
checks the scripts, addresses, network, unchanged TEE/recovery/namespace,
disjoint attestation sets, quorum and timelock at the recorded anchor. It does
not establish current chain admission by itself.

## 4. Bridge operator stages registrations and sends a versioned bundle

```bash
scrollsdk bridge rotation stage --rotation-dir "$ROTATION"
```

**This step changes the live deployment:** it retains existing registrations,
adds target identities, enables the WP rotation route, exports a target-aware
signer bundle and rolls out WP with the deployment's selected chart/image. It
does not submit RotateKey. Inspect `stage.json`; successful staging is recorded
as `applied`. Preserve `private-backup/` and `stage-private.log` privately.

Send ONLY `signer-deployment/` to new operators, plus the reported
`manifestSha256` through the authenticated channel. Send the proposal separately.
Do not distribute the whole rotation directory or private deployment files.
The bundle's `rotation-reference.json` binds the proposal/current/target hashes.
`protocol_context.json` retains the immutable genesis context: do not rewrite
it to pretend the new bridge was the genesis bridge.

## 5. Each NEW operator verifies the bundle and starts a separate instance

In the new workspace, save the bundle as `received-policy-bundle/` and set
`BUNDLE_SHA256` to the authenticated manifest digest:

```bash
bash "$KIT/scripts/verify-handoff.sh" ./received-policy-bundle \
  "$BUNDLE_SHA256" ./identity.json
cp "$KIT/docker-compose/docker-compose.yml" ./docker-compose.yml
cp "$KIT/docker-compose/attestation-signer.toml" ./attestation-signer.toml
mkdir -p policy
cp received-policy-bundle/signer-policy.env ./signer-policy.env
cp received-policy-bundle/protocol_context.json policy/
cp received-policy-bundle/advance-l2-agg-verifying-key.bin policy/
chmod 600 signer-policy.env attestation-signer.toml
```

The verifier checks the manifest, file hashes/sizes, identity membership and
`active / real / enforce` policy. Keep the received package unchanged as the
review record. Its `PARTNER-COMMANDS.md` describes rotation startup, not a second
key initialization or pre-genesis workflow.

**Before starting, fill your operator-owned RPC policy.** The TOML template
contains commented sections and is not a ready production policy. Existing
teams can copy their own reviewed RPC policy, but it may live in environment
variables as well as TOML. In this rehearsal the required source sets were:

- `ATTESTATION_SIGNER_ADVANCE_L1_TERMINAL_ANCHOR_SOURCE_SET_JSON`
- `ATTESTATION_SIGNER_ADVANCE_L2_ETHEREUM_SOURCE_SET_JSON`
- `ATTESTATION_SIGNER_ADVANCE_L2_L2_SOURCE_SET_JSON`

Retain those selected trust values privately if applicable. Do not copy the
entire old environment, WIF, transport key or database. New teams must obtain
their own source sets and credentials; the coordinator cannot invent independent
trust domains for them. Keep the new instance's rotation allowlists empty unless
it separately approves a future rotation.

Create `.env` next to Compose. `SIGNER_NAME` must differ from all old instances:

```bash
printf 'COMPOSE_PROJECT_NAME=%s\nSIGNER_IMAGE=%s\nSIGNER_HTTP_PORT=0\nSIGNER_METRICS_PORT=0\n' \
  "$SIGNER_NAME" "$SIGNER_IMAGE" > .env
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose port attestation-signer 4040
```

A new Compose project creates its own SQLite volume. Host port `0` asks Docker
for an unused loopback port; it prevents collisions with the old instance on the
same host. No public inbound signer endpoint is required. Query `/health` and
`/policy` at the loopback address printed by the last command (using curl or your
local HTTP client). For this handoff, confirm `advance_l1` and `advance_l2` have
`production_serving: true`. Global `/ready` can remain 503 when unrelated future
rotation capabilities have no approved targets; do not add invented allowlists
just to turn that endpoint green.

## 6. Current operators load their approved target and return receipts

Use the current instance's **existing** public identity JSON. If it was not
saved, export it from its existing local files using `identity.sh` with that
instance's reviewed image; do not run key initialization on it.

From the current instance's Compose directory, after independent approval:

```bash
CURRENT_CONTAINER=$(docker compose ps -q attestation-signer)
bash "$KIT/scripts/rotation.sh" approve ./proposal.json \
  --expected-sha256 "$PROPOSAL_SHA256" --current-key-hash "$CURRENT_KEY_HASH" \
  --identity ./identity.json --container "$CURRENT_CONTAINER"
```

For a service managed outside Compose, use its known Docker container name or
ID instead. The default config is `./attestation-signer.toml`. This must be the
actual single-file bind mount used by the container. The script backs it up,
adds only the exact approved target to its rotation allowlist, preserves the
file inode, restarts that container and verifies its rotation capability. It
never replaces keys or the database. Each current operator returns the generated
`rotation-approval-<digest>.json` through the authenticated channel.

## 7. New operators and bridge operator verify authenticated polling

The bridge operator checks recent successful TSO polls for **each new key**.
For the reference deployment, an authorized private inspection can use:

```bash
kubectl -n default port-forward --address=127.0.0.1 service/tso-service 13000:3000
```

From another terminal read `http://127.0.0.1:13000/metrics`. Inspect
`tso_core_signer_last_poll_timestamp_seconds{signer_pubkey="..."}` for each
new attestation public key. Confirm timestamps are recent and continue to
advance. This metric is updated after authenticated polling; a healthy process
or a registry entry alone is not evidence of connection. Stop the port-forward
after inspection. In other installations use the equivalent private metrics
endpoint, not a public TSO ingress.

Give each new operator their public-key-specific result through the authenticated
channel. In the new workspace, with the same reviewed proposal/digest/current
hash, run only after that connection is observed:

```bash
NEW_CONTAINER=$(docker compose ps -q attestation-signer)
bash "$KIT/scripts/rotation.sh" ready ./proposal.json \
  --expected-sha256 "$PROPOSAL_SHA256" --current-key-hash "$CURRENT_KEY_HASH" \
  --identity ./identity.json --container "$NEW_CONTAINER" \
  --acknowledge-tso-connected
```

Return `rotation-readiness-<digest>.json`. The acknowledgement records an observed
connection, not a guess. The script verifies local identity and AdvanceL1/L2
capabilities; it cannot independently query the bridge's private TSO metrics.
Receipts are JSON reports, not cryptographic signatures of Governance approval.
Their source must therefore be authenticated by the receiving coordinator.

## 8. Bridge operator collects receipts, checks, and stops

Store each operator's receipt under a unique filename, since all operators use
the same proposal digest. For example:

```text
rotations/rotation-003/receipts/
  current-a.json  current-b.json  current-c.json
  new-a.json      new-b.json      new-c.json
```

```bash
scrollsdk bridge rotation check --rotation-dir "$ROTATION"
```

This checks staged files, every current approval, every target readiness, live
admission and absence of a prior submission. It writes `check.json`, reports
all missing items, and exits with code 2 when blocked. It performs no WP
build/propose POST. A successful report has `readyForSubmissionChecks: true`,
`submitted: false` and `wpPreviewPerformed: false`.

**Stop here for a pre-submission rehearsal.** Keep both generations, records and
private backups. `apply` is a separate live operation that rechecks state and
performs WP preview/submission; it is deliberately not executed here. Actual
activation, subsequent WF progress, new-key signatures and retirement after the
overlap boundary require separate verification before stopping old instances.
Changing the plan after approval requires a new reviewed proposal and receipts.

See the [2026-10-11 rehearsal record](rotation-rehearsal-2026-10-11.md) for
commands actually exercised, discovered operator gaps and validation boundaries.
