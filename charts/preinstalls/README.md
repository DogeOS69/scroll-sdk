# preinstalls

Helm chart that runs the `dogeos-preinstalls` image as two ordered post-install
hooks on a fresh DogeOS L2:

1. **`{release}-preinstalls-deploy`** (hook-weight `1`) — waits for the L2
   sequencer, then runs `lib/deploy.sh` inside the container: presigned txs
   for Multicall3 + CreateX (+ upstream Safe Singleton Factory + Create2Deployer
   once their per-chain raw txs land), followed by Foundry CREATE2 deploys for
   Permit2, Safe v1.3.0 contracts, and EntryPoint v0.6/v0.7. Idempotent.
2. **`{release}-preinstalls-verify`** (hook-weight `10`) — waits for the
   Blockscout backend, then runs `lib/verify-blockscout.sh` to submit source
   verification for each preinstall. Best-effort: failures here don't roll
   back the deploy.

Sourcify is not invoked pre-launch (the chain ID has to be public in
`sourcify-chains-default.json` first). Run a sourcify backfill script
post-launch instead.

## Required values

```yaml
image:
  repository: ghcr.io/dogeos69/preinstalls
  tag: deploy-YYYYMMDD

envFrom:
  - configMapRef:
      name: preinstalls-deployment-env   # supplied by parent scroll-sdk chart

verify:
  blockscoutApiUrl: http://blockscout-backend:80/api
  blockscoutHealthUrl: http://blockscout-backend:80/api/v1/health
```

The configmap `preinstalls-deployment-env` must provide:
- `L2_RPC_ENDPOINT` — used by both pods (RPC URL + URL passed as arg).
- `PRIV_KEY` — deployer private key. Reuse the existing scroll-sdk L2 deployer
  (the EOA preallocated via `[genesis] L2_DEPLOYER_INITIAL_BALANCE` in
  `charts/scroll-sdk/config.toml`) — no genesis change required.
- `ETHERSCAN_API_KEY` — any non-empty string; Blockscout treats it as opaque.

## Re-running

A failed `verify` pod can be re-run without re-deploying:

```bash
kubectl delete pod {release}-preinstalls-verify
helm upgrade {release} . --reuse-values
```

The deploy pod is idempotent too — re-running skips contracts whose
runtime codehash already matches.
