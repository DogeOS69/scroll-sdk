# preinstalls-deployer

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

## Installation order and release artifacts

Install this chart after the L2 RPC and sequencer are ready, and wait for its
deployment hook to succeed **before installing the DogeOS contracts release**
(`contracts-production.yaml`). Helm waits for the hook to finish; a failed or
timed-out deployment must be investigated before proceeding.

The Helm chart and the deployment image are separate artifacts:

| Artifact | Registry reference | Client |
| --- | --- | --- |
| Release Helm chart | `oci://ghcr.io/dogeos69/scroll-sdk/helm/preinstalls-deployer`, version `0.1.1-dogeos` | Helm |
| Contract deployment image (standalone example) | `docker.io/dogeos69/preinstalls:v0.2.0` | Docker / Kubernetes |

The chart is published by this repository's `publish-chart.yaml` workflow.
Changes under `charts/preinstalls-deployer/` merged into `v0.3.0-develop` trigger that
workflow. Confirm the publish log includes this specific chart and that its
GHCR package is public; a green workflow alone does not verify anonymous access.
The separate `/helm/dev/preinstalls-deployer` package is not the release destination.
The image is published independently by
[dogeos-preinstalls](https://github.com/DogeOS69/dogeos-preinstalls).

Verify release availability with Helm, not `docker pull`:

```bash
helm pull oci://ghcr.io/dogeos69/scroll-sdk/helm/preinstalls-deployer --version 0.1.1-dogeos
```

A Helm chart uses Helm-specific OCI media types, so Docker reports an unsupported
media type when asked to pull it as a container image.

## Publication comparison

This is a copy of `charts/preinstalls` under a new OCI package name to diagnose
release-package access. The deployment image, resources, hooks, and default
values are unchanged; only the chart identity and helper names differ.
The original chart and umbrella chart are unchanged.

After the release workflow publishes this chart, test the package with an empty
Helm registry configuration to distinguish public access from cached credentials.
Check package visibility separately; a successful push does not imply public
read access.

The standalone `examples/Makefile.example` uses this chart by default, with
`examples/values/preinstalls-production.yaml` selecting `dogeos69/preinstalls:v0.2.0`
for both deployment and optional verification:

```bash
make install-preinstalls
```

Use the same release name when selecting this copy. Do not install both charts
as separate releases in the same namespace: they manage the same ConfigMap and
Secret names.

## Required values

```yaml
image:
  repository: dogeos69/preinstalls
  tag: v0.2.0

envFrom:
  - configMapRef:
      name: preinstalls-env   # public RPC configuration
  - secretRef:
      name: preinstalls-secret-env   # externally provisioned PRIV_KEY

verify:
  enabled: false  # enable only after Blockscout and its verifier are available
  image:
    repository: dogeos69/preinstalls
    tag: v0.2.0
  blockscoutApiUrl: http://blockscout-blockscout-svc:80/api
  blockscoutHealthUrl: http://blockscout-blockscout-svc:80/api/v2/stats
```

The ConfigMap `preinstalls-env` provides `L2_RPC_ENDPOINT`, used by both pods.
For optional Blockscout verification, `ETHERSCAN_API_KEY` can be a non-secret,
non-empty placeholder; Blockscout treats it as opaque.

The Kubernetes Secret `preinstalls-secret-env` provides `PRIV_KEY`. Reuse the
existing genesis-funded L2 deployer; no new identity or genesis allocation is
needed. Do not put the private key in a ConfigMap, committed values, or this
repository. Provision it through the deployment's existing Secret management
process.

## Re-running

A failed `verify` pod can be re-run without re-deploying:

```bash
kubectl delete pod {release}-preinstalls-verify
helm upgrade {release} . --reuse-values
```

The deploy pod is idempotent too — re-running skips contracts whose
runtime codehash already matches.
