# Dstack internal monitoring

The controller chart pins dstack 0.21.5. Its native `/metrics` endpoint includes
fleet allocations, run counters, task CPU/memory/GPU metrics and DCGM telemetry
on supported backends. The monitoring chart adds a dashboard and internal alerts;
it does not publish these alerts to Instatus.

## Native path (no new Pod or GPU-host agent)

Deploy the controller as an independent release with `monitoring.enabled: true`.
The chart enables native metrics and the OpenTelemetry Prometheus exporter on the
same endpoint. It reserves the corresponding environment variables; setting an
upstream enable variable to `"false"` would still enable it, so disable through
the chart boolean instead. No OTLP endpoint or additional collector is needed.

Prometheus pulls the controller's internal Service. Dstack continues collecting
remote task metrics using its existing SSH/shim connections. Monitoring does not
need the cloud-provider keys, controller admin token or SSH keys. A dedicated
Bearer token protects `/metrics`, including when the controller also has ingress.
Do not reuse this token for remote write or API management. The monitor API has
no separate TLS listener; cross-cluster scraping requires a protected transport.

For CLI generation, add to the existing deployment spec or equivalent TOML:

```yaml
dstackController:
  enabled: true
  fullnameOverride: dstack-controller
  monitoring:
    enabled: true
    namespace: dstack-system
    auth:
      existingSecret: dstack-controller-monitoring
      key: token
    interval: 30s
    scrapeTimeout: 10s
    sampleLimit: 50000
    alerts:
      enabled: true
      unavailableFor: 2m
      failedRunsThreshold: 3  # failed runs in ten minutes
    gpuHosts:
      enabled: false
      expectedHosts: []
      staleAfterSeconds: 180
      unavailableFor: 5m
      diskAvailableRatio: 0.1
```

Monitoring is enabled by default whenever the CLI generates a controller.
The values shown above are defaults; set `monitoring.enabled: false` to opt out.
Namespace must be the actual controller installation namespace. The CLI sets a
stable `fullnameOverride` when monitoring is enabled so target labels, alerts
and Kubernetes Deployment metrics agree across release names. On an existing
installation, set it to the CURRENT Deployment/Service name before upgrading;
changing it can rename resources and create a different PVC.

`setup gen-secrets --dstack-only` generates a separate random monitoring token
once in private credential state, then reuses it. The Secret is uploaded by the
existing explicit `setup push-secrets --dstack-only` workflow. Both the controller
and its ServiceMonitor reference that Secret in the controller namespace; there
is no cross-namespace Secret reference. An externally managed Secret is also
supported when installing the charts without CLI-managed credentials.

`setup prep-charts --dstack-only -N` and `generate-from-spec --values-only` emit
`dstack-controller-production.yaml` plus `scroll-monitor-dstack.yaml`. Apply the
second file AFTER the monitor's normal production values. It is an overlay, not
an independent chart or release:

```bash
make -f Makefile.example install-scroll-monitor \
  KUBE_CONTEXT=YOUR_CONTEXT NAMESPACE=YOUR_CHAIN_NAMESPACE
make -f Makefile.example install-dstack-controller \
  KUBE_CONTEXT=YOUR_CONTEXT DSTACK_NAMESPACE=dstack-system
```

Run these commands from the deployment directory containing `Makefile.example`
and `values/`. If you copied the example to `Makefile`, omit `-f Makefile.example`.
Prepare the base `values/scroll-monitor-production.yaml` and provision its
referenced Secrets first. `prep-charts --dstack-only` generates only the two
dstack files; it does not create or fill the base monitor values. Prepare and
publish the controller's Secrets before installing the controller.

`install-scroll-monitor` automatically loads `values/scroll-monitor-dstack.yaml`
after the base production values when it exists, including when called by
`install-all`. Override `SCROLL_MONITOR_DSTACK_VALUES` for another overlay path;
an explicit empty value skips the overlay. To disable an existing integration,
regenerate an overlay with monitoring disabled rather than just omitting it.

`install-dstack-controller` installs the independent OCI chart, pinned to version
`0.1.3`, and creates its namespace if needed. `DSTACK_NAMESPACE` defaults to
`dstack-system`; it must match `dstackController.monitoring.namespace` and the
namespace containing the controller Secrets. Override `DSTACK_CONTROLLER_CHART`,
`DSTACK_CONTROLLER_CHART_VERSION` or `DSTACK_CONTROLLER_VALUES` for a local chart,
another version or another generated values path. The controller is installed
explicitly and is not part of the chain's `install-all` or `delete-all` targets.

These commands change the selected cluster; generation itself does not. For
manual chart usage, `charts/scroll-monitor/values/dstack.yaml` is the equivalent
monitor overlay. Install Prometheus Operator CRDs before the controller's
ServiceMonitor. The monitor explicitly discovers ServiceMonitors in the chain
namespace and controller namespace, and Alloy adds controller logs to its
namespace list. If discovery already includes more namespaces, retain them when
combining overlays. Prometheus Operator/Prometheus and Alloy need their normal
cross-namespace RBAC. Custom namespace-restricted installations must grant it.

To disable an existing integration, set `monitoring.enabled: false`, regenerate
and apply BOTH files. Omitting the monitoring block selects the enabled defaults.
Omitting the entire controller block still skips controller generation.

## Dashboard availability

**DogeOS / Dstack and GPU fleets** is included in the Grafana DogeOS folder
whenever bundled dashboards are enabled. There is no separate dstack dashboard
switch; panels without metrics show **No data**.

