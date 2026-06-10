# scroll-reth examples

The default chart values and production examples still use `l2geth`.

Use these opt-in overlays only when testing the DogeOS `scroll-reth` image:

- `l2-sequencer-scroll-reth-production.yaml`
- `l2-bootnode-scroll-reth-production.yaml`
- `l2-rpc-scroll-reth-production.yaml`

These examples expect an image that provides `dogeos-reth-entrypoint` and reads
the `L2RETH_*` environment variables shown in each values file. The genesis
ConfigMap should expose `genesis.json` generated from `l2reth-genesis.json`.
