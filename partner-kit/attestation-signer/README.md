# Running a DogeOS Attestation Signer (Signer-Operator Runbook)

This is the generic, static manual for every signer operator. It explains the
roles, one-time setup, handoff, network contract, and operating rules, but it
does not contain addresses or commands for a particular bridge deployment.
After bridge genesis, the generated
`signer-policy-bundle/PARTNER-COMMANDS.md` supplied by the bridge operator is
the authoritative instruction file for that deployment.

You are one of N independent attestation signers securing a DogeOS bridge.
You deploy and operate **one service** — `attestation-signer` — on your own
infrastructure, holding your own signing key. The bridge operator never sees
your key; they only receive your **endpoint URL and public key**, and later
send you a **policy bundle** that binds your signer to the generated bridge.

The whole exchange has three phases. They are deliberately identical for mock
and production; the bridge operator's policy bundle selects the proof/signer
posture, so you do not pass a second mode flag:

```text
 ①  You:              generate key → deploy signer → send descriptor.json
 ②  Bridge operator:  collects all descriptors → generates the bridge
 ③  Bridge operator:  sends you the policy bundle → you apply it & restart
```

## What you need

- A host for one small container (2 vCPU / 1 GB is plenty) with a stable,
  reachable HTTPS endpoint (see Network requirements below).
- The `scrollsdk` CLI (only for key generation and preflight; the signer
  itself has no dependency on it).
- Optional but recommended for production: an AWS KMS key instead of a
  local WIF file.

## Step 1 — key + descriptor

Run every command from this `partner-kit/attestation-signer/` directory.
`signer init` writes everything into one directory (`signer-<id>/`) — a
complete deployment env plus the descriptor. The rest of the flow reads
from that directory; there is nothing to reconstruct by hand.

**Local WIF backend** (simplest):

```bash
scrollsdk signer init --id <agreed-signer-id> --network testnet \
  --endpoint https://signer.your-org.example:4040
# → signer-<id>/attestation-signer.env   (SECRET — holds the signing key)
# → signer-<id>/descriptor.json          (public — finalized in step 3)
```

**AWS KMS backend** (recommended for production) — one command instead of
key-juggling; the derived public key lands in the env and descriptor
automatically:

```bash
# Using a key you already created (ECC_SECG_P256K1, SIGN_VERIFY):
scrollsdk signer init --id <agreed-signer-id> --network testnet \
  --endpoint https://signer.your-org.example:4040 \
  --backend aws-kms --kms-key-id <KeyId-or-Arn> --kms-region <region> \
  --allowed-release-version <approved-cargo-version> \
  --allowed-git-commit <approved-full-40-character-git-sha>

# Or let the CLI create the key in your account:
scrollsdk signer init --id <agreed-signer-id> --network testnet \
  --endpoint https://signer.your-org.example:4040 \
  --backend aws-kms --create-key --kms-region <region> \
  --allowed-release-version <approved-cargo-version> \
  --allowed-git-commit <approved-full-40-character-git-sha>
```

The container additionally needs AWS credentials with `kms:Sign` +
`kms:GetPublicKey` on that key (EC2 instance role, or static keys — see the
commented lines in the generated env).

Low-level alternative: `scrollsdk signer kms-pubkey --key-id ... --region ...`
prints just the compressed public key, and the same value falls out of
standard tooling if your policy forbids vendor CLIs near AWS credentials:

```bash
aws kms get-public-key --key-id <KeyId> --region <region> --query PublicKey --output text \
  | base64 -d \
  | openssl ec -pubin -inform DER -conv_form compressed -outform DER 2>/dev/null \
  | tail -c 33 | xxd -p -c 33
```

## Step 2 — deploy

The endpoint is the base URL reachable **from the bridge operator's TSO
network**, not necessarily the signer's public Internet address. Production
normally uses a TLS domain. An isolated mock/VPN test may use a private address
such as `http://10.20.30.40:4040`. Never use `localhost`, a Docker service name,
or a Kubernetes-only name in the descriptor.

Deploy the Docker Compose reference:

```bash
cp "signer-<agreed-signer-id>/attestation-signer.env" docker-compose/
chmod 600 docker-compose/attestation-signer.env
mkdir -p docker-compose/policy

docker compose --project-directory docker-compose config --quiet
docker compose --project-directory docker-compose up -d

curl -fsS http://127.0.0.1:4040/health
curl -fsS https://signer.your-org.example:4040/health
```

