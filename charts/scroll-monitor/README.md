# scroll-monitor

Self-contained observability stack for Scroll SDK. The default profile installs
Grafana, Prometheus/Alertmanager, Loki, and Grafana Alloy in one namespace.

## Architecture

```text
Scroll services -- ServiceMonitor --> Prometheus ----> Grafana
                                  \--> Alertmanager
Pod logs -------- Grafana Alloy --> Loki ------------> Grafana
OTLP clients ---- Grafana Alloy --> Prometheus
```

The chart vendors the following dependencies:

| Dependency | Version | Default |
| --- | --- | --- |
| Grafana | 8.5.0 | enabled |
| Loki | 6.10.2 | enabled |
| kube-prometheus-stack | 59.0.0 | enabled |
| Grafana Alloy | 1.0.2 | enabled |

Promtail is not supported. Log and OTLP collection is provided by Grafana Alloy
directly through the official Alloy chart dependency.

## Standalone installation

```shell
helm upgrade --install scroll-monitor ./charts/scroll-monitor \
  --namespace monitoring \
  --create-namespace
```

The default service endpoints assume every component is in the same namespace.
They are configurable under `monitoring.datasources` and
`alloy`.

## Dashboard and alert assets

Dashboard ConfigMaps are controlled by `dashboards.bundled.enabled` and are
rendered independently of `grafana.enabled`, allowing an external Grafana
sidecar to discover them.

Metric alerts are native `PrometheusRule` resources controlled by
`prometheusRules.enabled`. Notification routing and credentials belong to
Alertmanager configuration; this chart does not embed notification secrets.

The provisioned datasource UIDs are stable:

- Prometheus: `scroll-prometheus`
- Loki: `scroll-loki`

The bundled DogeOS dashboards are scoped to the services deployed by the
production stack:

| Dashboard coverage | Services | Source |
| --- | --- | --- |
| Native application metrics | `tso-service`, `withdrawal-processor`, `l1-interface`, `proof-coordinator`, `eth-da-submitter`, `cubesigner-signer`, `fee-oracle-0` | Prometheus ServiceMonitor or operator-managed scrape target |
| External native application metrics | `attestation-signer` | Operator-managed Prometheus scrape target |
| Exporter-backed application metrics | `dogecoin` | Prometheus metrics exporter |
| Runtime health and logs | All Kubernetes workloads | kube-state-metrics, cAdvisor, and Loki |

Dedicated dashboards cover `attestation-signer`, `proof-coordinator`, and
`cubesigner-signer`. Proof queue depth and age remain sourced from
`withdrawal-processor`, which owns and exports the durable work-item gauges;
the coordinator dashboard does not manufacture a second queue authority.

The three dashboards select application metrics through Prometheus `job` and
`instance` labels instead of Kubernetes-only labels. This lets the same panels
work for in-cluster ServiceMonitors and for Attestation Signers on external EC2
hosts. External scrape targets are deliberately not configured by this chart:
add them to the Prometheus instance through an operator-managed scrape config,
using a stable job name such as `attestation-signer`. Prometheus supplies the
`instance` label from each target automatically, so no host address needs to be
committed to Helm values or dashboard JSON.

For example, keep the three external targets in Prometheus' operator-managed
`additionalScrapeConfigs` (or the equivalent configuration managed by your
cluster), outside this chart:

```yaml
- job_name: attestation-signer
  metrics_path: /metrics
  static_configs:
    - targets:
        - <signer-1-host>:<metrics-port>
        - <signer-2-host>:<metrics-port>
        - <signer-3-host>:<metrics-port>
```

Replace the placeholders only in the cluster-managed configuration. Do not add
those host addresses to this chart. After Prometheus reloads successfully, the
Attestation Signer dashboard discovers the job and all three `instance` values
and shows their individual `up` status.

The Attestation Signer exports latency and payload-size observations as
Prometheus summaries. Its dashboard reads the exported `quantile` series
directly and preserves the `instance` label because summary quantiles cannot be
aggregated across signers. The `_sum / _count` series remain available for
average calculations. The CubeSigner and coordinator dashboards use their own
native metric types. The dashboards also expose bounded request, worker,
signing, callback, replay, and policy outcome counters as rates so throughput
and failure-volume changes remain visible.
The CubeSigner dashboard follows the metric contract merged in dogeos-core
#1009: it shows proof-fallback signs, policy denials, live policy evaluations,
the observed policy rule identity, and the two integrity counters that must
remain zero. CubeSigner deliberately does not register default Node.js process
metrics, so the dashboard does not query them.

All service dashboards provide a Prometheus datasource selector. Kubernetes
service dashboards use namespace variables; the signer/coordinator dashboards
use `job` and `instance` so they also work for external scrape targets.
Embedded indexer queries are additionally constrained to their owning service
job so identically named metrics from `l1-interface` and
`withdrawal-processor` are not merged accidentally.

The dedicated `reth` folder monitors the six Scroll L2 rollup-node workloads
deployed by the production example: two sequencers, two bootnodes, the internal
RPC service, and the public RPC service. Use **Scroll L2 Reth Fleet** for
multi-node health, chain-height divergence, derivation/L1-watcher progress,
resources, and logs. The other five dashboards are intended for a single-pod
drill-down.

The drill-down dashboards are Kubernetes adaptations of the official
`scroll-tech/rollup-node` dashboards at tag `v1.0.7-rc6` (commit
`bc3d5006c41b38cc442ebe92d1afc4285fc43ca1`), matching the rollup-node image
version used by the production values. The import is pinned and reproducible:

```shell
node charts/scroll-monitor/scripts/import-rollup-node-dashboards.mjs
```

Upstream source:
<https://github.com/scroll-tech/rollup-node/tree/v1.0.7-rc6/docker-compose/resource/dashboards>

## Discovery boundaries

Prometheus selects Helm-managed ServiceMonitors in its own namespace. This
keeps discovery scoped to the Scroll deployment namespace without requiring
monitoring-specific labels or version bumps in application charts.

Alloy limits pod-log discovery to the release namespace by default. Set
`alloy.logs.namespaces` for an explicit namespace allowlist and
`alloy.logs.podLabels` to require matching pod labels.

## Required cluster services

The chart does not install an ingress controller or a dynamic volume
provisioner. The configured Grafana ingress requires nginx, and persistent
components require a usable StorageClass.
