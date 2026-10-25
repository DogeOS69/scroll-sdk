# Reth peer allowlist

This chart owns one ConfigMap and no workloads. Install it once per namespace;
any number of `l2-reth` bootnode releases in that namespace can reference its
`configMapName`. The default `peers: []` authorizes no additional identities;
startup-configured `reth.trustedPeers` (such as sequencers) remain allowed.

The list contains secp256k1 P2P public keys: 128 hex digits (x followed by y),
optionally prefixed with `enode://` or `0x`. It does not contain IP addresses,
ports, compressed keys, Ethereum addresses or private keys. The Helm schema
checks the format; the sidecar also checks that each point is on the curve.

After editing the operator-owned values file, upgrade only this release:

```sh
helm upgrade --install reth-peer-allowlist ./charts/reth-peer-allowlist \
  --namespace "$NAMESPACE" --values ./examples/values/reth-peer-allowlist.yaml
```

Helm manages the `peers.json` key. The mounted ConfigMap propagates to each
bootnode sidecar without restarting its Pod. Helm success means the ConfigMap
was updated; it does not mean every sidecar has applied it yet.

See [runtime allowlist setup and operation](../../examples/reth-peer-allowlist.md)
for bootnode configuration, policy updates and verification.
