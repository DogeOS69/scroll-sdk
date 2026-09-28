# Public-entrypoint probes in the existing Alloy

Decision: use each chain's existing Alloy instance to request its public domains.
No additional probe Pod or external VM is required. When public WebSocket URLs
are configured, the CLI adds a small Node.js helper container to the existing
Alloy Pod; Alloy scrapes it over localhost and reuses its private remote-write path. Generate configuration offline, review it, and apply it
through the normal monitoring deployment workflow. This document does not claim
that any particular chain has been deployed or its public status verified.

```text
existing Alloy -> public DNS / public ingress -> RPC, Bridge, Blockscout
       |
       | probe metrics, existing private remote-write connection
       v
existing Prometheus -> existing Grafana -> delivery verifier -> Instatus
                              |
                              +-> Instatus Cron heartbeat -> internal operators
```

The delivery verifier and optional official Node Sync collector remain separate
existing features. “No additional probe Pod” refers to the public-entrypoint
checks, not a claim that every status-page feature executes inside Alloy.

## Configuration ownership

The complete examples are in `examples/values/scroll-monitor-production.yaml`
and the chart's production values. The relevant operator inputs are:

```yaml
statusPage:
  enabled: true
  environment: testnet # The network belonging to this deployment directory.
  sources:
    frontendsConfig: frontends-config.yaml
  publication:
    probes:
      mode: alloy
      metricsTargets: [] # No external exporter scrape job in this mode.
      bridgeChecks: auto # Derive public API URLs; JSON-path checks are external-only.
      explorerApiUrls: [] # Derived from the Blockscout backend ingress, or override.
      alloyChecks: [] # Optional additional GET response assertions, RE2 syntax.
      # - component: bridge-portal
      #   url: https://YOUR_PUBLIC_API/health
      #   bodyRegex: ['"status"\s*:\s*"ok"']
    heartbeat:
      enabled: false # Enable before switching any component to automatic.
      alertIds: [] # Instatus INTERNAL monitoring alert destinations, supplied by operator.
    components:
      public-rpc: {mode: observe, rule: {builtin: true}}
      bridge-portal: {mode: observe, rule: {builtin: true}}
      block-explorer: {mode: observe, rule: {builtin: true}}
```

- **Derived:** public URLs, chain ID, per-endpoint modules, check identities and a
  configuration revision. These appear in `statusPage.generated.alloyProbes`.
  Changes in endpoints/checks produce a new revision, so old samples cannot satisfy
  the replacement configuration. Repeated generation, including YAML round trips,
  preserves the same configuration when inputs have not changed.
- **Fixed runtime defaults:** Alloy v1.8.2 bundled by the existing chart, one Alloy
  replica, 30-second scrape interval, 5-second probe timeout and 10-second scrape
  timeout. HTTP 200 is required. Redirects are rejected, TLS verification remains
  enabled. Normal DNS resolution is used. No authorization headers or credentials
  are generated. The existing private remote-write URL remains configurable under
  `alloy.metrics.prometheusRemoteWrite.url`.
- **Configurable health:** existing `health.failureFor` (5m), `recoveryFor` (10m),
  `freshnessSeconds` (120), `maxRpcLatencySeconds` (2). RPC latency uses p95 of each
  individual HTTP probe, after at least ten samples within five minutes. It is not
  the multi-request sequence latency used by the external probe.
- **External-only settings:** `minimumProbeLocations`, browser selectors, canary
  dependency checks and external metrics targets do not make Alloy an independent
  external site. Explicit JSON-path `bridgeChecks` cannot be silently translated
  into HTTP checks: generation rejects them in Alloy mode. Use `auto` for API URL
  discovery and optional `alloyChecks` for response patterns.

Existing configurations without `probes.mode` normalize to `external` for backward
compatibility. New SDK examples explicitly select `alloy`. Set `external` explicitly
when using the separate deep-probe chart. `--probe-values` is rejected in Alloy mode.

## Exact coverage

| Component | Alloy evidence | Deliberately not established by that evidence |
| --- | --- | --- |
| Public RPC | Each public HTTP endpoint accepts `eth_chainId` and `eth_blockNumber`; expected response patterns, JSON content type, latency | Full JSON validation, block contents/freshness, cross-node consistency, transaction inclusion |
| Bridge Portal | Each page returns HTML/200; each derived history API returns JSON content type/200; optional body assertions | Browser rendering, CORS/browser fetch, wallet behavior, API JSON-path semantics, successful deposit/withdrawal |
| Block Explorer | Frontend returns HTML/200 and configured backend APIs return JSON content type/200 | Browser rendering, indexing freshness or canonical block-hash agreement |

