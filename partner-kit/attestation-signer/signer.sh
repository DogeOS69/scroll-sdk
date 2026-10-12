#!/usr/bin/env bash
# Standalone signer operator entry point. Docker + Compose + Bash; no scrollsdk.
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd "$root"
python_image='python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
aws_image='public.ecr.aws/aws-cli/aws-cli:2.31.18@sha256:d3f5b7078a71fd7cb488719571c50abd252f4320cdf375601f2d6d40caf97b55'
fail() { echo "$*" >&2; exit 1; }
usage() {
  cat <<'EOF'
Run from a private copy of this kit (see README.md):
  ./signer.sh init --name signer-a --network testnet [--backend local]
  ./signer.sh init --name signer-a --network testnet --backend aws-kms \
    --kms-region us-east-1 (--kms-key-id KEY | --create-key)
  ./signer.sh identity
  ./signer.sh import RECEIVED_BUNDLE AUTHENTICATED_MANIFEST_SHA256
  ./signer.sh start
  ./signer.sh check
  ./signer.sh rotation inspect PROPOSAL --expected-sha256 SHA --current-key-hash HASH
  ./signer.sh rotation approve PROPOSAL --expected-sha256 SHA --current-key-hash HASH
  ./signer.sh rotation ready PROPOSAL --expected-sha256 SHA --current-key-hash HASH --acknowledge-tso-connected
  ./signer.sh stop
  ./signer.sh logs
KMS creates cloud resources ONLY with explicit --create-key. Existing keys use GetPublicKey.
Public keys: public-identity.json (named pair) and identity.json (core upload format).
EOF
}
case "${1:---help}" in --help|-h) usage; exit 0 ;; esac
command -v docker >/dev/null || fail 'Docker is required.'
case "$root" in *,*) fail 'Docker bind paths cannot contain commas.' ;; esac
protect_outputs() {
  bash "$root/scripts/protect-output.sh" "$root"
}

