#!/usr/bin/env bash
# Signer-owned rotation approval. Docker/Bash only; never mount the Docker socket.
set -euo pipefail
usage() {
  cat <<'EOF'
Usage:
  rotation.sh inspect PROPOSAL --expected-sha256 DIGEST --current-key-hash HASH
  rotation.sh approve PROPOSAL --expected-sha256 DIGEST --current-key-hash HASH \
    --config FILE --container NAME --signer-public-key PUBKEY [--port 4040]
  rotation.sh ready PROPOSAL --expected-sha256 DIGEST --current-key-hash HASH \
    --config FILE --container NAME --signer-public-key PUBKEY \
    --transport-public-key PUBKEY --acknowledge-tso-connected [--port 4040]

Use a digest received through the agreed approval channel and corroborate the
current bridge hash independently. Approve changes local policy and restarts
only the explicitly named Docker container. It does not submit a rotation.
EOF
}
[ "${1:-}" != --help ] && [ "${1:-}" != -h ] || { usage; exit 0; }
[ "$#" -ge 2 ] || { usage >&2; exit 1; }
action=$1 proposal=$2
shift 2
case "$action" in inspect|approve|ready) ;; *) usage >&2; exit 1 ;; esac
expected='' current='' config='' container='' signer='' port=4040 transport='' acknowledge=false
while [ "$#" -gt 0 ]; do
  if [ "$1" = --acknowledge-tso-connected ]; then acknowledge=true; shift; continue; fi
  [ "$#" -ge 2 ] || { usage >&2; exit 1; }
  case "$1" in
    --expected-sha256) expected=$2 ;;
    --current-key-hash) current=$2 ;;
    --config) config=$2 ;;
    --container) container=$2 ;;
    --signer-public-key) signer=$2 ;;
    --port) port=$2 ;;
    --transport-public-key) transport=$2 ;;
    *) usage >&2; exit 1 ;;
  esac
  shift 2
done
[[ "$expected" =~ ^[0-9a-f]{64}$ && "$current" =~ ^0x[0-9a-f]{40}$ ]] \
  || { echo 'Expected digest and independently confirmed current bridge hash are required.' >&2; exit 1; }
[ -f "$proposal" ] && [ ! -L "$proposal" ] || { echo 'Proposal must be a regular, non-symlink file.' >&2; exit 1; }
proposal_dir=$(cd -- "$(dirname -- "$proposal")" && pwd -P)
proposal="$proposal_dir/$(basename -- "$proposal")"
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
case "$proposal$script_dir$config" in *,*) echo 'Docker bind paths cannot contain commas.' >&2; exit 1 ;; esac
image='python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
base=(docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --mount "type=bind,src=$script_dir,dst=/tool,readonly"
  --mount "type=bind,src=$proposal,dst=/proposal.json,readonly")
args=(--proposal /proposal.json --expected-sha256 "$expected" --current-key-hash "$current")
if [ "$action" = inspect ]; then
  exec "${base[@]}" --network none --entrypoint python "$image" /tool/rotation.py inspect "${args[@]}"
fi
[[ "$container" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ && "$signer" =~ ^0[23][0-9a-f]{64}$ && "$port" =~ ^[0-9]{1,5}$ ]] \
  || { echo 'Explicit container, signer public key and valid port are required.' >&2; exit 1; }
[ -f "$config" ] && [ ! -L "$config" ] || { echo 'Config must be a regular, non-symlink file.' >&2; exit 1; }
config_dir=$(cd -- "$(dirname -- "$config")" && pwd -P)
config="$config_dir/$(basename -- "$config")"
# Approval backups can contain RPC credentials. Refuse tracked/unignored outputs.
ancestor=$config_dir
while :; do
  if [ -e "$ancestor/.git" ]; then
    command -v git >/dev/null || { echo 'Git is needed to verify ignored private output.' >&2; exit 1; }
    [ -z "$(git -C "$ancestor" ls-files -- "$config_dir")" ] \
      || { echo 'Use a private directory outside Git or an entirely ignored directory.' >&2; exit 1; }
    git -C "$ancestor" check-ignore --quiet -- "$config_dir/" \
      || { echo 'Ignore the entire private configuration directory before approval.' >&2; exit 1; }
    break
  fi
  [ "$ancestor" != / ] || break
  ancestor=$(dirname -- "$ancestor")
done
args+=(--signer-public-key "$signer" --port "$port")
if [ "$action" = ready ]; then
  [[ "$transport" =~ ^0[23][0-9a-f]{64}$ ]] && [ "$acknowledge" = true ] \
    || { echo 'Readiness requires the target transport public key and explicit acknowledgement of authenticated TSO connectivity.' >&2; exit 1; }
  args+=(--transport-public-key "$transport" --acknowledge-tso-connected)
elif [ -n "$transport" ] || [ "$acknowledge" = true ]; then
  echo 'TSO acknowledgement and transport public key apply only to readiness.' >&2
  exit 1
fi
# Inspect only mount/command metadata and the presence of the allowlist override;
# do not read or print the rest of the container environment.
# Docker retains the original host spelling (for example a symlinked parent
# directory). Match the actual host file before passing that spelling into the
# isolated checker, which cannot resolve paths on the host filesystem.
host_config_source=$config
while IFS= read -r source; do
  if [ "$source" -ef "$config" ]; then host_config_source=$source; fi
done < <(docker inspect --format '{{range .Mounts}}{{println .Source}}{{end}}' "$container")
docker inspect --format '{"mounts":{{json .Mounts}},"command":{{json .Config.Cmd}},"override":{{ $found := false }}{{range .Config.Env}}{{if eq (index (split . "=") 0) "ATTESTATION_SIGNER_ALLOWED_NEXT_BRIDGE_SCRIPT_HASHES"}}{{$found = true}}{{end}}{{end}}{{$found}}}' "$container" |
  "${base[@]}" -i --network none --entrypoint python "$image" /tool/rotation.py container-check \
  "${args[@]}" --host-config "$host_config_source"
if [ "$action" = approve ]; then
  "${base[@]}" --network "container:$container" --entrypoint python "$image" /tool/rotation.py check "${args[@]}"
fi
base+=(--mount "type=bind,src=$config_dir,dst=/private")
args+=(--config "/private/$(basename -- "$config")")
if [ "$action" = ready ]; then
  "${base[@]}" --network "container:$container" --entrypoint python "$image" /tool/rotation.py ready "${args[@]}"
  printf 'Receipt: %s/rotation-readiness-%s.json\n' "$config_dir" "$expected"
  exit 0
fi
"${base[@]}" --network none --entrypoint python "$image" /tool/rotation.py approve "${args[@]}"
docker restart --time 15 "$container" >/dev/null
"${base[@]}" --network "container:$container" --entrypoint python "$image" /tool/rotation.py receipt "${args[@]}"
printf 'Receipt: %s/rotation-approval-%s.json\n' "$config_dir" "$expected"