The CLI records `coverage: public-entrypoint` in readiness and narrows these public
component descriptions to availability. Configured WebSocket endpoints execute real chain-ID and block-number JSON-RPC
exchanges in the supplemental container, including TLS validation, response IDs,
quantity validation, timeouts and latency. Missing or stale helper telemetry
keeps Public RPC unknown; a failed exchange is affected. Missing Bridge or
Explorer API endpoints also leave the corresponding built-in unready.

The pinned Blackbox implementation supports response regular expressions, not a
general JSON parser or arbitrary Python/JavaScript execution. A pattern match is
not a full semantic JSON validation. Do not describe these checks as equivalent
to the optional browser/chain-aware external checks.

With official Node Sync and continuous block production, Sequencing uses the
existing collector to read the active reference sequencer directly. A fresh valid
reference with an old block is affected; missing RPC/discovery evidence is unknown.
Follower failure does not itself mark Sequencing affected. Other modes still need
a custom metric expression. Returning a block number alone does not prove new blocks or accepted
transactions are progressing. Official Node Sync and the application business
metrics retain their existing rules; business deadlines still require confirmed
operator inputs. No missing check is replaced with a constant healthy expression.

## Failure and heartbeat semantics

Every configured check must have exactly one fresh `probe_success` sample and one
fresh successful exporter scrape (`up=1`). A failed request yields `probe_success=0`
and affected evidence. Missing, duplicate, invalid, stale or old-revision samples
yield unknown, never recovery. All endpoints must recover before a component can
begin its recovery window. The existing delivery verifier rechecks this expression.

The heartbeat requires fresh complete Alloy telemetry. A legitimate target failure
still sends heartbeats; loss of Alloy, its scrape/remote-write path, Prometheus,
Grafana or the configured delivery verifier stops them. Instatus's existing Cron
monitor reports missed heartbeats to internal destinations. It does not declare
every public component down and does not infer a public recovery.

Automatic publication in Alloy mode requires `heartbeat.enabled: true` and actual
internal `alertIds`; offline/observe generation works without provider credentials.
Use `--apply --create-webhook` to create/reuse integrations and the Cron monitor.
Apply the generated component and heartbeat Secret manifests using the existing
Secret workflow. Verify the first heartbeat reaches Instatus and starts its timer.
The management API key remains CLI-only; Alloy receives no Instatus credential.

## Deployment acceptance

```sh
scrollsdk setup status-page --deployment-dir /path/to/network
scrollsdk setup status-page --deployment-dir /path/to/network --plan --create-webhook
scrollsdk setup status-page --deployment-dir /path/to/network --apply --create-webhook
```

Generation does not deploy Helm resources. Deploy the generated monitoring values
and scoped Secrets normally; retain the existing one-replica Alloy configuration.
Helm rejects disabled Alloy, alternate ConfigMaps, autoscaling/clustering, multiple
replicas, missing generated snapshots or a disabled bundled remote-write receiver.
OTLP may be disabled without disabling the probe remote-write path.

Check DNS resolution and routing from the actual Alloy Pod: the hostname alone
does not prove public ingress is traversed. Avoid split DNS to private Services,
Host/IP overrides, special WAF bypasses and TLS exceptions. The CLI rejects obvious
private/literal URLs but cannot verify a deployment's DNS or network path offline.

Validate TLS failure, HTTP failure, incorrect RPC chain ID, partial target loss,
Alloy restart and heartbeat expiry. A same-cluster probe covers the public entry
path from that network; it cannot independently report after the whole cluster
loses connectivity. The external heartbeat covers monitoring loss, not regional
user reachability. Optional external monitors may add that perspective later.

Local acceptance runs the rendered configuration in Alloy v1.8.2, writes real
probe metrics to Prometheus v2.52.0, verifies their labels, and tests failure/body
assertions against temporary HTTP fixtures. Promtool exercises missing, duplicate,
stale and revision-mismatched evidence. No live chain or Instatus page is mutated.

For Blockscout, a discovered backend root URL is checked at `/api/v2/stats`
to require a JSON API response. An explicitly configured non-root API path is
preserved. TLS certificate validation remains enabled for all public targets.
