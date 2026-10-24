# Runtime public-key allowlist for Reth bootnodes

One `reth-peer-allowlist` Helm release owns the public-key policy. Each
participating `l2-reth` release runs a sidecar that reads that ConfigMap and
updates its own Reth instance through a shared Unix-domain IPC socket. The
sidecars do not call the Kubernetes API or need additional RBAC. All releases
must be in the same namespace.

The feature is disabled by default.

## Initial deployment

Copy these files into the operator deployment directory:

- [values/reth-peer-allowlist.yaml](values/reth-peer-allowlist.yaml): the runtime
  policy. It can start with `peers: []`; members need not be known at deployment.
- [values/l2-reth-bootnode-allowlist.yaml](values/l2-reth-bootnode-allowlist.yaml):
  the stable overlay enabling each bootnode's sidecar. Keep it separate from
  CLI-generated values and apply it last on every subsequent bootnode upgrade.

Create the shared policy before enabling bootnodes. From this SDK checkout:

```sh
helm upgrade --install reth-peer-allowlist ./charts/reth-peer-allowlist \
  --namespace "$NAMESPACE" --values /path/to/deployment/values/reth-peer-allowlist.yaml
```

For each bootnode, install/upgrade `charts/l2-reth` with its own usual values
and the allowlist overlay last:

```sh
helm upgrade --install l2-reth-bootnode-0 ./charts/l2-reth \
  --namespace "$NAMESPACE" \
  --values /path/to/deployment/values/l2-reth-bootnode-production-0.yaml \
  --values /path/to/deployment/values/l2-reth-bootnode-allowlist.yaml
```

Repeat for `l2-reth-bootnode-1`, etc., referencing the same ConfigMap. The first
upgrade changes the Pod template and restarts the Pod. Subsequent policy-only
updates do not. Existing external P2P Services/NLB bindings stay configured in
the per-release values.

The example Makefile also provides `upgrade-reth-peer-allowlist` and accepts
`L2_RETH_BOOTNODE_ALLOWLIST_VALUES=values/l2-reth-bootnode-allowlist.yaml` for
`install-l2-reth-bootnode`. For unpublished charts, set `L2_RETH_CHART` and
`RETH_PEER_ALLOWLIST_CHART` to their local chart paths. The shared release is
deliberately not part of `install-all` or the general deletion targets, so
routine application installs cannot overwrite the runtime policy.

## Add and revoke members during operation

Edit only `peers` in the operator-owned policy values. Use a YAML list of quoted
128-hex-digit P2P public keys. Public-key-only `enode://` and `0x` prefixes are
also accepted; addresses and ports are not. Duplicate IDs are normalized.
Include internal nodes that must connect as well as external partners, except
for sequencers already configured in `reth.trustedPeers`.

Upgrade only the shared release, using the same command as its initial install,
or `make upgrade-reth-peer-allowlist`. No CLI regeneration or bootnode Helm
upgrade is needed. An empty array revokes the runtime members but preserves
the fixed peers in `reth.trustedPeers`. An ID in both lists remains authorized
when removed from the runtime list; removing a fixed peer requires changing
the bootnode's startup configuration.

The ConfigMap is mounted as a directory, without `subPath`; Kubernetes projects
updates asynchronously. After projection, each sidecar reconciles at
`reth.peerAllowlist.intervalSeconds` (default 5 seconds). This is eventual
convergence, not an atomic cutover across bootnodes. Network or IPC failures
extend that delay. `helm --wait` on the policy release cannot verify convergence.

The sidecar validates the entire file before applying it. An invalid or missing
policy retains the last valid policy and makes the sidecar unready; it is not
interpreted as an empty list. With no previously valid policy, it performs no
RPC writes. Reth starts with `--trusted-only` and its configured sequencer peers.

For removed IDs, the sidecar calls `admin_removeTrustedPeer` before
`admin_removePeer` to revoke trust and disconnect established sessions. It
retries removals and replays the desired list every cycle. A small write-ahead
journal in an `emptyDir` retains all managed IDs, including revocation
tombstones, across sidecar container restarts. The journal is persisted before
mutating RPC calls, so a lost response cannot lose track of an added ID.

Reth can restart between polls and still recover without a policy edit. A new
Pod resets both the journal and Reth's dynamic peer state; `--no-persist-peers`
prevents loading old peer permissions/addresses from the datadir. Do not modify
trusted peers through a second controller or manual admin calls: IPC has no API
to enumerate all offline trusted IDs, and this sidecar must own their lifecycle.

## Connection policy and IPC

Enabled bootnodes run with discovery disabled, `--trusted-only` and
`--no-persist-peers`. The chart preserves `reth.trustedPeers` and
`reth.rpc.maxOutboundPeers`; it does not force the outbound limit to zero.
Keep sequencer enodes in `reth.trustedPeers` so Reth can connect and reconnect
to them. When the sidecar is enabled, this field accepts comma-separated
address-bearing enode URLs, including DNS hosts. Their IDs are automatically
passed to the sidecar as protected peers, separate from the runtime policy.
The sidecar never removes or disconnects those peers, even with an empty runtime
list. The effective admission list is the union of fixed peers and runtime IDs.

Public-key-only runtime entries provide no address to dial at addition time.
However, discovery disabled means no automatic peer discovery, not a strict
ban on all other outbound attempts. Once Reth knows a trusted peer's address,
it may consider that peer for outbound connections. This implementation preserves
sequencer connectivity and disables discovery; it does not claim strict
static-only outbound enforcement. Other roles retain their existing configuration.
A public key is authenticated during the P2P handshake; this does not prevent
arbitrary hosts from opening a TCP socket.

The socket is `/run/reth-allowlist/reth.ipc` in a shared `emptyDir`. In this mode
it overrides `reth.ipcPath`. The sidecar uses the same configured UID as Reth
(default 0 for the supported rollup-node image) with IPC permissions unchanged
(default `0600`). If using a non-root image, explicitly set the main
`securityContext.runAsUser` or `podSecurityContext.runAsUser`, and configure
`podSecurityContext.fsGroup` for writable shared volumes. The sidecar mounts
neither node keys nor the execution client's data PVC. Its Python standard-library
program ships in the chart; `peerAllowlist.image` supplies a Python 3.12+ runtime,
so no custom sidecar image needs to be published.

The chart rejects `admin` in HTTP/WS API lists and conflicting network/IPC
`extraArgs` when enabled. Keep privileged IPC access local. Helm values remain
trusted operator input; arbitrary custom containers or Pod overrides can change
the security boundary.

## Verification

Inspect every bootnode's `peer-allowlist` container logs and readiness. A
successful cycle reports the number of desired public keys and confirms that
no unauthorized peers are currently connected. Readiness indicates successful
RPC reconciliation, not independent proof of Reth's internal trusted set.

Before production use, test the selected image with compatible disposable peers:

1. Configured sequencer peers connect, reconnect and survive an empty runtime list.
2. A public key absent from both lists cannot establish an accepted P2P session.
3. Adding its key permits a connection without changing bootnode Pod UIDs.
4. Removing a connected runtime key disconnects it and prevents reconnection.
5. Adding and removing a runtime key before its first connection also denies it.
6. Restarting only Reth restores the list without editing the ConfigMap.
7. Restarting only the sidecar, including across a policy deletion, converges.
8. Multiple bootnode releases converge after one shared policy upgrade.

The SDK tests exercise reconciliation against a simulated Reth RPC interface and
real Unix sockets, plus chart rendering. They are not live Reth or Kubernetes
acceptance tests.
