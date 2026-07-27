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
| Native application metrics | `tso-service`, `withdrawal-processor`, `l1-interface`, `eth-da-submitter`, `fee-oracle-0` | Prometheus ServiceMonitor |
| Exporter-backed application metrics | `dogecoin` | Prometheus metrics exporter |
| Runtime health and logs | `proof-coordinator`, `cubesigner-signer` | kube-state-metrics, cAdvisor, and Loki |

`proof-coordinator` and `cubesigner-signer` do not currently expose a
Prometheus endpoint. The operations overview deliberately uses Kubernetes
readiness, restarts, resource saturation, and logs for them instead of showing
nonexistent application metrics. Proof queue depth and age remain visible from
the `withdrawal-processor`, which owns and exports those work-item gauges.

All service dashboards provide Prometheus datasource and namespace variables.
Embedded indexer queries are additionally constrained to their owning service
job so identically named metrics from `l1-interface` and
`withdrawal-processor` are not merged accidentally.

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
