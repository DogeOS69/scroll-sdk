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
| scroll-monitor-agent | 0.1.0-dogeos | enabled |

Promtail is not supported. Log and OTLP collection is provided by Grafana Alloy
through the independently installable `scroll-monitor-agent` chart.

## Standalone installation

```shell
helm upgrade --install scroll-monitor ./charts/scroll-monitor \
  --namespace monitoring \
  --create-namespace
```

The default service endpoints assume every component is in the same namespace.
They are configurable under `monitoring.datasources` and
`scroll-monitor-agent`.

## External backends

Install `scroll-monitor-agent` directly when Grafana, Loki, and Prometheus are
managed externally:

```shell
helm upgrade --install scroll-monitor-agent ./charts/scroll-monitor-agent \
  --namespace scroll \
  --values examples/values/scroll-monitor-agent-production.yaml
```

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
- Infinity: `dogeos-infinity`

## Discovery boundaries

Prometheus selects Helm-managed ServiceMonitors in its own namespace. This
keeps discovery scoped to the Scroll deployment namespace without requiring
monitoring-specific labels or version bumps in application charts.

Alloy limits pod-log discovery to the release namespace by default. Set
`scroll-monitor-agent.logs.namespaces` for an explicit namespace allowlist and
`scroll-monitor-agent.logs.podLabels` to require matching pod labels.

## Required cluster services

The chart does not install an ingress controller or a dynamic volume
provisioner. The configured Grafana ingress requires nginx, and persistent
components require a usable StorageClass.