The generated `attestation-signer.env` is the authoritative field list for
this signer; keep it private and do not rebuild it by hand.

## Step 3 — verify and hand over

```bash
scrollsdk signer preflight --dir signer-<agreed-signer-id>
# Add --endpoint https://... only when signer init did not set it.
```

`--dir` pulls the id, network, and expected public key from step 1's
descriptor, checks them against the running signer, and writes the verified
endpoint back into `signer-<id>/descriptor.json`.

Send `descriptor.json` to the bridge operator. **The public key in it enters
the bridge multisig permanently at genesis — make sure it is the key you
intend to operate long-term.** Never send `attestation-signer.env`, a WIF, or
AWS credentials.

## Step 4 — apply the policy bundle (after bridge genesis)

The bridge operator sends back a bundle directory:

| file | what to do with it |
|---|---|
| `signer-policy.env` | replaces `docker-compose/signer-policy.env` |
| `verifier-registry.toml`, `source-set.toml` | copy into `docker-compose/policy/` |
| `signer-policy.json` | machine-readable summary (for your records) |
| `PARTNER-COMMANDS.md` | authoritative mode, addresses, apply/restart commands, and reachability checks for this deployment |

Keep the received directory intact, place it at `signer-policy-bundle/` next
to `docker-compose/`, open its `PARTNER-COMMANDS.md`, and execute the
partner-operator section exactly as generated. Those commands place the files,
validate the resolved Compose configuration, restart the signer, and probe the
deployment-specific addresses. Do not reconstruct those commands from examples
in this static manual or substitute addresses from another deployment.

After those generated commands succeed, the signer enforces the bridge
identity (protocol instance, namespace, active bridge key hash) and starts
receiving `/sign` requests from the bridge operator's TSO.

Every bundle sets a positive, bounded proof-artifact cap. Mock mode selects the
same audited `staging_scaffold` posture as dogeos-core's e2e harness and leaves
both TEE allowlists empty by default because mock evidence has no TEE receipt.
Production selects fail-closed `production_enforce` and requires both TEE
allowlists to be non-empty. Your generated commands and network routes stay
the same.

Before applying a production bundle, `attestation-signer.env` must contain the
approved image identity pins. `scrollsdk signer init` writes them when passed
`--allowed-release-version` and `--allowed-git-commit`, and always writes the
approved signing-policy version. Missing or mismatched pins make the production
signer refuse to start.

The current dogeos-core signer still reports cryptographic STARK proof-byte
verification as `NotImplemented`; a production-enforce build therefore refuses
proof-backed signing until that check exists in the selected release. The mock
lane is the supported way to test the complete deployment/network/callback
flow with deterministic non-cryptographic proofs.

## Network requirements (agree these with the bridge operator)

1. **Inbound** — the bridge operator's TSO must reach your signer's
   `POST /sign` (and `GET /health`).
2. **Outbound** — your signer calls back the TSO URL from the policy bundle
   to submit signatures.
3. **Outbound** — your signer fetches proof artifacts over HTTPS GET from
   the full `required_proof_artifacts[].proof_artifact_fetch.url` carried in
   each signing request. `signer-policy.json` records the deployment's base URL
   for audit; the runtime request contains the concrete object URL.

After applying the policy, verify the deployment-specific TSO and signer
addresses printed in `signer-policy-bundle/PARTNER-COMMANDS.md`.

The bridge operator must separately repeat the signer `/health` request from
the actual TSO network. A successful laptop probe alone does not prove the
production route works.

There is currently **no application-layer authentication** on the signer↔TSO
HTTP path: connectivity must be private (VPN / WireGuard / IP-allowlisted TLS
reverse proxy). Agree the mechanism with the bridge operator before exposing
anything.

## Operations notes

- The SQLite volume holds the signer's audit/request database — persist it.
- The signer is otherwise stateless with respect to the bridge: it validates
  each request against its own policy config and signs independently.
- **Never run two live instances with the same key.** Run one; restore from
  the same key material if the host dies.
- Key rotation is a coordinated ceremony with the bridge operator (RotateKey
  transition) — do not rotate unilaterally.
