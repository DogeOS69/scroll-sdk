# scroll-monitor-agent

Deploys Grafana Alloy as the Scroll SDK collection plane. It collects selected
Kubernetes pod logs into Loki and accepts OTLP/HTTP metrics for Prometheus
remote write.

By default, log discovery is limited to the Helm release namespace. Configure
`logs.namespaces` and `logs.podLabels` to use an explicit workload allowlist.
The Loki and Prometheus endpoints are configurable, so this chart can be used
with either `scroll-monitor` or external backends.
