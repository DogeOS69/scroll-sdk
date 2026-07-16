# Running a DogeOS Attestation Signer (Signer-Operator Runbook)

You are one of N independent attestation signers securing a DogeOS bridge.
You deploy and operate **one service** — `attestation-signer` — on your own
infrastructure, holding your own signing key. The bridge operator never sees
your key; they only receive your **endpoint URL and public key**, and later
send you a **policy bundle** that binds your signer to the generated bridge.

The whole exchange is three steps:

```
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

**Local WIF backend** (simplest):

```bash
scrollsdk signer init --id <agreed-signer-id> --network testnet \
  --endpoint https://signer.your-org.example:4040
# → signer-<id>/attestation-signer.env   (SECRET — your signing key)
# → signer-<id>/descriptor.json          (public — send to bridge operator)
```

**AWS KMS backend**: create a secp256k1 signing key in your own AWS account,
fill the KMS block in `docker-compose/.env.example`, deploy (step 2), then
emit the descriptor from the running signer:

```bash
scrollsdk signer preflight --endpoint https://signer.your-org.example:4040 \
  --id <agreed-signer-id> --out descriptor.json
```

## Step 2 — deploy

### docker-compose (reference path)

```bash
cd docker-compose/
cp .env.example attestation-signer.env && chmod 600 attestation-signer.env
# paste the WIF from signer init (or fill the KMS block)
mkdir -p policy
docker compose up -d
curl -fsS http://localhost:4040/health   # → shows your public_key
```

### Helm (if you already run Kubernetes)

Use `helm/values-partner.example.yaml` with the `attestation-signer` chart
from this repository (`charts/attestation-signer`). Create the WIF Secret
yourself as described in the values file.

## Step 3 — verify and hand over

```bash
scrollsdk signer preflight --endpoint https://signer.your-org.example:4040 \
  --id <agreed-signer-id> \
  --expected-public-key <publicKey from signer init, if used> \
  --out descriptor.json
```

Send `descriptor.json` to the bridge operator. **The public key in it enters
the bridge multisig permanently at genesis — make sure it is the key you
intend to operate long-term.**

## Step 4 — apply the policy bundle (after bridge genesis)

The bridge operator sends back a bundle directory:

| file | what to do with it |
|---|---|
| `signer-policy.env` | replaces `docker-compose/signer-policy.env` |
| `verifier-registry.toml`, `source-set.toml` | copy into `docker-compose/policy/` |
| `values-overlay.yaml` | Helm deployments: merge into your values instead |
| `signer-policy.json` | machine-readable summary (for your records) |

Then `docker compose up -d` (or `helm upgrade`). The signer now enforces the
bridge identity (protocol instance, namespace, active bridge key hash) and
will start receiving `/sign` requests from the bridge operator's TSO.

## Network requirements (agree these with the bridge operator)

1. **Inbound** — the bridge operator's TSO must reach your signer's
   `POST /sign` (and `GET /health`).
2. **Outbound** — your signer calls back the TSO URL from the policy bundle
   to submit signatures.
3. **Outbound** — your signer fetches proof artifacts over HTTPS GET from
   the `signerProofArtifactBaseUrl` in the policy bundle.

There is currently **no application-layer authentication** on the
signer↔TSO HTTP path: connectivity must be private (VPN / WireGuard /
IP-allowlisted TLS reverse proxy). Agree the mechanism with the bridge
operator before exposing anything.

## Operations notes

- The SQLite volume holds the signer's audit/request database — persist it.
- The signer is otherwise stateless with respect to the bridge: it validates
  each request against its own policy config and signs independently.
- **Never run two live instances with the same key.** Run one; restore from
  the same key material if the host dies.
- Key rotation is a coordinated ceremony with the bridge operator (RotateKey
  transition) — do not rotate unilaterally.
