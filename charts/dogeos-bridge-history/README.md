# dogeos-bridge-history

The DogeOS bridge history service: the read API at `/api/history/v1` behind the Portal's Activity panel. It derives everything from public chain data into one SQLite file, so deleting a replica's volume and restarting rebuilds it.

## Shape

- A StatefulSet, one replica by default, with `podManagementPolicy: Parallel`. Each replica gets its own volume from `volumeClaimTemplates` (10 GiB, at `/data`), rebuilds on its own, and shares nothing writable with another replica.
- `enableServiceLinks: false`. Kubernetes would otherwise inject `DOGEOS_BRIDGE_HISTORY_*` variables for this Service, which match the service's own config prefix, so the service would reject them and fail to start.
- `terminationGracePeriodSeconds: 100`, above the service's 90 s default shutdown timeout.
- Probes: liveness and startup on `/api/history/v1/live`, and readiness on `/api/history/v1/health`. Readiness is 503 until the initial sync or a rebuild finishes, which can take hours. It only gates traffic and never restarts the pod. During a rebuild with one replica, the API path therefore answers with the load balancer's own 503, which the Portal shows as "catching up".
- Ingress: `/api/history/v1` on the Portal's host, so the Portal reaches it same-origin. The service serves that prefix itself, so there's no rewrite.
- The controller is fixed by `values.schema.json`: a StatefulSet with `RollingUpdate` and `Parallel`, and any number of replicas.

## Configuration

- `config` is rendered to `/app/conf/config.toml`. The `l2` and `ethereum` tables are rendered only when they're set.
- Every key can be overridden with a `DOGEOS_BRIDGE_HISTORY_<KEY>` environment variable, with nested keys joined by `__`. The Dogecoin RPC URL and credentials come from the `dogeos-bridge-history-secret-env` secret (see `externalSecrets` in `values/production.yaml`), as do the later L2 and Ethereum RPC URLs.
- The L2 `genesis.json` and the network's `protocol_context.json` come from the shared `genesis-config` and `protocol-context-config` ConfigMaps that `scroll-common` owns. They're mounted as single files with `subPath`, declared in production values as for the other services (see `docs/production-values.md`). A change to either needs a rollout restart.

## Ingress

Production routes `/api/history/v1` on the Portal's host through the Portal's ALB IngressGroup (`examples/shared-alb.md`). Its `group.order` of 10 puts the rule ahead of the Portal's `/` catch-all. The Portal's own Ingress must be in the same group, or the two Ingresses would get separate ALBs for one host.

## Portal migration

The production Portal example still pins an image that reads `REACT_APP_BRIDGE_API_URI`. Keep that legacy endpoint configured alongside `REACT_APP_HISTORY_API_URI` until the Activity-enabled Portal image is deployed. The new image reads the history key; the old image continues using the legacy key.

The status-page generator also infers legacy `/txs` checks from `REACT_APP_BRIDGE_API_URI`. Before retiring that endpoint, migrate or disable those checks using the applicable monitoring mode. Remove the legacy key only after both consumers have migrated.

## Rebuilding a replica

The index is rebuildable from public chain data. To rebuild replica `<n>` from an empty volume:

1. `kubectl scale statefulset dogeos-bridge-history --replicas=<n>`. This stops replica `<n>` and every replica above it; replicas below `<n>` keep serving.
2. `kubectl delete pvc data-dogeos-bridge-history-<n>`
3. Scale back to the full count. Replica `<n>` starts on a new, empty volume, and its `/health` is 503 until the rebuild has caught up. Any higher replicas restart on their existing volumes.

`helm uninstall` keeps the `data-dogeos-bridge-history-<n>` claims, as Kubernetes does for every StatefulSet claim. Delete them yourself if you don't want the index back on reinstall.

With `controller.replicas` above 1, enable the commented ALB stickiness annotation in production values. Each replica has its own index and can be a tick ahead of another.

## Image

`image.tag` is a placeholder until the service image is published.
