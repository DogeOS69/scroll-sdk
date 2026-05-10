#!/usr/bin/env bash
set -Eeuo pipefail

trap 'echo "[ERROR] Command failed: line ${LINENO}, command: ${BASH_COMMAND}" >&2' ERR

usage() {
  cat <<'EOF'
Usage: ./generate_volume_snapshots.sh [options]

Options:
  --namespace <ns>               Namespace (default: default)
  --date <YYYYMMDD>              Snapshot date (default: today)
  --out <file>                   Output YAML file
  --snapshot-class <name>        VolumeSnapshotClass name (default: ebs-csi-snapclass)
  --install-prereqs              Install prerequisites before generation
  --skip-check                   Skip prerequisite checks
  --apply                        Apply the generated manifests
  --context <name>               Allow execution only on this kube context
  --allow-contexts <a,b,c>       Context allowlist
  -h, --help                     Show help

Env:
  REQUIRE_CONTEXT_GUARD=1|0      Enable context guard (default: 1)
  TARGET_CONTEXT=<name>          Same as --context
  ALLOWED_CONTEXTS=<a,b,c>       Same as --allow-contexts
EOF
}

if ! command -v kubectl >/dev/null 2>&1; then
  echo "[ERROR] kubectl not found. Please install it and configure kubeconfig first." >&2
  exit 127
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_context_guard="${REQUIRE_CONTEXT_GUARD:-1}"
target_context="${TARGET_CONTEXT:-}"
allowed_contexts="${ALLOWED_CONTEXTS:-}"

namespace="${NS:-default}"
date_value="${DATE:-$(date +%Y%m%d)}"
out_file="${OUT:-}"
snapshot_class_name="${SNAPSHOT_CLASS_NAME:-ebs-csi-snapclass}"

install_prereqs="false"
run_check="true"
apply_changes="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      namespace="$2"
      shift 2
      ;;
    --date)
      date_value="$2"
      shift 2
      ;;
    --out)
      out_file="$2"
      shift 2
      ;;
    --snapshot-class)
      snapshot_class_name="$2"
      shift 2
      ;;
    --install-prereqs)
      install_prereqs="true"
      shift
      ;;
    --skip-check)
      run_check="false"
      shift
      ;;
    --apply)
      apply_changes="true"
      shift
      ;;
    --context)
      target_context="$2"
      shift 2
      ;;
    --allow-contexts)
      allowed_contexts="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

out_file="${out_file:-volume_snapshots_${date_value}.yaml}"

assert_context_guard() {
  local current_context
  local matched="false"

  current_context="$(kubectl config current-context)"
  if [[ -z "$current_context" ]]; then
    echo "[ERROR] Failed to get current kube context." >&2
    exit 1
  fi

  if [[ "$require_context_guard" != "0" ]]; then
    if [[ -z "$target_context" && -z "$allowed_contexts" ]]; then
      echo "[ERROR] To prevent accidental operations, set --context or --allow-contexts; set REQUIRE_CONTEXT_GUARD=0 to bypass." >&2
      exit 1
    fi

    if [[ -n "$target_context" && "$current_context" != "$target_context" ]]; then
      echo "[ERROR] Current context=${current_context} does not match target context=${target_context}." >&2
      exit 1
    fi

    if [[ -n "$allowed_contexts" ]]; then
      IFS=',' read -r -a allowed_list <<< "$allowed_contexts"
      for allowed in "${allowed_list[@]}"; do
        allowed="$(echo "$allowed" | xargs)"
        if [[ "$allowed" == "$current_context" ]]; then
          matched="true"
          break
        fi
      done

      if [[ "$matched" != "true" ]]; then
        echo "[ERROR] Current context=${current_context} is not in allowlist [${allowed_contexts}]." >&2
        exit 1
      fi
    fi
  fi

  echo "[INFO] Current kube context: ${current_context}"
}

assert_context_guard

if [[ "$install_prereqs" == "true" ]]; then
  echo "[1/5] Installing snapshot prerequisites..."
  install_args=()
  [[ -n "$target_context" ]] && install_args+=(--context "$target_context")
  [[ -n "$allowed_contexts" ]] && install_args+=(--allow-contexts "$allowed_contexts")
  "${script_dir}/install_snapshot_prerequisites.sh" "${install_args[@]}"
else
  echo "[1/5] Skipping prerequisite installation (--install-prereqs not set)"
fi

if [[ "$run_check" == "true" ]]; then
  echo "[2/5] Checking snapshot prerequisites..."
  "${script_dir}/check_snapshot_prerequisites.sh"
else
  echo "[2/5] Skipping prerequisite checks (--skip-check set)"
fi

echo "[3/5] Loading target PVC list..."

PVCS=(
  data-l2-rpc-0
  fee-oracle-data
  l1-interface-data
  l2-sequencer-0-data
  session-cache-0-cubesigner-signer-0-0
  session-cache-1-cubesigner-signer-1-0
  session-cache-2-cubesigner-signer-2-0
  withdrawal-processor-data
)

echo "[4/5] Validating PVC existence..."
for pvc in "${PVCS[@]}"; do
  kubectl get pvc "$pvc" -n "$namespace" >/dev/null
done

echo "[5/5] Generating VolumeSnapshot manifests..."
> "$out_file"
for pvc in "${PVCS[@]}"; do
  cat >> "$out_file" <<EOF
---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: ${pvc}-snap-${date_value}
  namespace: ${namespace}
spec:
  volumeSnapshotClassName: ${snapshot_class_name}
  source:
    persistentVolumeClaimName: ${pvc}
EOF
done

echo "Generated ${out_file}"

if [[ "$apply_changes" == "true" ]]; then
  echo "[APPLY] kubectl apply -f ${out_file}"
  kubectl apply -f "$out_file"
  kubectl get volumesnapshot -n "$namespace"
else
  echo "[DRY-RUN] Manifests generated only; not applied. Run the command below to apply:"
  echo "kubectl apply -f ${out_file}"
fi
