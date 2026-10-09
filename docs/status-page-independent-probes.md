# Probe deployment decision and optional independent sites

Decision, 2026-09-28: use the existing per-chain Alloy through the public DNS and
public ingress for the first public-entrypoint checks. Do not provision additional
probe Pods or VMs for this mode. Implementation, configuration, precise coverage
and acceptance are documented in [Alloy probes](status-page-alloy.md).

The independently hosted Instatus Cron heartbeat detects lost monitoring and
notifies internal operators. It does not classify every public component as down.
Existing Instatus network groups are reused. Planned maintenance integration is
last priority.

The deep `external` probe mode remains optional for browser rendering, WebSocket,
block freshness and cross-endpoint consistency checks. Native Instatus HTTP/API
monitors are another possible external perspective; they are not reconciled by
this implementation and must not become a competing automatic publisher for the
same component. Their coverage and behavior need separate acceptance.

The following is an optional deep-probe hosting proposal, not first-release
infrastructure, a requirement for Alloy mode, or provisioned resources.

## Self-hosted alternative, if deeper checks require it

Use two external locations outside the monitored chain clusters. Prefer different
providers and regions, with different public egress and no shared chain-cluster
control plane. Reuse genuinely independent operations infrastructure if available;
otherwise run a small Linux VM at each site with Docker Compose. A new Kubernetes
cluster is not required for this workload. If independent Kubernetes clusters
already exist, the implemented Helm chart is an equally valid deployment target.

Both sites observe the same public endpoints. With all three networks enabled,
each site runs three separate probe containers/configurations, one per network.
The current runtime takes one chain configuration per process. This preserves
per-network identity and keeps public endpoints sourced from their respective
work directories. Site hosts can be shared; do not combine all networks into one
CLI deployment directory or silently reuse one network's endpoints for another.

For an initial single-network pilot, 2 vCPU / 4 GiB per VM is a planning estimate,
not a benchmark or measured requirement. Measure Chromium RSS, probe duration and
CPU before adding networks. The existing chart requests 100m CPU / 512 MiB and
limits one probe to 1 CPU / 1 GiB; do not multiply that into a capacity guarantee.

## Data and credential flow

```text
Site A public egress -> public RPC / WS / Bridge / Blockscout
Site B public egress -> public RPC / WS / Bridge / Blockscout

chain Prometheus -- private scrape requests --> Site A/B metrics endpoints
chain Prometheus <-- observations + timestamps -- Site A/B metrics endpoints
       |
       v
existing chain Grafana -> delivery verifier -> component webhook -> Instatus

inside each chain: official Node Sync + core metrics -> same chain Prometheus
```

The probe requests must use public DNS and public ingress/TLS. The telemetry
connection must not turn those requests into private service/VPC routing or
split-horizon DNS that bypasses the user's public path. Use a split-route private
connection: only the metrics path is private. Test the effective DNS answer and
egress at both sites during acceptance.

Prometheus initiates collection from the external probe exporters. This does not
expose internal Grafana, Prometheus or Kubernetes APIs to a provider, nor require
an inbound remote-write receiver on the chain Prometheus. External measurement
from a separate network is an established blackbox monitoring use case; see the
[Prometheus exporter guide](https://prometheus.io/docs/guides/multi-target-exporter/).
Our runtime additionally performs chain-aware JSON-RPC and browser checks, so a
basic HTTP-200 blackbox module alone is not a replacement.

Use existing private connectivity if suitable, or a restricted WireGuard-style
VPN managed by us. Only the designated monitoring source may reach each network's
metrics listener. Bind published container ports to the telemetry interface and
allow only the exact required ports; VPN membership alone must not grant general
access to chain subnets. The existing runtime exports plain HTTP without built-in
authentication; it must stay on this restricted path. An HTTP endpoint exposed to
the internet is not the proposed deployment. See the
[Prometheus security model](https://prometheus.io/docs/operating/security/).

The external sites hold probe configuration and, if needed, their own narrowly
scoped VPN/network identity. They do not hold an Instatus management key, component
webhook URL, chain signing key, Grafana credential or Kubernetes credential for the
chain. An overlay credential is still a credential: keep it in the host/Secret
manager, not the generated public configuration or repository.

## Runtime and packaging

Reuse the implemented `status-page-probe` Python checks and Chromium/Playwright
runtime. Keep exactly one reporter per `(environment, chain_id, location)`; do not
run a VM container and a Helm release with the same identity during migration.
Current checks run roughly every 30 seconds, with timestamp-based freshness in
Prometheus. Browser checks are sequential within the worker, so measure the full
round duration with the actual endpoints and failure timeouts.

Proposed packaging work:

1. Add a CI image build/publish workflow, immutable version/SHA tags and a recorded
   image digest; keep Playwright's Python package and browser image versions aligned.
   The [Playwright container guide](https://playwright.dev/python/docs/docker)
   documents browser/runtime version alignment and non-root execution.
2. Add a Compose example with non-root execution, dropped capabilities, read-only
   root filesystem, writable bounded `/tmp` and `/dev/shm`, restart behavior and
   health checks equivalent to the existing Helm chart.
3. Mount the version-matched probe script and generated JSON configuration. The
   current image contains runtime dependencies only; the application is supplied
   by a chart ConfigMap. A VM cannot run that image without also receiving the script.
   Either package a matched release bundle or explicitly revise the image build to
   include the script; do not accidentally run a stale local script with new values.
4. Extend CLI export for the VM bundle, taking the existing per-network values as
   input. Site name, image digest and private listener address/port are deployment
   inputs. Preserve separate per-network bundles and support review before deployment.
5. Reuse `publication.probes.metricsTargets` to generate the chain Prometheus scrape
   job. The selected VPN/private connectivity must actually make these addresses
   reachable; chart generation alone does not establish that network connection.

No additional Grafana, Instatus publisher or full node is needed at an external
site. Deposits, withdrawals and DA remain based on core observations inside the
chain; official Node Sync remains an internal per-Pod collector. Independent
canary Node Sync is an optional different mode, not required for this rollout.

## Failure semantics and acceptance

With the currently implemented two-location policy:

- Both fresh sites agree healthy: healthy evidence.
- Both fresh sites agree affected: affected evidence, subject to failure window.
- One healthy / one affected: unknown and internal notification, not automatic
  classification as a regional partial outage.
- A missing, duplicate or stale reporter: unknown; never a recovery.

This is a conservative agreement policy, not majority voting. Three-site quorum
and regional incident classification would require explicit rule changes; simply
setting a larger site count does not implement voting.

Loss of the chain Prometheus/Grafana means these sites alone cannot update the
public page. The existing independent Instatus heartbeat notifies internal
operators; public components retain their last confirmed state until an operator
or valid restored monitoring changes them. An independently hosted automatic
publisher for complete monitoring loss is outside this proposal.

Pilot on one network, then repeat the configuration/export flow for the others.
Verify public DNS/TLS, browser/API behavior, fresh metrics from both locations,
private network ACLs, and component isolation. Exercise one-site failure, two-site
failure, disagreement, telemetry loss and recovery before enabling automatic
publication. Existing Instatus groups are already created and will be reused.
Planned-maintenance/automatic-publication integration remains last priority.
