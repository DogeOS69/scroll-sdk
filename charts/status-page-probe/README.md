# Independent public status probes

Optional **external** deep-probe mode. The selected first-release public-entrypoint
mode reuses existing Alloy; see [Alloy setup](../../docs/status-page-alloy.md).
Do not deploy this chart or export its values for `probes.mode: alloy`.

Build and push the runtime image from this directory's Dockerfile to your registry.
It contains Chromium, pinned Playwright and a WebSocket client; the probe script is
mounted from the Helm chart. There are no blockchain signing or Instatus credentials.

Export configuration from the deployment work directory with:

```sh
scrollsdk setup status-page --deployment-dir /path/to/network \
  --probe-values values/status-page-probe-production.yaml
```

Supply `enabled: true`, your image, and a distinct `location` such as `us-east`.
Deploy once at each of at least two independent sites outside the chain cluster:

```sh
helm upgrade --install dogeos-testnet-probe ./charts/status-page-probe \
  --namespace monitoring -f /path/to/site/probe-values.yaml
```

`config` is generated. Public probes remain external when official Node Sync is
collected inside the chain cluster. Only in optional external Node Sync mode does
`overrides.nodeRpcUrl` select that site's already running sync canary. Review
the required API JSON checks and explorer CSS data selector for the deployed versions.
URLs come from selected deployment inputs; no domain substitutions are performed.

The service exports port 9111 `/metrics`. Set `publication.probes.metricsTargets` in
the monitor production values to let the CLI merge a scrape job automatically. Either scrape it over your private monitoring
network from the chain Prometheus, or use a local Prometheus/agent with your existing
private federation/remote-write setup. This chart creates no public ingress. A minimal
additional scrape configuration for the chain Prometheus (use actual reachable hosts):

```yaml
kube-prometheus-stack:
  prometheus:
    prometheusSpec:
      additionalScrapeConfigs:
        - job_name: status-page-external-probes
          scrape_interval: 30s
          scrape_timeout: 10s
          static_configs:
            - targets:
                - '<PROBE_SITE_A_PRIVATE_METRICS_HOST>:9111'
                - '<PROBE_SITE_B_PRIVATE_METRICS_HOST>:9111'
```

Merge this job with existing additionalScrapeConfigs; do not replace unrelated jobs.
Alternatively enable this chart's ServiceMonitor for a Prometheus at the probe site.
Preserve `environment`, `chain_id`, `component_key` and `location` metric labels.
Increasing replica count at one site is not additional independent evidence. Duplicate
reporters for a location prevent publication, as do disagreement or stale observations.

The probe performs read-only calls and browser form interactions, never transactions.
CLI `bridgeChecks: auto` derives typed history API checks from the selected
frontend configuration. Each JSON check requires either `equals` or `type`;
the latter validates a response field without requiring a fixed transaction count.
A broken local browser gives unknown; a loaded browser that encounters a broken page
reports affected. A dead probe's last timestamp ages out. Sequencing requires valid
RPC observations and explicit continuous production mode. On-demand chains need a
custom pending-work rule. Browser/API acceptance should be repeated after frontend
versions change; the built-in bridge flow targets the current DogeOS frontend UI.

For local verification:

```sh
python3 -m unittest discover -s charts/status-page-probe/tests
# With Playwright/browser installed:
STATUS_PROBE_BROWSER_TEST=1 python3 -m unittest discover -s charts/status-page-probe/tests
```

`STATUS_PROBE_CHROMIUM_PATH` may select an existing local Chromium binary for tests.

Deployment options, public request routing, private scrape isolation and the
proposed VM packaging are in [the independent probe plan](../../docs/status-page-independent-probes.md).
The Helm chart is implemented; VM packaging and automatic image publication are
proposals pending implementation. No separate Grafana or full node is required
at an external probe site when using official Node Sync.
