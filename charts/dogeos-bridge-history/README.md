# dogeos-bridge-history

The DogeOS bridge history service: the read API at `/api/history/v1` behind the Portal's Activity panel. It derives everything from public chain data into one SQLite file, so deleting a replica's volume and restarting rebuilds it.

## Shape

- A StatefulSet, one replica by default, with `podManagementPolicy: Parallel`. Each replica gets its own volume from `volumeClaimTemplates` (10 GiB, at `/data`), rebuilds on its own, and shares nothing writable with another replica.
- `terminationGracePeriodSeconds: 100`, above the service's 90 s default shutdown timeout.
- Probes: liveness and startup on `/api/history/v1/live`, and readiness on `/api/history/v1/health`. Readiness is 503 until the initial sync or a rebuild finishes, which can take hours. It only gates traffic and never restarts the pod.
- Ingress: `/api/history/v1` on the Portal's host, so the Portal reaches it same-origin. The service serves that prefix itself, so there's no rewrite.
- The controller is fixed by `values.schema.json`: a StatefulSet with `RollingUpdate` and `Parallel`, and any number of replicas.

## Configuration

- `config` is rendered to `/app/conf/config.toml`. The `l2` and `ethereum` tables are rendered only when they're set.
- Every key can be overridden with a `DOGEOS_BRIDGE_HISTORY_<KEY>` environment variable, with nested keys joined by `__`. The Dogecoin RPC URL and credentials come from the `dogeos-bridge-history-secret-env` secret (see `externalSecrets` in `values/production.yaml`), as do the later L2 and Ethereum RPC URLs.
- The L2 `genesis.json` and the network's `protocol_context.json` come from the shared `genesis-config` and `protocol-context-config` ConfigMaps that `scroll-common` owns. They're mounted as single files with `subPath`, declared in production values as for the other services (see `docs/production-values.md`). A change to either needs a rollout restart.

## Ingress

Production routes `/api/history/v1` on the Portal's host through the Portal's ALB IngressGroup (`examples/shared-alb.md`). Its `group.order` of 10 puts the rule ahead of the Portal's `/` catch-all. The Portal's own Ingress must be in the same group, or the two Ingresses would get separate ALBs for one host.

## Image

`image.tag` is a placeholder until the service image is published.
