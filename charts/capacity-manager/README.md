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

Keep the primary selectors unchanged and prepare a separate fallback fleet in the
same dstack project, with a configured backend for its provider. Chart 0.1.9
accepts `aws` as well as `vastai` for `initialization.fallbackProvider`, so a
Vast primary can fall back to on-demand AWS. The fallback fleet must have
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
maximum. With `fleetAction: create` or `reuse`, a changed existing fleet is
rejected, never force-applied. `fleetAction: reuse` requires all fleets to exist.
When a selected provider's backend is missing, the failed probe names it
(`missingBackends`): dstack creates backends only at startup and only logs a
failure, so check the dstack-controller log and restart the controller after
fixing the credentials.
No Worker runs are submitted by the Job.

Chart 0.1.9 adds `fleetAction: update`: missing fleets are created as with
`create`, and an existing fleet that differs is updated in place. Only the fields
dstack 0.21.5 updates in place may differ: `nodes`, `resources`, `backends`,
`regions`, `instance_types`, `spot_policy` and `max_price`. Any other difference,
for example `idle_duration`, fails the Job before any fleet changes; declare a
fleet with a new name instead. The update is planned with dstack and applied
against the fleet just read, without force, so a concurrent change fails the Job.
Fleets are updated one after another: if one update fails, the fleets updated
before it keep their new configuration; rerunning the upgrade skips them and
continues.
dstack then terminates idle or provisioning instances that no longer match the
fleet, and idle instances above a lowered `nodes.max`; busy instances keep
running. A Helm rollback does not run the Job, so it does not revert fleets: run
an upgrade with the previous values instead.

The Job uses the manager's NetworkPolicy labels and no Kubernetes API token or
RBAC. Secrets must already be synchronized, dstack and WP must be reachable, and
WP must allow the manager peer. A failed Job blocks installation/upgrade; the old
manager may continue running during an upgrade. Retry the Helm operation after
correcting the failure. Successful Jobs are deleted; failed Jobs have a one-hour
TTL. The public script ConfigMap is retained until the next hook creation.

The chart default is `initialization.enabled: false` for deployments with
operator-owned fleets. Enable it in the values passed to Helm to run these
checks and initialize empty fleets during installation or upgrade.

## Private CA for an in-cluster dstack controller (0.1.8+)

`manager.dstack.caBundle`, default empty, holds PEM CA certificates that replace
the public roots for `manager.dstack.serverUrl`. Use it with a dstack-controller
release that sets `tls.enabled`: copy `ca.crt` from that release's
`<fullname>-tls` Secret and set `serverUrl` to
`https://<fullname>.<namespace>.svc:8443`. The bundle is public data rendered into
a ConfigMap; the chart rejects a private key, other or incomplete PEM blocks, a
non-PEM value and an `http` URL.

The manager receives `--dstack-ca-file`, which needs a Core image with
dogeos-core #1786. With initialization enabled, the Job first checks that the
selected binary accepts the flag, and its dstack client trusts the same bundle
through `REQUESTS_CA_BUNDLE`. Core reads the file once at startup; the chart
restarts the manager when the bundle changes. A bundle may hold several CAs, but
the dstack-controller chart cannot stage a new CA before it serves it. When its CA
is replaced and the server certificate reissued (see that chart's README), update
`caBundle` right after, in a short maintenance window.

The manager keys its worker state by server URL. Moving an existing fleet from a
public hostname to the Service URL, or back, is a migration: drain the workers and
finish cleanup through the old URL first, then change `serverUrl` and `caBundle`
together.
