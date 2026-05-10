## Recommended Script Usage (After High-Priority Fixes)
```bash
# 1) Install prerequisites (pinned snapshotter version + context guard)
./install_snapshot_prerequisites.sh \
  --context your-eks-context \
  --snapshotter-version v8.2.0

# 2) Generate snapshot YAML only (default dry-run, no apply)
./generate_volume_snapshots.sh \
  --context your-eks-context \
  --namespace default

# 3) Explicitly apply after reviewing YAML
./generate_volume_snapshots.sh \
  --context your-eks-context \
  --namespace default \
  --apply
```

> Security policy: context guard is enabled by default. If neither `--context` nor `--allow-contexts` is provided, the scripts will refuse to run.

## List all existing snapshots
aws ec2 describe-snapshots --owner-ids self \
  --query 'Snapshots[*].[SnapshotId,VolumeSize,StartTime,Description]' \
  --output table

kubectl get volumesnapshot

```
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: l2-sequencer-data-restored
  namespace: default
spec:
  storageClassName: gp3        # Must match the original PVC; verify with: kubectl get pvc l2-sequencer-0-data -n default -o jsonpath='{.spec.storageClassName}'
  dataSource:
    name: mysql-data-snap-20260422 # Snapshot name from volume_snapshot_example.yaml
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi

```


# coldsnap
```
cargo install coldsnap

aws ec2 describe-snapshots --snapshot-ids snap-0b993410665085a61

# Get all VolumeSnapshotContent resources
kubectl get volumesnapshotcontent

NAME                                               READYTOUSE   RESTORESIZE   DELETIONPOLICY   DRIVER            VOLUMESNAPSHOTCLASS   VOLUMESNAPSHOT             VOLUMESNAPSHOTNAMESPACE   AGE
snapcontent-2263bd85-868c-4cec-b944-a8b048ebd5c1   true         10737418240   Retain           ebs.csi.aws.com   ebs-csi-snapclass     mysql-data-snap-20260422   default                   8h
# Get snapshot ID
kubectl get volumesnapshotcontent snapcontent-2263bd85-868c-4cec-b944-a8b048ebd5c1 \
  -o jsonpath='{.status.snapshotHandle}'
snap-0b993410665085a61

# Download (10GB usually takes a few to tens of minutes, depending on bandwidth)
coldsnap download snap-0b993410665085a61 ./l2geth_snap-0b993410665085a61.img

```
