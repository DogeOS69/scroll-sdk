#!/usr/bin/env bash
# Standalone local-key onboarding. No scrollsdk, Node.js or OpenSSL on the host.
set -euo pipefail
usage() {
  echo 'Usage: init-keys.sh --name <signer-name> --network <mainnet|testnet|regtest> --out <private-directory>'
}
signer_name='' signer_network='' output_dir=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --name|--network|--out)
      [ "$#" -ge 2 ] || { usage >&2; exit 1; }
      case "$1" in
        --name) signer_name=$2 ;;
        --network) signer_network=$2 ;;
        --out) output_dir=$2 ;;
      esac
      shift 2 ;;
    *) usage >&2; exit 1 ;;
  esac
done
[[ "$signer_name" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] && [ "${#signer_name}" -le 63 ] \
  || { echo 'A stable DNS-label signer name is required.' >&2; exit 1; }
case "$signer_network" in mainnet|testnet|regtest) ;; *) usage >&2; exit 1 ;; esac
[ -n "$output_dir" ] || { usage >&2; exit 1; }
command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
umask 077
mkdir -p -- "$output_dir"
output_dir=$(cd -- "$output_dir" && pwd -P)
# Outside Git, Docker and Bash are sufficient. In an operator's Git workspace,
# require Git to verify explicit ignore rules and reject any tracked output.
ancestor=$output_dir
while :; do
  if [ -e "$ancestor/.git" ]; then
    command -v git >/dev/null || { echo 'Git is required to verify an ignored output directory inside a checkout.' >&2; exit 1; }
    [ -z "$(git -C "$ancestor" ls-files -- "$output_dir")" ] \
      || { echo 'Output contains tracked files; choose an untracked private directory.' >&2; exit 1; }
    for candidate in "$output_dir/" "$output_dir/attestation-signer.env" "$output_dir/transport.key" "$output_dir/public-identity.json"; do
      git -C "$ancestor" check-ignore --quiet -- "$candidate" \
        || { echo 'Choose an output directory outside Git, or explicitly ignore the entire private directory first.' >&2; exit 1; }
    done
    break
  fi
  [ "$ancestor" != / ] || break
  ancestor=$(dirname -- "$ancestor")
done
case "$output_dir$script_dir" in *,*) echo 'Docker bind-mount paths must not contain commas.' >&2; exit 1 ;; esac

# Multi-platform Docker Official Image, pinned so a mutable tag cannot change
# the key generator's runtime. The script uses only Node's built-in crypto/fs.
image='node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392'
exec docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$script_dir,dst=/keygen,readonly" \
  --mount "type=bind,src=$output_dir,dst=/output" \
  --entrypoint node "$image" /keygen/init-keys.mjs \
  --name "$signer_name" --network "$signer_network" --out /output
