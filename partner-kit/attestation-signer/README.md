# Attestation-signer operator manual

This is the **single operating manual** for a signer: first installation,
normal operation, AWS KMS, and both sides of RotateKey. Copy this entire kit
into a private directory and run its `signer.sh` there. You do **not** need
scroll-sdk-cli, a host Node/Python/OpenSSL installation, or a Dogecoin node.

The host needs Bash, Docker, and Docker Compose v2. Commands below run on Linux, macOS, or WSL. Docker
must be able to run the selected signer image's architecture. The signer polls
TSO outbound; it needs **no public inbound port**, public IP, or TLS certificate.

The short path is: **copy → initialize → register public keys → import the
deployment kit and configure trusted RPCs → start and check**.

## 1. Copy the template into a private runtime directory

Obtain a reviewed SDK checkout or an archive of this **whole kit** from the
bridge operator. Ask for the SDK revision, signer image digest and matching
release/commit/policy pins. Do not download individual scripts from different
revisions. With an existing reviewed checkout:

```bash
cp -a /path/to/reviewed-scroll-sdk/partner-kit/attestation-signer "$HOME/dogeos-signer-a"
cd "$HOME/dogeos-signer-a"
```

Copy the clean template, never another running signer's directory. The runtime
directory may be inside your deployment Git repository. Initialization adds
ignore rules for generated private keys, credentials and database
automatically; tracked public templates/scripts do not block it.
Only a private output file that is already tracked needs to be untracked first.
Review your own TOML before any commit: ignore rules do not hide tracked files.

The supplied `.env.example` pins the official beta.6a image and its matching
binary identity. If your bridge uses another approved release, copy it to
`.env`, fill `COMPOSE_PROJECT_NAME`, and update all four `SIGNER_*` image/pin
fields as directed by the release owner **before initialization**. These are
not secrets. Do not substitute an arbitrary image or proof release.

## 2. Initialize your identity

Agree a stable name and the Dogecoin network with the bridge operator. Names
must be unique among simultaneously running Compose projects on this host.
For a local signing key:

```bash
./signer.sh init --name signer-a --network testnet
```

Use `mainnet`, `testnet`, or `regtest` as appropriate. No RPC connection or
deployment kit is needed for local initialization. The script runs cryptography
inside a pinned Docker Official Node image with networking disabled. It does
not start the signer. For AWS KMS, use the alternative immediately below.

| File in this directory | Purpose | May be shared? |
| --- | --- | --- |
| `attestation-signer.env` | Local WIF **or** KMS reference and pinned public key; binary approval pins | No |
| `transport.key` | Independent local transport private key used to authenticate to TSO | No |
| `public-identity.json` | Name, network, labelled `attestationPubkey` and `transportPubkey` | Yes |
| `identity.json` | Core public descriptor format: schema, network, `publicKey`, `transportPubkey` | Yes, where the portal accepts this format |
| `.env` | Compose project name, approved image/pins, local port choices | Review before sharing |
| `data/` | This instance's SQLite database and related files | No |

The terminal displays the **two public keys**, never the private keys. To see
them again, run `./signer.sh identity`. Backup both private identity files.
Rerunning the same initialization verifies and reuses a complete identity; it
never rotates keys. Incomplete or mismatched files stop initialization. Restore
from backup instead of deleting files to get past a check. An interrupted
`.init.lock` or `.key-init.lock` may be removed only after confirming no
initializer is still running.

### AWS KMS alternative (attestation key only)

The attestation key supports `local` or `aws-kms`; the transport key remains a
local file. KMS private key material stays in AWS. The bridge operator receives
the same two public keys regardless of backend.

Prepare AWS access **for containers**, not just a host CLI session. Copy
`aws.env.example` to `aws.env`, then provide temporary credentials there or
select a dedicated profile backed by `aws/config` and `aws/credentials` in this
runtime directory. Keep these files mode `0600` and directory `aws/` mode `0700`.
On an appropriate AWS host, an accessible instance IAM role can supply credentials
without populated files. The script does not automatically mount your home AWS
folder, export host credentials or refresh expired sessions. Never enter secrets
in command arguments, Governance, or the deployment kit.

The same `aws.env` and read-only `aws/` mount are used by the AWS CLI container
and the signer container. A host SSO login/cache is not automatically forwarded;
use a credential method available to both, and arrange refresh for long-running
service credentials. See the [official AWS CLI container documentation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-docker.html)
for the container/host credential boundary.

If your host already has a working AWS CLI profile (including an authenticated
SSO profile), the shortest setup is to export **that selected identity** into
this directory's `aws.env`. Run from the signer runtime directory:

