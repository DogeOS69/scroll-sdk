#!/usr/bin/env bash
# Verify a versioned bridge bundle against an authenticated digest and core identity.
set -euo pipefail
if [ "${1:-}" = --help ]; then
  echo 'Usage: verify-handoff.sh BUNDLE EXPECTED_MANIFEST_SHA256 IDENTITY_JSON'
  echo 'Digest comes through the authenticated bridge/Governance channel; identity is core --print-identity output.'
  exit 0
fi
[ "$#" = 3 ] || { echo 'Expected bundle directory, authenticated manifest digest, and identity JSON.' >&2; exit 1; }
[[ "$2" =~ ^[0-9a-f]{64}$ ]] || { echo 'Expected a lowercase manifest SHA-256.' >&2; exit 1; }
bundle=$(cd -- "$1" && pwd -P)
[ -f "$3" ] && [ ! -L "$3" ] || { echo 'Identity must be a regular file.' >&2; exit 1; }
identity="$(cd -- "$(dirname -- "$3")" && pwd -P)/$(basename -- "$3")"
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
case "$bundle$identity$script_dir" in *,*) echo 'Docker bind paths cannot contain commas.' >&2; exit 1 ;; esac
exec docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$bundle,dst=/bundle,readonly" \
  --mount "type=bind,src=$identity,dst=/identity.json,readonly" \
  --mount "type=bind,src=$script_dir,dst=/tool,readonly" \
  --entrypoint python python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 \
  /tool/verify-handoff.py "$2"
