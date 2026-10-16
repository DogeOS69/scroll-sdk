# Capacity manager

Independent Core worker-capacity controller. It has no public Service/Ingress,
no cloud credentials and no Kubernetes API token. Requires a digest-pinned Core
capacity-manager image, prepared values, existing token Secrets, an existing
dstack project/fleet and durable state. One replica only; Recreate updates.
By default the chart creates a dedicated, unannotated ServiceAccount with token
automount disabled. Set `serviceAccount.create: false` and `serviceAccount.name`
to reuse an existing unannotated account; the Pod still disables token automount.

`workerCredentialMaster` references the coordinator-only worker-credential
master (dogeos-core #1591). The manager reads it as
`--worker-credential-master-file` and mints each run's own credential
(dogeos-core #1598). Never mount this Secret key on a worker.

`manager.workerReadinessFile` optionally asks the remote worker to write its
startup evidence. Verify that evidence against the current dstack run ID; a
Ready manager Pod does not establish GPU worker readiness.

See [operator instructions](../../examples/capacity-manager.md) and the
[spec fragment](../../examples/capacity-manager-spec.example.yaml).
The [DevNet RTX3090 profile](../../examples/capacity-manager-devnet.md) records
the tested full-mode deployment and its explicit raw-manifest-to-Helm handoff.

Installing starts continuous reconciliation and can allocate paid resources.
Pausing/uninstalling does not by itself stop remote workers. Preserve the state
PVC and follow the drain procedure before deleting or changing the deployment.
