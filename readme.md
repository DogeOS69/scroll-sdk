# DogeOS Scroll SDK

Helm charts, deployment examples and operational tooling for running a DogeOS
chain on Kubernetes. This repository is a fork of
[Scroll SDK](https://github.com/scroll-tech/scroll-sdk), extended for DogeOS
services, Ethereum data availability, proof workers and monitoring.

## Repository layout

- `charts/` – Helm charts. Released charts are published to
  `oci://ghcr.io/dogeos69/scroll-sdk/helm/<chart>`; development builds go to
  `oci://ghcr.io/dogeos69/scroll-sdk/helm/dev/<chart>`.
- `examples/` – The supported deployment: `Makefile.example`, production values
  under `examples/values/`, deployment spec examples and operator guides. Only
  the charts installed by `Makefile.example` are part of it; other charts are
  legacy upstream components.
- `docs/` – Reference documentation, such as the
  [production values contract](docs/production-values.md),
  [sequencer sizing](docs/sequencer-sizing.md), status page and alerting.
- `custom-images/` – Dockerfiles for images built from this repository; see
  [custom-images/README.md](custom-images/README.md).
- `partner-kit/` – Standalone kits for partner-operated attestation signers and
  offline recovery keys.
- `snap_tools/` – Helpers for EBS volume snapshots.
- `devnet/`, `ansible/` – Local devnet and prover playbooks inherited from
  upstream.
- `scroll-contracts/` – Git submodule with the DogeOS contracts.

## Getting started

Deployments are generated with the DogeOS fork of
[scroll-sdk-cli](https://github.com/DogeOS69/scroll-sdk-cli) using the spec
`plan`/`apply` workflow. Start with [examples/README.md](examples/README.md) and
the [step-by-step deployment guide](examples/deployment-spec.md).

Keep completed deployment inputs, credentials and environment records in a
private deployment workspace. This is a public repository; see
[AGENTS.md](AGENTS.md) for the rules on secrets.

## License

MIT; see [LICENSE](LICENSE). Upstream Scroll SDK copyright notices are retained.
