# scroll-reth examples

The default chart values and production examples still use `l2geth`.

Use these opt-in replacement values only when testing the DogeOS `scroll-reth`
image:

- `l2-sequencer-scroll-reth-production.yaml`
- `l2-bootnode-scroll-reth-production.yaml`
- `l2-rpc-scroll-reth-production.yaml`

Do not layer these files on top of the `l2geth` production values with multiple
`-f` flags; Helm deep-merges maps and can retain l2geth-only env/secrets.

These examples expect an image that provides `dogeos-reth-entrypoint` and reads
the `L2RETH_*` environment variables shown in each values file. The genesis
ConfigMap should expose `genesis.json` generated from `l2reth-genesis.json`.
