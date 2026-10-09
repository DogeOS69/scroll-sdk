# Core signing metrics adapter

This chart includes an opt-in, standard-library Python adapter for DogeOS core's
signing snapshot v1. It reads Prometheus only. It does not connect to TSO health
APIs, signer providers, bridge databases or Instatus, and does not hold a service
account token or signing/publication credentials.

## Configure and deploy

The chart owns templates and runtime packaging. The following explicit inputs
belong to scroll-sdk-cli generation or reviewed Helm overrides; the CLI generator
has not been changed by this chart addition. The adapter is disabled by default.

```yaml
bridgeHealth:
  enabled: true
  environment: devnet
  chainId: "291"                # Example only: use the actual L2 chain ID.
  sourceNamespace: bridge       # Namespace label on the scraped core metrics.
  tsoJob: tso-service           # Exact Prometheus job for this deployment.
  expectedTargets: 1            # All current targets must be observed.
  intervalSeconds: 30
  freshnessSeconds: 120
  timeoutSeconds: 5
```

The Prometheus URL comes from `monitoring.datasources.prometheus.url`. The chart
renders a ConfigMap, single-replica Deployment, internal Service and ServiceMonitor.
It uses the existing Python runtime image convention; no new image is required.
If Status Page is enabled, environment/chain ID must match its generated catalog.
It does not rewrite generated publication rules, contact points or delivery state.

The actual TSO ServiceMonitor must already be collecting `/metrics`. A core image
without signing snapshot v1 produces unknown evidence rather than healthy zeroes.
The new core collector exposes no transaction IDs or per-input labels. Signer
metrics hosted by third parties are not required.

## Contract

The adapter issues one exact namespace/job-scoped Prometheus instant query for
`up` and the `tso_core_signing_*` snapshot fields. It validates schema version,
all required series, snapshot validity, numeric/count invariants, freshness,
expected target count, duplicate series and response warnings. A failure returns
an invalid observation, never zero backlog or a bridge outage. Instances are
kept separate: replicas are not assumed to hold disjoint transactions.

For each role, `satisfied + pending + unreachable = active - unclassified`, and
`waiting = pending + unreachable`. Oldest wait must be zero for an empty wait
queue. `pending` is unknown signer availability, not an online count.
Unclassified work preserves valid facts but sets `coverageComplete: false`.
Observer start timestamps identify process-local continuity, not canonical epochs.

There are two entry points in `scripts/bridge-health-prometheus.py`:

- `collect(config)` / one-shot CLI: typed evidence for an external Python evaluator.
- `--serve`: periodic collection plus `/metrics` for normalized operator evidence,
  and `/healthz` for collector-loop liveness. The renderer expires old output even
  if collection stops; query failures remove payload and invalidate evidence.

The normalized metrics use the `scroll_bridge_signing_` prefix. They include
`observation_valid`, `coverage_complete`, source observation/observer-start times,
active/unclassified counts and per-role quorum/wait counts and oldest wait.
Labels are configured `environment`, `chain_id`, existing `source_instance`, and
bounded `role`/`state`. No transaction, key, attempt or policy identity is added.
Consumers must require a fresh normalized observation timestamp in addition to
validity/coverage because an adapter target can itself disappear or stop scraping.

A one-shot response explicitly includes:

```json
{
  "coverage": "tso_signing_only",
  "businessStatus": "unknown",
  "observationValid": true,
  "coverageComplete": true,
  "validUntil": 1120,
  "sources": []
}
```

This abbreviated example omits actual sources and identifiers. A valid real
response always contains the configured number of sources. `coverageComplete`
means complete **signing evidence**, never complete deposit/withdrawal coverage.

## Status Page boundary

These metrics are inputs to the evaluator, not a replacement for the complete
business decision. Do not connect `unreachable > 0` directly to the deposits or
withdrawals MAJOROUTAGE webhook. TSO lacks the current canonical WP head/flow
mapping; terminal history is excluded, and an empty active queue cannot prove
new-work readiness. These limitations remain even after changing API data to
metrics. Missing data must not resolve an active incident.

The existing Status Page delivery component retains ownership of webhook secrets
and publication. Its current binary/fixed-severity contract is not silently
changed by this adapter. Full dynamic public severity and authoritative
flow/head/new-work capability inputs remain separate integration work.

## Validation

`tests/fixtures/tso-signing-v1.prom` is produced by the Rust collector renderer
and matches `dogeos-core/crates/tso_core/tests/golden/signing-metrics-v1.prom`
at core commit `7e3ee2877e3cd18eaa524473d6a14a83e659f29d`. The snapshot schema
remains v1; reordered metric families and updated HELP text need no parser change.
To refresh it from a core checkout:

```sh
DOGEOS_SIGNING_METRICS_FIXTURE=/absolute/path/to/scroll-sdk/charts/scroll-monitor/tests/fixtures/tso-signing-v1.prom \
  cargo test -p tso_core --lib signing_metrics_wire_contract_fixture
```

Run the adapter and Helm contract tests from scroll-sdk:

```sh
python3 -m unittest discover -s charts/scroll-monitor/tests -p test_bridge_health_prometheus.py -v
```

Tests cover real exported data, missing/duplicate series, wrong namespace,
expected targets, invalid numbers, inconsistent counts, unsupported schemas,
stale/future observations, scrape/query/network failures, unsupported work,
output expiry, namespace/chain configuration and credential-free deployment.