When dstack runs locally or is not ready for monitoring, explicitly set
`dstack.enabled: false` and upgrade only scroll-monitor. This keeps dstack alerts and
namespace log discovery disabled and does not install or modify dstack. Do not
apply the full `values/dstack.yaml` overlay until connecting the controller.

## Coverage and limits

- Controller unavailable and native scrape failure alerts are gated by desired
  controller replicas. Intentional scale-to-zero does not alert, and does not
  terminate remote GPU instances. Missing kube-state-metrics must be monitored
  separately by the Kubernetes monitoring stack.
- Failed run counters provide execution diagnostics; they are not proof queue or
  proof completion metrics. The proof coordinator/worker remain authoritative.
- Allocated GPU counts come from instance offers, not hardware detection.
- Native task metrics can be cached. A fresh Prometheus scrape timestamp is not
  the GPU observation time. Native temperature/XID/ECC panels are diagnostic;
  this integration intentionally does not page on cached GPU readings.
- Native DCGM collection covers running jobs and allocated GPU UUIDs. It does
  not provide complete idle-host monitoring. Container-only backends may not
  expose DCGM or host OS metrics. Missing DCGM panels mean no data, not healthy.
- The 30-second interval and 50,000-sample limit are starting limits, not a scale
  certification. Measure `/metrics` duration at your fleet size: upstream queries
  its database. Preserve job/GPU identity labels; aggregate in queries instead
  of dropping labels and creating duplicate series.

## Optional always-on GPU host monitoring

For hosts you control, run an Alloy service independently of dstack tasks. Start
from `host.alloy`; it uses the built-in Unix exporter, so no separate node-exporter
process is required. On bare metal/VMs use the host's `/proc`, `/sys` and `/`.
Containerized Alloy needs explicit host mounts and exporter paths; without those
it measures its own container. Keep the Alloy HTTP listener on loopback and use
a persistent WAL directory. Pin/test the Alloy version (the example is checked
against v1.8.2).

Set these variables through the host's service manager:

| Variable | Value supplied by the operator |
| --- | --- |
| `DSTACK_HOST_ID` | Stable unique ID, e.g. `gpu-01`; match `expectedHosts` |
| `DSTACK_NAMESPACE` | Controller namespace |
| `DSTACK_CONTROLLER` | Controller Deployment name |
| `DSTACK_REMOTE_WRITE_URL` | Private/VPN or authenticated TLS gateway to the chain Prometheus `/api/v1/write` |
| `DSTACK_REMOTE_WRITE_TOKEN_FILE` | Restricted file containing the gateway write credential |

The endpoint/gateway and its write credential are infrastructure-specific and
are NOT created by these charts. Do not expose an unauthenticated Prometheus
receiver publicly. This credential is different from the controller scrape token.
Host configuration and GPU allocation are not applied by the CLI.

Set `gpuHosts.enabled: true` and list expected host IDs to alert on absent/stale
`node_time_seconds`. This continues to work while tasks are idle. An empty
inventory supports scaling to zero; retire hosts from the list when intentionally
removing them. The heartbeat indicates host telemetry availability, not GPU
health, and assumes synchronized host clocks. Disk alerts require fresh host data.

If a persistent DCGM exporter is already running, append `dcgm.alloy` and set
`DSTACK_DCGM_ADDRESS` to its actual loopback endpoint. Inspect existing hostengine
and shim-managed exporter ownership first. Native task exporters may disappear
when tasks stop, so they cannot substitute for persistent idle-host monitoring.
Host-backed DCGM metrics carry `dstack_source="host"` to distinguish them from
cached controller metrics. GPU fault policy/temperature thresholds depend on the
hardware and backend; they are not inferred from utilization alone.

## Remaining upstream gap

Dstack 0.21.5's API exposes instance lifecycle/health information and job metric
timestamps, but has no dedicated read-only monitoring role. We do not introduce
an API poller holding a controller administrator token, nor patch private dstack
internals from a ConfigMap. A future native exporter change should expose actual
collection success/time, lifecycle state and expected inventory. Until then,
the native-only path cannot certify GPU/idle-host liveness; use the optional host
collector where available. Real GPU hardware/provider acceptance is separate
from chart and local monitoring tests.

Sources: [dstack metrics](https://dstack.ai/docs/concepts/metrics/),
[0.21.5 native exporter](https://github.com/dstackai/dstack/blob/0.21.5/src/dstack/_internal/server/services/prometheus/custom_metrics.py),
[Alloy Unix exporter](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.unix/).

## Local validation

The implementation was checked with strict Helm lint for both charts, existing
controller/monitor template tests, five cross-chart monitoring tests, and five
Prometheus behavior scenarios. The latter cover intentional scale-to-zero,
missing native scrape targets, cached GPU data, absent expected hosts and stale
host telemetry. Run the focused SDK checks from the repository root:

```bash
python3 -m unittest discover -s charts/scroll-monitor/tests -p test_dstack_monitoring.py
python3 charts/scroll-monitor/tests/check_dstack_alerts.py
```

The companion CLI passed 34 generation, preparation and credential lifecycle
tests, including legacy-state migration and repeat generation without token
rotation. TypeScript checking passed and targeted lint had no errors.
The host/DCGM Alloy examples started successfully with Alloy v1.8.2 in an
isolated local runtime. No real GPU provider, GPU machine or dstack controller
was deployed by this validation; idle-host/DCGM acceptance requires actual hosts
and the deployment's protected remote-write endpoint.
