#!/usr/bin/env bash
set -Eeuo pipefail

trap 'echo "[ERROR] Command failed: line ${LINENO}, command: ${BASH_COMMAND}" >&2' ERR

usage() {
    cat <<'EOF'
Usage: ./install_snapshot_prerequisites.sh [options]

Options:
  --context <name>               Allow execution only on this kube context
  --allow-contexts <a,b,c>       Context allowlist
  --snapshotter-version <tag>    external-snapshotter version (default: v8.2.0)
  --snapshot-class-name <name>   VolumeSnapshotClass name (default: ebs-csi-snapclass)
  --set-default-class            Mark VolumeSnapshotClass as default
  --unset-default-class          Do not mark as default (default behavior)
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

require_context_guard="${REQUIRE_CONTEXT_GUARD:-1}"
target_context="${TARGET_CONTEXT:-}"
allowed_contexts="${ALLOWED_CONTEXTS:-}"
snapshotter_version="${SNAPSHOTTER_VERSION:-v8.2.0}"
snapshot_class_name="${SNAPSHOT_CLASS_NAME:-ebs-csi-snapclass}"
set_default_class="${SET_AS_DEFAULT_CLASS:-false}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --context)
            target_context="$2"
            shift 2
            ;;
        --allow-contexts)
            allowed_contexts="$2"
            shift 2
            ;;
        --snapshotter-version)
            snapshotter_version="$2"
            shift 2
            ;;
        --snapshot-class-name)
            snapshot_class_name="$2"
            shift 2
            ;;
        --set-default-class)
            set_default_class="true"
            shift
            ;;
        --unset-default-class)
            set_default_class="false"
            shift
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

if [[ "$set_default_class" != "true" && "$set_default_class" != "false" ]]; then
    echo "[ERROR] SET_AS_DEFAULT_CLASS only supports true/false, current: ${set_default_class}" >&2
    exit 1
fi

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

apply_manifest() {
    local manifest_url="$1"
    echo "[APPLY] ${manifest_url}"
    kubectl apply -f "$manifest_url"
}

assert_context_guard

base_url="https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snapshotter_version}"

echo "[1/3] Deploying Snapshot CRDs..."
apply_manifest "${base_url}/client/config/crd/snapshot.storage.k8s.io_volumesnapshotclasses.yaml"
apply_manifest "${base_url}/client/config/crd/snapshot.storage.k8s.io_volumesnapshotcontents.yaml"
apply_manifest "${base_url}/client/config/crd/snapshot.storage.k8s.io_volumesnapshots.yaml"

echo "[2/3] Deploying Snapshot Controller..."
apply_manifest "${base_url}/deploy/kubernetes/snapshot-controller/rbac-snapshot-controller.yaml"
apply_manifest "${base_url}/deploy/kubernetes/snapshot-controller/setup-snapshot-controller.yaml"

default_annotation_block=""
if [[ "$set_default_class" == "true" ]]; then
    default_annotation_block=$'  annotations:\n    snapshot.storage.kubernetes.io/is-default-class: "true"'
fi

echo "[3/3] Creating VolumeSnapshotClass..."
kubectl apply -f - <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: ${snapshot_class_name}
${default_annotation_block}
driver: ebs.csi.aws.com
deletionPolicy: Retain
EOF

echo "Installation complete. snapshotter=${snapshotter_version}, snapshotClass=${snapshot_class_name}, defaultClass=${set_default_class}"
