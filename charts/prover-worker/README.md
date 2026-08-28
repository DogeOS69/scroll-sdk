# prover-worker

This chart installs the exact local Worker contract emitted by the versioned
`dogeos-proof-topology` compiler and projected by `scrollsdk setup prep-charts`.
The compiler owns the digest-pinned image, complete argv, environment,
capabilities, topology digest, and readiness evidence path. Do not construct
those fields by hand.

The default has zero replicas. A compiler-selected local Worker changes it to
one; an external Worker keeps it at zero and is launched from the separately
generated Compose bundle.

Install through the deployment contract so every compiler material uses
`--set-file` with integrity verification:

```bash
scrollsdk helper proof-helm \
  --component prover-worker \
  --release prover-worker \
  --chart ./charts/prover-worker \
  --namespace default
```