py=(docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --mount "type=bind,src=$root,dst=/workspace")
setting() {
  local name=$1 file=${2:-.env} line value=''
  [ -f "$file" ] && [ ! -L "$file" ] || fail "Missing regular configuration file: $file"
  while IFS= read -r line; do
    case "$line" in "$name="*) [ -z "$value" ] || fail "Duplicate setting: $name"; value=${line#*=} ;; esac
  done < "$file"
  [ -n "$value" ] || fail "Missing setting: $name"
  printf '%s' "$value"
}
assert_stopped() {
  local project running
  project=$(setting COMPOSE_PROJECT_NAME)
  running=$(docker ps -q --filter "label=com.docker.compose.project=$project" --filter 'label=com.docker.compose.service=attestation-signer')
  [ -z "$running" ] || fail 'Stop this signer before importing configuration. Keys and database are preserved.'
}
container_id() {
  local container
  container=$(docker compose ps -q attestation-signer)
  [[ "$container" =~ ^[0-9a-f]+$ ]] || fail 'Expected one running signer in this Compose project.'
  printf '%s' "$container"
}
action=$1; shift
case "$action" in
  init)
    protect_outputs
    name='' network='' backend=local region='' key_id='' create=false
    while [ "$#" -gt 0 ]; do
      if [ "$1" = --create-key ]; then create=true; shift; continue; fi
      [ "$#" -ge 2 ] || fail 'Missing option value; use --help.'
      case "$1" in
        --name) name=$2 ;; --network) network=$2 ;; --backend) backend=$2 ;;
        --kms-region) region=$2 ;; --kms-key-id) key_id=$2 ;; *) fail 'Unknown initialization option.' ;;
      esac
      shift 2
    done
    [[ "$name" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ && ${#name} -le 63 ]] || fail 'Use a stable DNS-label signer name.'
    case "$network" in mainnet|testnet|regtest) ;; *) fail 'Select mainnet, testnet or regtest.' ;; esac
    case "$backend" in local|aws-kms) ;; *) fail 'Select local or aws-kms.' ;; esac
    if [ "$backend" = local ]; then
      [ -z "$region$key_id" ] && [ "$create" = false ] || fail 'KMS options require --backend aws-kms.'
    else
      [[ "$region" =~ ^[a-z]{2}(-[a-z]+)+-[0-9]+$ ]] || fail 'A valid KMS region is required.'
      if [ "$create" = true ]; then [ -z "$key_id" ] || fail 'Choose --create-key OR --kms-key-id.'
      else [[ -n "$key_id" && "$key_id" != -* && "$key_id" != *[[:space:]]* ]] || fail 'A KMS key ID or ARN is required.'; fi
    fi
    mkdir .init.lock 2>/dev/null || fail 'Initialization is locked; inspect any interrupted operation before removing .init.lock.'
    trap 'rmdir "$root/.init.lock"' EXIT
    "${py[@]}" --network none --entrypoint python "$python_image" /workspace/scripts/runtime.py prepare "$name"
    pins=(--release-version "$(setting SIGNER_RELEASE_VERSION)" --git-commit "$(setting SIGNER_GIT_COMMIT)" --signing-policy-version "$(setting SIGNER_POLICY_VERSION)")
    # Refuse incomplete local identity before any cloud mutation.
    count=0
    for f in attestation-signer.env transport.key public-identity.json; do
      if [ -e "$f" ] || [ -L "$f" ]; then
        [ -f "$f" ] && [ ! -L "$f" ] || fail 'Identity files must be regular.'
        count=$((count + 1))
      fi
    done
    [ "$count" = 0 ] || [ "$count" = 3 ] || fail 'Incomplete identity; restore it instead of generating another.'
    if [ "$count" = 0 ]; then
      for f in identity.json data active-bundle; do
        [ ! -e "$f" ] && [ ! -L "$f" ] || fail 'Existing runtime state without a complete identity; restore the original identity.'
      done
    fi
    kms_args=()
    if [ "$backend" = aws-kms ]; then
      if [ "$count" = 3 ]; then
        [ "$(setting ATTESTATION_SIGNER_BACKEND attestation-signer.env)" = aws_kms ] || fail 'Existing identity uses another backend.'
        [ "$(setting ATTESTATION_SIGNER_KMS_REGION attestation-signer.env)" = "$region" ] || fail 'Existing KMS region differs.'
        if [ "$create" = true ]; then key_id=$(setting ATTESTATION_SIGNER_KMS_KEY_ID attestation-signer.env); create=false; fi
      fi
      for record in .kms/created-key-id .kms/created-key-id.pending .kms/region .kms/create-pending .kms/public-key.json .kms/provider-error.log .kms/auth-error.log; do
        [ ! -L "$record" ] || fail 'KMS records must not be symlinks.'
        [ ! -e "$record" ] || [ -f "$record" ] || fail 'KMS records must be regular files.'
      done
      aws=(docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges
        --user "$(id -u):$(id -g)" --env-file "$root/aws.env" --env AWS_PAGER=
        --env AWS_CONFIG_FILE=/etc/signer-aws/config --env AWS_SHARED_CREDENTIALS_FILE=/etc/signer-aws/credentials
        --mount "type=bind,src=$root/aws,dst=/etc/signer-aws,readonly" "$aws_image" --no-cli-pager --region "$region")
      # Credentials must work before creating a pending cloud-operation record.
      if ! "${aws[@]}" sts get-caller-identity --query Account --output text > /dev/null 2> .kms/auth-error.log; then
        fail 'AWS authentication failed in the container. Configure aws.env or aws/config + aws/credentials, then retry. No KMS creation was attempted; details: .kms/auth-error.log.'
      fi
      if [ "$create" = true ]; then
        # Recover only the old tool's known pre-request credential failure.
        # Network/timeouts remain uncertain and still require manual reconciliation.
        if [ -f .kms/create-pending ] && [ ! -e .kms/created-key-id ] && \
            [ -f .kms/provider-error.log ] && grep -q '^Unable to locate credentials' .kms/provider-error.log; then
          rm -f .kms/create-pending .kms/created-key-id.pending .kms/region
        fi
        if [ -f .kms/created-key-id ] && [ ! -L .kms/created-key-id ]; then
          [ "$(cat .kms/region)" = "$region" ] || fail 'Recorded KMS creation used another region.'
          key_id=$(cat .kms/created-key-id)
        else
          [ ! -e .kms/create-pending ] && [ ! -L .kms/create-pending ] || fail 'Prior KMS creation has an uncertain outcome. Inspect AWS and resume with --kms-key-id; do not create another key blindly.'
          (set -C; printf '%s\n' "$region" > .kms/region; : > .kms/create-pending)
          if ! "${aws[@]}" kms create-key --key-spec ECC_SECG_P256K1 --key-usage SIGN_VERIFY \
              --description "DogeOS attestation signer $name" --query KeyMetadata.Arn --output text \
              > .kms/created-key-id.pending 2> .kms/provider-error.log; then
            fail 'KMS creation failed or its outcome is uncertain. Inspect the private .kms/provider-error.log; no automatic creation retry.'
          fi
          key_id=$(cat .kms/created-key-id.pending)
          [[ "$key_id" =~ ^arn:[a-z0-9-]+:kms:[a-z0-9-]+:[0-9]{12}:key/[a-zA-Z0-9-]+$ ]] || fail 'KMS returned no valid key ARN; inspect the creation record.'
          mv .kms/created-key-id.pending .kms/created-key-id
        fi
      fi
      [ ! -L .kms/public-key.json ] && [ ! -L .kms/provider-error.log ] || fail 'KMS records must not be symlinks.'
      if ! "${aws[@]}" kms get-public-key --key-id "$key_id" --output json > .kms/public-key.json 2> .kms/provider-error.log; then
        fail 'KMS public-key lookup failed. Check the private .kms/provider-error.log and container AWS credentials; no key was regenerated.'
      fi
      kms_args=(--kms-info /output/.kms/public-key.json --kms-region "$region")
    fi
    bash scripts/init-keys.sh --name "$name" --network "$network" --out "$root" "${pins[@]}" "${kms_args[@]}"
    mkdir -p data
    echo 'Public identity: ./public-identity.json and ./identity.json. Next: register the paired public keys in DogeOS Governance.'
    ;;
  identity)
    [ "$#" = 0 ] || fail 'identity takes no arguments.'
    [ -f public-identity.json ] && [ ! -L public-identity.json ] || fail 'Initialize first.'
    cat public-identity.json
    echo 'Upload format: ./identity.json (public only). Never upload the entire directory.'
    ;;
  import)
    [ "$#" = 2 ] || fail 'Usage: ./signer.sh import BUNDLE AUTHENTICATED_MANIFEST_SHA256'
    protect_outputs
    assert_stopped
    bundle=$(cd -- "$1" && pwd -P)
    case "$bundle" in *,*) fail 'Docker bind paths cannot contain commas.' ;; esac
    "${py[@]}" --network none --mount "type=bind,src=$bundle,dst=/bundle,readonly" --entrypoint python "$python_image" /workspace/scripts/runtime.py import "$2"
    ;;
  start)
    [ "$#" = 0 ] || fail 'start takes no arguments.'
    protect_outputs
    [ -L active-bundle ] && [ -f identity.json ] && [ -d data ] || fail 'Initialize and import the approved bundle first.'
    # Parse resolved Compose in a container; never print credential-bearing config.
    docker compose config --format json | "${py[@]}" -i --network none --entrypoint python "$python_image" /workspace/scripts/runtime.py prestart
    docker compose up -d --force-recreate attestation-signer
    echo 'Run ./signer.sh check after startup. Docker health alone does not prove TSO connectivity.'
    ;;
  check)
    [ "$#" = 0 ] || fail 'check takes no arguments.'
    container=$(container_id)
    "${py[@]}" --network "container:$container" --entrypoint python "$python_image" /workspace/scripts/runtime.py check
    ;;
  rotation)
    [ "$#" -ge 2 ] || fail 'Provide rotation inspect, approve or ready and the proposal; see --help.'
    op=$1; shift
    case "$op" in
      inspect) exec bash scripts/rotation.sh inspect "$@" ;;
      approve|ready)
        protect_outputs
        container=$(container_id)
        exec bash scripts/rotation.sh "$op" "$@" --config "$root/attestation-signer.toml" --identity "$root/identity.json" --container "$container"
        ;;
      *) fail 'Unknown rotation operation.' ;;
    esac
    ;;
  stop) [ "$#" = 0 ] || fail 'stop takes no arguments.'; docker compose stop attestation-signer ;;
  logs) [ "$#" = 0 ] || fail 'logs takes no arguments.'; docker compose logs --tail=100 attestation-signer ;;
  *) usage >&2; exit 1 ;;
esac
