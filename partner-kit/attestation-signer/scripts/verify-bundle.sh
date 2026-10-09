#!/usr/bin/env bash
# Read-only verification before installing the operator's policy bundle.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
: "${SIGNER_ID:?Set SIGNER_ID to the agreed signer ID}"
: "${EXPECTED_MANIFEST_SHA256:?Set the manifest SHA-256 received from the operator}"
if [[ ! "$EXPECTED_MANIFEST_SHA256" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo 'Expected manifest SHA-256 must contain exactly 64 hex characters' >&2
  exit 1
fi

printf '%s  %s\n' "$EXPECTED_MANIFEST_SHA256" signer-policy-bundle/signer-policy-manifest.json |
  sha256sum --check --strict
(
  cd signer-policy-bundle
  jq -r '.files[] | "\(.sha256 | sub("^sha256:"; ""))  \(.file)"' \
    signer-policy-manifest.json | sha256sum --check --strict
)
jq -e --slurpfile descriptor "signer-$SIGNER_ID/descriptor.json" '
  .contract == "attestation_evidence_v2" and
  .network == $descriptor[0].network and
  any(.signers[];
    .id == $descriptor[0].id and
    .publicKey == $descriptor[0].publicKey and
    .transportPubkey == $descriptor[0].transportPubkey)
' signer-policy-bundle/signer-policy.json >/dev/null
echo 'Bundle integrity and signer descriptor match. Review the deployment policy before Phase B.'
