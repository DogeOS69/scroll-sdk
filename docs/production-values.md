# Production values contract

The `charts/<service>/values/production.yaml` files and their corresponding
`examples/values/<service>-production.yaml` files are the operator-facing
deployment contract. An operator must be able to review a production file and
understand its environment-specific runtime configuration without having to
discover operational defaults in `values.yaml` or in a Helm template. Fixed
workload structure remains owned by the chart.

## What belongs in a production values file

Every runtime-affecting setting exposed by the chart must be explicit. This
includes:

- image repository, immutable tag placeholder, and pull policy;
- command and arguments, including an explicit empty list when the image's
  `ENTRYPOINT` or `CMD` is intentional;
- enabled services, ports, target ports, protocols, probes, and monitoring;
- application environment variables, ConfigMap/Secret references, and native
  application configuration inputs;
- persistent and ephemeral storage, access modes, sizes, retention, mounts,
  and read-only flags;
- resource requests/limits and security settings supported by the chart.

Helm templates continue to own mechanical Kubernetes rendering: standard
labels, selectors, generated resource structure, and common-template wiring do
not need to be restated in production values.

Controller kind, replica capability, and update strategy describe the fixed
nature of a service rather than an environment decision. They remain in the
chart defaults, are constrained by the chart schema, and must not be repeated
in a production values file.

Secrets must not be copied into values. Production values declare the Secret
or ExternalSecret contract and the required keys; the secret material remains
in the configured secret provider.

## Shared protocol files

`scroll-common` owns two separate ConfigMaps:

- `genesis-config`, containing the key `genesis.json`;
- `protocol-context-config`, containing the key `protocol_context.json`.

Each consuming service declares the ConfigMap name, projected key, absolute
mount path, `subPath`, and `readOnly: true` in its production values. The file
contents remain centralized in `scroll-common`; duplicating them in every
service chart would create competing sources of protocol identity.

These files are intentionally mounted as single files with `subPath` because
the applications require stable, exact startup paths. Kubernetes does not
refresh a ConfigMap-backed `subPath` mount in an already-running container.
Therefore, a reviewed change to either shared ConfigMap must be followed by a
rollout/restart of every consuming workload. Do not treat either file as
dynamically reloadable configuration.

## Validation

`.github/scripts/validate_production_values.py` compares each supported chart's
defaults with both production overlays. CI rejects a change that adds a chart
default without making the corresponding production decision explicit, or
that obscures the image, network, probe, resource, or shared-file mount
contract. It also rejects production overlays that attempt to override the
chart-owned controller contract.
