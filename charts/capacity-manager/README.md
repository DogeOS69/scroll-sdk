# Capacity manager

Independent Core worker-capacity controller. It has no public Service/Ingress,
no cloud credentials and no Kubernetes API token. Requires a digest-pinned Core
capacity-manager image, prepared values, existing token Secrets, an existing
dstack project/fleet and durable state. One replica only; Recreate updates.

See [operator instructions](../../examples/capacity-manager.md) and the
[spec fragment](../../examples/capacity-manager-spec.example.yaml).

Installing starts continuous reconciliation and can allocate paid resources.
Pausing/uninstalling does not by itself stop remote workers. Preserve the state
PVC and follow the drain procedure before deleting or changing the deployment.