```bash
# Use the host's currently selected/default AWS profile.
(umask 077; aws configure export-credentials --format env-no-export > aws.env.new && mv aws.env.new aws.env)

# OR select a specific existing profile:
(umask 077; aws configure export-credentials --profile YOUR_PROFILE_NAME \
  --format env-no-export > aws.env.new && mv aws.env.new aws.env)
```

`YOUR_PROFILE_NAME` is the same profile you use for your intended AWS account;
check it on the host with `aws sts get-caller-identity --profile YOUR_PROFILE_NAME`
if unsure. These commands write credentials directly to a private file, not the
terminal. The temporary file is ignored by the kit and an existing `aws.env`
is replaced only after a successful export. If your profile uses SSO and its
login has expired, first renew it using `aws sso login --profile YOUR_PROFILE_NAME`.
The exported file is a credential snapshot, not a live link to the host login.
For temporary credentials, repeat the export before expiry and recreate the
running signer with `./signer.sh start` to load the refreshed values.

Host AWS CLI is an **optional convenience** for this export, not a signer-kit
dependency. Without it, use the `aws.env.example` credential fields, the dedicated
`aws/` profile files, or an accessible instance IAM role described above.

Then choose one initialization command:

```bash
# Read an EXISTING ECC_SECG_P256K1 / SIGN_VERIFY key:
./signer.sh init --name signer-a --network testnet --backend aws-kms \
  --kms-region us-east-1 --kms-key-id '<YOUR_KEY_ID_OR_ARN>'

# OR explicitly create a NEW signing key in your AWS account:
./signer.sh init --name signer-a --network testnet --backend aws-kms \
  --kms-region us-east-1 --create-key
```

The key ID/ARN and region come from your AWS account or its administrator.
Initialization uses a pinned official AWS CLI image, first checks container
credentials with STS, then validates the key's type,
usage and curve, derives its compressed public key, and writes the correct
runtime fields automatically. It does not ask you to type a matching public key.

Existing-key initialization needs `kms:GetPublicKey` on that key. Creating a
key additionally needs `kms:CreateKey`; creation incurs AWS resource charges.
The running signer needs `kms:GetPublicKey` and `kms:Sign` on **only its key**.
Configure both IAM and the KMS key policy as necessary; do not grant signing
access across all keys. Creation privilege is not required for normal operation.

`Workspace ready` means local files are prepared; it does **not** mean a KMS key
has been created. Initialization is complete when the two public keys and the
`public-identity.json` / `identity.json` locations are printed.

If the command reports **AWS authentication failed ... No KMS creation was
attempted**, configure or refresh the container credentials, then rerun the
same initialization command. Details are in private `.kms/auth-error.log`.
The older message `KMS creation failed or its outcome is uncertain` can also
have been caused by `Unable to locate credentials` in `.kms/provider-error.log`.
The updated script recognizes that specific pre-request failure after AWS
authentication succeeds, so it can retry without manual removal of records.
It does not treat network timeouts or lost creation responses this way.

A successful creation is recorded under `.kms/` before identity generation.
Reruns reuse that key. If creation's response is lost, the command refuses an
automatic creation retry: inspect your AWS audit records and the private
`.kms/provider-error.log`, identify any created key, and resume with
`--kms-key-id`. Do not clear this record and unknowingly create more keys.
No AWS provider error output is printed into public logs by initialization.

## 3. Register your two public keys in DogeOS Governance

Open the **DogeOS Governance** deployment selected by your bridge operator.
Paste the attestation and transport public keys into their respective fields
on **the same signer record**, associate your team, and use the agreed name.
Alternatively upload `identity.json` if that portal version supports the core
public descriptor format; otherwise use the two labelled fields from
`public-identity.json`. Portal upload compatibility is not inferred merely from
a filename. No automatic Governance API integration is performed by this kit.

If you paste public keys, no additional identity-file handoff is required.
Never upload the entire directory, `attestation-signer.env`, `transport.key`,
AWS credentials, database, or private RPC configuration.

## 4. Import the deployment kit and configure your RPC trust

The bridge operator exports one **deployment kit** per deployment and kit
version, and publishes it unchanged at an immutable URL. The deployment's
approved Governance record lists the kit version, its download URL and its
**manifest SHA-256**. Copy the SHA-256 from that record, not from a file that
came with the download. If the kit is an archive, unpack it first; `import`
takes the directory.

```bash
./signer.sh import ./deployment-kit-k-10918298dde4 '<MANIFEST_SHA256_FROM_THE_GOVERNANCE_RECORD>'
```

`import` requires a stopped signer. It verifies the manifest against that
digest, every listed file's SHA-256 and size, that the kit is for your
signer's network, `enforce` mode, the verifier material, and that
`deployment-kit.json`, `deployment-kit.env` and the files agree. It stores an
immutable copy under `bundles/<manifest-sha256>/` and selects it with
`active-bundle`. `start` verifies `active-bundle/` against its manifest again
on every start and refuses to start on any mismatch. `signer.sh` uses only this
kit's `docker-compose.yml`: a `docker-compose.override.yml` or `COMPOSE_FILE` is
ignored, and `start` refuses a Compose file that changes the signer command or
the `/etc/dogeos` mount.

