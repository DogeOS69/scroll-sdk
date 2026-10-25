# Frontend deployment and live Bridge address

Select a `dogeos69/scroll-sdk-frontends` image supporting dynamic deposit
destinations, runtime configuration and strict Dogecoin network validation.
The frontends chart hashes `scrollConfig` into the Pod template, so a Helm upgrade
that changes runtime configuration recreates Pods and regenerates `runtime-env.js`.

The portal discovers the current deposit address through L1 Interface replay.
It no longer consumes `REACT_APP_DOGE_BRIDGE_ADDRESS`. Withdrawals still use
`REACT_APP_MOAT_ADDRESS`, populated from the deployed contracts.

## Generated configuration

Keep domain, network, wallet connection and public URL intent in the DeploymentSpec.
No new manually supplied protocol hashes or rotating Bridge address are needed.
The normal preparation flow generates these values:

| Location | Field | Source |
| --- | --- | --- |
| `values/frontends-config.yaml`, `scrollConfig` | `REACT_APP_DEPOSIT_API_PATH` | `/api/deposit`, the image's same-origin proxy path |
| Same | `REACT_APP_DOGE_NETWORK` | `dogecoin.network`: exactly `mainnet`, `testnet` or `regtest` |
| Same | `REACT_APP_DOGEOS_PROTOCOL_ID` | Derived from local `.data/protocol_context.json`; checked against its protocol ID sidecar when present |
| Same | `REACT_APP_DOGEOS_GENESIS_STATE_HASH` | Prepared Bridge proof-materials receipt, cross-checked with the checksum-validated native Bridge manifest |
| `values/frontends-production.yaml`, `env` | `L1_INTERFACE_UPSTREAM` | `l1-interface:9090`, the internal health/replay HTTP listener |

Configure `REACT_APP_DOGE_NETWORK` explicitly. Missing, empty, `livenet`, uppercase
or whitespace-padded values fail container startup and browser initialization.
The value selects the **Dogecoin L1 network**, including withdrawal address
validation; `REACT_APP_CHAIN_ID_L2` separately identifies DogeOS L2. For a regtest
deployment, set `REACT_APP_DOGE_NETWORK = "regtest"` in `scrollConfig`. The production command
loads this ConfigMap into the container environment before invoking the image
entrypoint. Do not rely on a build-time network or an implicit testnet fallback.

The genesis state hash is the **DogeOS protocol genesis state hash**, not the EVM
genesis block hash or state root. The CLI verifies local artifact checksums and
network bindings. It never obtains the expected identity by trusting the API it
is about to expose. A selected proof-materials receipt must be present and valid.

Before Bridge proof preparation completes, `setup generate-from-spec` writes empty
identity values and reports that deposits remain disabled. `setup prep-charts`
fills both values once the artifacts are available; real-proof preparation refuses
to finalize frontend configuration without them. These steps are already part of
the [deployment sequence](bridge-operator-deployment.md).

`scrollConfig` is the single frontend ConfigMap payload. The CLI converts older
generated `configMaps.frontend-config` payloads to this form and removes the old
static Bridge address. Other operator frontend fields remain available.

The upstream belongs in the container environment, never browser configuration.
For a custom internal proxy, override `env.L1_INTERFACE_UPSTREAM` in the production
values with `host:port`. Do not use the Ethereum RPC URL, credentials or a path.
The public proxy exposes only GET/HEAD `/api/deposit/config`. The bundled Node
service validates internal readiness and replay responses and returns a minimal
deposit configuration from its memory cache; internal replay and admin routes
are not exposed.

## Install and verify

After preparation, use the normal frontend target from the deployment directory:

```sh
make install-frontends KUBE_CONTEXT="$KUBE_CONTEXT" NAMESPACE="$NAMESPACE"
```

The same target upgrades an existing release. Chart `0.1.5-dogeos` and later
automatically roll out Pods when `scrollConfig` changes through Helm. For an
older chart, or a ConfigMap edited directly outside Helm, restart the deployment:

```sh
kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" rollout restart deployment/frontends
```

Check the portal's `/api/deposit/config` response. Its protocol ID and genesis
state hash must match the generated values. The bundled service checks full
replay validation, readiness, network and current Bridge key. The older public
`/api/deposit/ready` and `/api/deposit/state` routes return 404.
The same-origin proxy and `/runtime-env.js` must return `Cache-Control: no-store`;
configure any ingress/CDN to preserve it and bypass caching, and purge old entries
when switching to this image.

The backend must require full replay validation and suppress these responses when
discovery loses chain synchronization, observations become stale or reorg recovery
is active. A fresh health response or matching discovered/validated WF alone does
not prove live-chain catch-up or a particular confirmation depth. See the frontend
[backend readiness contract](https://github.com/DogeOS69/scroll-sdk-frontends/blob/develop/docs/deposit-destination.md#backend-readiness-synchronization-and-finality-contract)
before enabling deposits.

The service refreshes every 30 seconds and the browser polls every 15 seconds.
Browser requests, including confirmation clicks, do not force upstream refreshes.
Failed refreshes clear the cache; expired results return 503 without a stale
fallback. Account for these observation intervals when planning a rotation.

After a Bridge rotation, the protocol identity stays fixed and the frontend reads
the new current key/address. No static address edit or restart is required for the
rotation itself. Verify the newly displayed address against validated replay;
previously copied addresses and transactions in external wallets still require
operator/user handling.
