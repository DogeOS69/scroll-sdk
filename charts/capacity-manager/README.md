# Capacity manager

Independent Core worker-capacity controller. It has no public Service/Ingress,
no cloud credentials and no Kubernetes API token. Requires a digest-pinned Core
capacity-manager image, prepared values, existing token Secrets, an existing
dstack project and prepared fleet intent and durable state. One replica only; Recreate updates.
By default the chart creates a dedicated, unannotated ServiceAccount with token
automount disabled. Set `serviceAccount.create: false` and `serviceAccount.name`
to reuse an existing unannotated account; the Pod still disables token automount.

`workerCredentialMaster` references the coordinator-only worker-credential
master. The manager reads it as
`--worker-credential-master-file` and mints each run's own credential. Never mount this Secret key on a worker.

`manager.workerReadinessFile` optionally asks the remote worker to write its
startup evidence. Verify that evidence against the current dstack run ID; a
Ready manager Pod does not establish GPU worker readiness.

`manager.workerEnv` (chart 0.1.4+) is a string-to-string map passed to remote
workers through repeated `--dstack-worker-env KEY=VALUE` arguments. The CLI
places public artifact URLs and SHA-256 digests here; `manager.workerCommand`
references them with quoted shell variables. These values are visible in the
Deployment arguments, so never use this map for credentials. Token, readiness,
NVIDIA capabilities, and Core ownership/identity variables are reserved.
Omitting the map remains compatible with existing self-contained commands.

See [operator instructions](../../examples/capacity-manager.md) and the
[spec fragment](../../examples/capacity-manager-spec.example.yaml).
See the [RTX3090 configuration example](../../examples/capacity-manager-devnet.md)
for an alternative GPU configuration.

Installing starts continuous reconciliation and can allocate paid resources.
Pausing/uninstalling does not by itself stop remote workers. Preserve the state
PVC and follow the drain procedure before deleting or changing the deployment.

## Optional primary-to-fallback fleet switching

Chart 0.1.5 adds `manager.dstack.fallbackFleet`, default empty. A nonempty name
passes `--dstack-fallback-fleet` to Core. Select an immutable manager image that
supports this argument. The initialization Job checks the selected binary
before installing the release.

Keep primary AWS selectors unchanged and prepare a separate Vast fleet in the
same dstack project, with a configured Vast backend. The fallback fleet must have
an explicit `max_price` within `pool.hourly_cost_usd_per_worker`, enough VRAM and
node capacity, and a GPU supported by the same worker image and startup command.
Core strips primary backend/region/GPU/price selectors from fallback runs and
uses the fallback fleet's settings. This is primary/backup switching, not weighted
multi-provider balancing. Backend configuration belongs to the controller. With initialization enabled,
the chart creates or verifies the declared empty primary and fallback fleets.

Primary no-capacity failures or provisioning timeouts switch new workers to the
fallback fleet for 30 minutes. The window is in memory; restart tries the primary
again and adopts existing workers. Other failures do not trigger fallback.

## Fleet initialization (0.1.6+)

Set `initialization.enabled: true` and provide reviewed dstack fleet definitions
in `initialization.fleets`, with the matching provider and `fleetAction`. The `pre-install,pre-upgrade` Job first probes DNS/TLS,
dstack project/backends, WP capacity API access and three existing Secret
references, then uses the pinned dstack 0.21.5 client to create missing fleets or
reuse equivalent ones. It requires zero initial/minimum nodes and a finite
maximum. A changed existing fleet is rejected, never force-applied. `fleetAction:
reuse` requires all fleets to exist. No Worker runs are submitted by the Job.

The Job uses the manager's NetworkPolicy labels and no Kubernetes API token or
RBAC. Secrets must already be synchronized, dstack and WP must be reachable, and
WP must allow the manager peer. A failed Job blocks installation/upgrade; the old
manager may continue running during an upgrade. Retry the Helm operation after
correcting the failure. Successful Jobs are deleted; failed Jobs have a one-hour
TTL. The public script ConfigMap is retained until the next hook creation.

The chart default is `initialization.enabled: false` for deployments with
operator-owned fleets. Enable it in the values passed to Helm to run these
checks and initialize empty fleets during installation or upgrade.
