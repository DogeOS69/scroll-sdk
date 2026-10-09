#!/usr/bin/env bash
# Run from a private copy of the kit. The phase body matches scrollsdk's
# generated PARTNER-COMMANDS.md; keep both implementations aligned.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
: "${SIGNER_ID:?Set SIGNER_ID to the agreed signer ID}"
# Production readiness by default; set PREFLIGHT_FLAGS empty only for observe.
: "${PREFLIGHT_FLAGS=--require-production-ready}"

(
  set -eu
  cp "signer-$SIGNER_ID/attestation-signer.env" "signer-$SIGNER_ID/attestation-signer.toml" docker-compose/
  chmod 600 docker-compose/attestation-signer.env
  (
    set -eu
    key="signer-$SIGNER_ID/transport.key"
    descriptor="signer-$SIGNER_ID/descriptor.json"
    # Registration is complete: missing inputs must never generate a new key.
    if [ ! -f "$key" ] || [ ! -f "$descriptor" ]; then
      echo "Transport key or descriptor missing; restore the registered files before continuing" >&2
      exit 1
    fi
    # The whole file must be exactly 64 lowercase hex characters and a newline.
    if [ "$(wc -c < "$key")" -ne 65 ] || [ "$(tail -c 1 "$key" | wc -l)" -ne 1 ] \
      || ! head -c 64 "$key" | grep -Eqx '[0-9a-f]{64}'; then
      echo "$key must be exactly one line of 64 hex characters; restore it (rotation is a separate step)" >&2
      exit 1
    fi
    # Node is already required by scrollsdk. Derive the compressed secp256k1
    # public key locally; never print the private key or pass it in argv.
    node --input-type=commonjs -e '
      const fs = require("node:fs");
      const {createECDH} = require("node:crypto");
      try {
        const key = createECDH("secp256k1");
        key.setPrivateKey(Buffer.from(fs.readFileSync(process.argv[1], "utf8").trim(), "hex"));
        if (fs.existsSync(process.argv[2])) {
          const descriptor = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
          if (typeof descriptor.transportPubkey !== "string" ||
              descriptor.transportPubkey.toLowerCase() !== key.getPublicKey("hex", "compressed")) {
            throw new Error();
          }
        }
      } catch {
        console.error("Transport key invalid or does not match descriptor; restore the registered files");
        process.exit(1);
      }
    ' "$key" "$descriptor"
    # Install atomically: the runtime key is replaced only by a validated copy.
    cp "$key" docker-compose/transport.key.new
    chmod 600 docker-compose/transport.key.new
    mv -f docker-compose/transport.key.new docker-compose/transport.key
  )
  mkdir -p docker-compose/policy
  cp signer-policy-bundle/signer-policy.env docker-compose/signer-policy.env
  cp signer-policy-bundle/protocol_context.json docker-compose/policy/protocol_context.json
  # Production bundles also carry the aggregate verifying key.
  if [ -e signer-policy-bundle/advance-l2-agg-verifying-key.bin ]; then
    cp signer-policy-bundle/advance-l2-agg-verifying-key.bin docker-compose/policy/advance-l2-agg-verifying-key.bin
  fi
  docker compose --project-directory docker-compose config --quiet
  docker compose --project-directory docker-compose up -d
  scrollsdk signer preflight --dir "signer-$SIGNER_ID" ${PREFLIGHT_FLAGS:-}
)
