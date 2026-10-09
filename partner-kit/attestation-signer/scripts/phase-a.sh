#!/usr/bin/env bash
# Run from a private copy of the kit. The phase body matches scrollsdk's
# generated PARTNER-COMMANDS.md; keep both implementations aligned.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
: "${SIGNER_ID:?Set SIGNER_ID to the agreed signer ID}"
: "${DOGE_NETWORK:?Set DOGE_NETWORK to the agreed network}"

(
  set -eu
  # 1. Signing key and env, once (a rerun keeps them). The env selects pull
  #    delivery and the transport key file.
  [ -e "signer-$SIGNER_ID/attestation-signer.env" ] \
    || scrollsdk signer init --id "$SIGNER_ID" --network "$DOGE_NETWORK" ${SIGNER_INIT_FLAGS:-}
  # 2. Signing env and policy next to the Compose file, then the transport key:
  #    created locally only if absent, validated, installed.
  cp "signer-$SIGNER_ID/attestation-signer.env" "signer-$SIGNER_ID/attestation-signer.toml" docker-compose/
  chmod 600 docker-compose/attestation-signer.env
  (
    set -eu
    key="signer-$SIGNER_ID/transport.key"
    descriptor="signer-$SIGNER_ID/descriptor.json"
    # Only first-time initialization may create a key; never recover by rotating.
    if [ ! -e "$key" ]; then
      if [ -e "$descriptor" ] || [ -e docker-compose/transport.key ]; then
        echo "Transport key missing; restore the registered key before continuing" >&2
        exit 1
      fi
      umask 077
      openssl rand -hex 32 > "$key.new"
      ln "$key.new" "$key"
      rm -f "$key.new"
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
  # 3. Print the identity with the real backend, network and transport key
  #    (the same Compose service and mounts the runtime uses).
  docker compose --project-directory docker-compose run --rm --no-deps -T attestation-signer \
    -c /etc/dogeos-partner/attestation-signer.toml --print-identity > "signer-$SIGNER_ID/identity.json.new"
  mv "signer-$SIGNER_ID/identity.json.new" "signer-$SIGNER_ID/identity.json"
  # 4. Wrap it into descriptor.json (read-only for the existing signer).
  scrollsdk signer init --id "$SIGNER_ID" --network "$DOGE_NETWORK" --identity "signer-$SIGNER_ID/identity.json"
)
