# prover-worker

This chart installs the exact local Worker contract emitted by the versioned
`dogeos-proof-topology` compiler and projected by `scrollsdk setup prep-charts`.
The compiler owns the digest-pinned image, complete argv, environment,
capabilities, topology digest, and readiness evidence path. Do not construct
those fields by hand.

The default has zero replicas. A compiler-selected local Worker changes it to
one; an external Worker keeps it at zero and is launched from the separately
generated Compose bundle.

`scrollsdk setup prep-charts` embeds every compiler-generated text manifest in
the final values file. Validate that self-contained input once, then deploy it
with ordinary Helm:

```bash
scrollsdk setup proof-config-check
helm upgrade --install prover-worker ./charts/prover-worker \
  --values values/prover-worker-production.yaml \
  --namespace default
```
