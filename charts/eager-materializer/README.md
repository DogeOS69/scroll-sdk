# Eager materializer

Requires the matching PR #1136-or-later compiler bundle. Install only when
`bundle-manifest-v1.json` declares `eager_materializer` (real Scroll
materialization with an RPC witness source). Mock **generation** is supported;
synthetic one-chunk **materialization** is not the eager profile.

The CLI projects compiler TOML, generated statement namespace and L2 genesis
mounts. Do not independently specify the bucket, prefix, RPC or proof identity
inside production values. Give the ServiceAccount prefix-scoped S3 list/read
and create-object access, or configure a genuinely shared local filesystem.
An independent local PVC is not a shared artifact store.

Runtime command, ports, probes and the small cursor/scratch PVC default are in
`values.yaml`. `/health` is process liveness; `/ready` checks discovery and chain
identity; `/metrics` is optional Prometheus monitoring. Readiness failure must
not restart the process. Missing or invalid bundles cause coordinator fallback;
the producer is never a correctness or availability dependency.