| Kit file | Meaning |
| --- | --- |
| `deployment-kit.json` | Network, protocol instance id, kit version (`k-<12 hex>`), TSO URL, artifact origin, context and verifier digests |
| `deployment-kit.env` | The same bridge-owned runtime fields, loaded by Compose |
| `protocol_context.json` | Canonical deployment/genesis context |
| `advance-l2-agg-verifying-key.bin` | Production AdvanceL2 aggregate verifying key |
| `deployment-kit-manifest.json` | File sizes and SHA-256 hashes; its own SHA-256 is the kit identity |

The kit holds no signer list and no rotation material. `import` and `start`
reject kit fields that would set your private key, RPC trust, binary pins or
rotation permissions, and `start` refuses local env files that override a kit
field. They never change `attestation-signer.env`,
`transport.key`, `attestation-signer.toml`, `identity.json`, AWS credentials
or the database. Image, commit and policy pins come from the approved release
record, not from the kit.

Edit **your** `attestation-signer.toml` in this directory. Fill these three source sets; the template already provides two entries
for each:

| Source set | Used for | Who supplies/approves it? |
| --- | --- | --- |
| `advance_l1_policy.terminal_anchor_sources` | Dogecoin terminal anchor verification | Your trusted Dogecoin providers; bridge operator identifies network/shadowfork |
| `advance_l2_policy.ethereum_sources` | Ethereum canonicality/finality | Your trusted providers for this deployment's Ethereum DA network |
| `advance_l2_policy.l2_sources` | Exact DogeOS L2 state-root verification | Your trusted providers for this specific L2 deployment |

Each set in `enforce` requires `posture = "quorum"`,
`required_agreement >= 2`, and at least two independent trust domains. Two URLs
for the same backend are not independent. Ethereum here must match the DA
network, unlike a Fee Oracle's optional mainnet price source. A container's
`localhost` refers to that container, not the host or another machine.

Dogecoin sources optionally accept `rpc_user` and `rpc_password` alongside
`rpc_url` in TOML. Fill both or omit both. API keys in a provider's URL path
also make this file private; URL userinfo, query and fragment are not supported
by the current core source policy. This template does not promise arbitrary
header-based authentication. Use providers supported by the selected release.

Initialization sets this TOML to mode `0600`. Keep that permission and never
upload it. The three source sets are read directly from TOML; no hand-written
JSON or conversion is needed. Remove these old env overrides if migrating:

- `ATTESTATION_SIGNER_ADVANCE_L1_TERMINAL_ANCHOR_SOURCE_SET_JSON`
- `ATTESTATION_SIGNER_ADVANCE_L2_ETHEREUM_SOURCE_SET_JSON`
- `ATTESTATION_SIGNER_ADVANCE_L2_L2_SOURCE_SET_JSON`

`start` checks the resolved Compose environment and refuses these overrides,
even empty ones, because core would otherwise ignore the corresponding TOML.
A populated legacy `operator.env` also blocks startup until its settings are
moved into the supported TOML fields. Operator credentials remain local; the
deployment kit must not replace these trust decisions.

Leave `allowed_next_bridge_script_hashes` and `allowed_next_sequencer_signers`
empty/unset until separately approving those operations. Normal startup does
not require pre-approving an unknown future rotation.

## 5. Start and check

```bash
./signer.sh start
./signer.sh check
```

`start` performs Compose validation and starts/recreates only this signer.
`check` verifies the runtime attestation identity, network, `enforce`, and serving
AdvanceL1/AdvanceL2 capabilities. Retry after startup if necessary; failures
must be investigated, not bypassed. An unrelated global `/ready` 503 caused by
unapproved future rotation targets does not fail this normal-service check.

Check also with the bridge operator that your **specific registered public key**
has recent, advancing authenticated TSO polls. On their private TSO metrics,
`tso_core_signer_last_poll_timestamp_seconds{signer_pubkey="..."}` provides
that evidence. The operator must actually observe it: Docker health, a TSO
registry entry, or a locally serving capability does not prove connectivity.
Coordinate a real request and confirm artifact retrieval, verification, signed
submission and TSO receipt before claiming end-to-end signing acceptance.

No public signer endpoint is required. Ports default to randomly assigned
loopback ports so new and old instances can coexist. Find them with:

```bash
docker compose port attestation-signer 4040
docker compose port attestation-signer 9100
```

Use the first address for local `/health` and `/policy`, and the second for
`/metrics`. `docker compose ps` only reports process/health status.

## Kit updates and RotateKey

