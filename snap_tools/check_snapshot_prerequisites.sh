#!/usr/bin/env bash
set -Eeuo pipefail

trap 'echo "[ERROR] Command failed: line ${LINENO}, command: ${BASH_COMMAND}" >&2' ERR

if ! command -v kubectl >/dev/null 2>&1; then
    echo "[ERROR] kubectl not found. Please install it and configure kubeconfig first." >&2
    exit 127
fi

echo "--- Starting EKS snapshot prerequisite checks ---"

failed_checks=0

# 1. Check Snapshot CRDs (required: later steps fail without CRDs)
echo "[1/4] Checking Snapshot CRDs..."
crd_output=$(kubectl get crd -o name)
crd_count=$(printf '%s\n' "$crd_output" | awk '/snapshot.storage.k8s.io/ {count++} END {print count+0}')

if (( crd_count >= 3 )); then
    echo "  - OK: Found ${crd_count} snapshot-related CRDs."
else
    echo "  - ERROR: Missing Snapshot CRDs (found ${crd_count}, need at least 3)."
    ((failed_checks += 1))
fi

# 2. Check Snapshot Controller
echo "[2/4] Checking Snapshot Controller..."
controller_pods=$(kubectl get pods -n kube-system -o name)
controller_matches=$(printf '%s\n' "$controller_pods" | grep snapshot-controller || true)

if [[ -n "$controller_matches" ]]; then
    total_count=$(printf '%s\n' "$controller_matches" | wc -l | tr -d ' ')
    running_count=$(kubectl get pods -n kube-system --no-headers | awk '/snapshot-controller/ && $3 == "Running" {count++} END {print count+0}')

    if (( running_count == total_count )); then
        echo "  - OK: Found ${total_count} Snapshot Controller pod(s), all Running."
        printf '%s\n' "$controller_matches" | sed 's/^/    /'
    else
        echo "  - ERROR: Found ${total_count} pod(s), but only ${running_count} are Running."
        printf '%s\n' "$controller_matches" | sed 's/^/    /'
        ((failed_checks += 1))
    fi
else
    echo "  - ERROR: Snapshot Controller not found."
    ((failed_checks += 1))
fi

# 3. Check EBS CSI Driver
echo "[3/4] Checking EBS CSI Driver..."
if kubectl get csidriver ebs.csi.aws.com >/dev/null; then
    echo "  - OK: EBS CSI Driver is installed."
else
    echo "  - ERROR: EBS CSI Driver is not installed."
    ((failed_checks += 1))
fi

# 4. Check VolumeSnapshotClass
echo "[4/4] Checking VolumeSnapshotClass..."
if (( crd_count > 0 )); then
    classes=$(kubectl get volumesnapshotclass \
        -o custom-columns=NAME:.metadata.name,DRIVER:.driver,DELETIONPOLICY:.deletionPolicy \
        --no-headers)

    if [[ -n "$classes" ]]; then
        echo "  - OK: The following VolumeSnapshotClass resources are defined:"
        printf '%s\n' "$classes" | sed 's/^/    /'

        ebs_class=$(printf '%s\n' "$classes" | grep "ebs.csi.aws.com" || true)
        if [[ -z "$ebs_class" ]]; then
            echo "  - ERROR: No VolumeSnapshotClass found for driver ebs.csi.aws.com."
            ((failed_checks += 1))
        fi
    else
        echo "  - ERROR: CRDs exist, but no VolumeSnapshotClass instances are defined."
        ((failed_checks += 1))
    fi
else
    echo "  - SKIP: Cannot check VolumeSnapshotClass because CRDs are missing."
fi

if (( failed_checks > 0 )); then
    echo "--- Check complete: ${failed_checks} check(s) failed ---"
    exit 1
fi

echo "--- Check complete: all checks passed ---"
