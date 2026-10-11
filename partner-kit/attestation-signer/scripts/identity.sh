#!/usr/bin/env bash
# Export the real core identity using an existing local signer workspace.
# Outputs public JSON only. Never starts a service or makes a network request.
set -euo pipefail
if [ "${1:-}" = --help ] || [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo 'Usage: identity.sh REVIEWED_SIGNER_IMAGE [WORKSPACE=.]'
  echo 'WORKSPACE contains attestation-signer.env and transport.key from init-keys.sh.'
  echo 'Image comes from the approved deployment release, preferably pinned by digest.'
  [ "${1:-}" = --help ] && exit 0
  exit 1
fi
image=$1
workspace=$(cd -- "${2:-.}" && pwd -P)
[[ "$image" != -* && "$image" != *[[:space:]]* ]] || { echo 'Invalid image reference.' >&2; exit 1; }
for filename in attestation-signer.env transport.key; do
  [ -f "$workspace/$filename" ] && [ ! -L "$workspace/$filename" ] || { echo "Missing regular $filename; restore the registered identity." >&2; exit 1; }
done
grep -qx 'ATTESTATION_SIGNER_BACKEND=local' "$workspace/attestation-signer.env" || { echo 'This offline export is for local keys; KMS export requires a configured AWS credential provider.' >&2; exit 1; }
case "$workspace" in *,*) echo 'Docker bind paths cannot contain commas.' >&2; exit 1 ;; esac
# Pull the reviewed image explicitly first; the identity command itself is offline.
exec docker run --rm --pull never --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
  --env-file "$workspace/attestation-signer.env" \
  --mount "type=bind,src=$workspace/transport.key,dst=/etc/dogeos-partner/transport.key,readonly" \
  --entrypoint /usr/local/bin/attestation_signer "$image" --print-identity