**New signer.** Import the deployment's current kit once (steps 1–5).

**Existing signer, ordinary rotation.** An attestation-key rotation does
**not** need a new kit and existing signers do not re-import. In the old
signer's directory, check the rotation export the bridge operator sends you:

```bash
./signer.sh inspect ./rotation-export.json
```

It re-verifies the active kit, then runs the signer image's `inspect-rotation`
offline with only the kit's network and protocol context; your keys, TOML and AWS files are not
passed to it. That subcommand needs a signer release that includes it; the
beta.6a image pinned in `.env.example` does not. It prints the decoded old/new
sets, the grace and the exact `allowed_next_bridge_script_hashes` line. After
your team's review, add that line to `attestation-signer.toml` and restart with
`./signer.sh start`, one signer at a time. The new signers are set up as new
signers above, in new directories with new keys and databases.

**Kit update.** A change of endpoints or verifier material is a new kit version
with its own Governance record; a published kit is never overwritten. Use
**stop → import → start**:

```bash
./signer.sh stop
./signer.sh import ./deployment-kit-k-<new 12 hex> '<NEW_MANIFEST_SHA256_FROM_THE_RECORD>'
./signer.sh start
```

**Upgrading from the old bundle format.** A signer that imported a
`signer-policy-bundle` with an earlier version of this kit re-imports **once**
after updating these scripts, and only once the deployment's kit record is
approved in Governance. Use the same stop → import → start; `start` refuses
the old bundle. Keys, database and TOML are kept.

## Routine operation, backup and troubleshooting

```bash
./signer.sh logs       # Private diagnostics; redact before sharing
./signer.sh check
./signer.sh stop
./signer.sh start
```

For a normal restart, `docker compose restart attestation-signer` preserves the
identity and database. After image/env/kit changes use `./signer.sh start`
which recreates the container so those changes are read. Stop before importing
a new kit; review image and binary pins together. Never rerun key creation
to perform an upgrade. Do not launch two instances with the same signing key.

The database is in **this directory's `data/`**, not an anonymous/named Docker
volume. Changing directory contents, restoring another signer's `data/`, or
running two containers against it changes/corrupts operational state. The
legacy `docker-compose/` reference uses a named volume; do not confuse its
storage with this new root-level Compose file or migrate a live instance merely
by copying that file.

For a consistent backup, stop the signer, then archive this private directory
(including dotfiles, both keys/KMS references, `data/`, bundles, active link,
TOML and private env) into your secure backup location. For
example, with an existing private backup directory:

```bash
./signer.sh stop
umask 077
tar -czf "$HOME/private-backups/signer-a-$(date -u +%Y%m%dT%H%M%SZ).tgz" .
./signer.sh start
```

The archive contains secrets; never attach it to Governance or an issue. KMS
private material is not in this archive: restoring a KMS signer also requires
access to the **same** key and AWS account. Restore the directory with original
permissions and review image/database compatibility before starting. Never
restore while the original instance still runs. A new image's database migration
may make rollback unsafe; preserve a stopped pre-upgrade backup.

| Symptom | Action |
| --- | --- |
| Initialization rejects partial files | Restore the original complete identity; do not generate replacement keys |
| KMS lookup/signing fails | Check container credentials, expiry, region, expected public key, IAM and key policy; inspect private provider diagnostics |
| Import fails | Check the manifest SHA-256 from the Governance record, an unpacked complete kit, and its network |
| Start refuses the active kit | Re-import the approved kit; never edit files under `bundles/` |
| Local checks fail | Inspect `/policy` for AdvanceL1/L2 blocks; check RPC quorum, release pins, proof artifacts and network |
| `/ready` is 503 only for future rotations | Keep those targets unapproved; use the capability-specific check above |
| No TSO polls | Check outbound DNS/routes, TSO endpoint, transport registration and clock; local health is insufficient |
| No proof artifact access | Check the request's proof-store origin/access, not the Ethereum DA blob bucket |
| Stop takes up to 60 seconds | Compose sends SIGTERM, then may force-kill after the grace period; do not mistake a forced exit for an application-level drain or delete SQLite files |
| Port already used | Keep dynamic loopback ports or choose unique explicit ports in `.env` |

Monitor queue age, worker failures, artifact fetch, source-set verdicts and
per-capability serving state from `/metrics`. Global readiness includes future
rotation capabilities, so it is not a substitute for capability-specific
alerts. Keep HTTP/metrics on loopback, or explicitly restrict a private/VPN
monitoring listener. Do not expose these ports publicly to operate a signer.

The nested `docker-compose/` files remain as a legacy reference for existing
CLI-managed deployments. They are not steps in this standalone workflow. Do not
run them over a newly initialized directory. Historical rehearsal records
are evidence of those runs, not an alternative operating manual.
