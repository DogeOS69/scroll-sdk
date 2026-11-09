# Status page integration architecture

Division of responsibilities in the current code (2026-10-01): dogeos-core provides read-only health
facts and their interpretation contract; scroll-monitor ships the evaluation and publication scripts;
scroll-sdk-cli resolves actual deployment parameters. Mainnet, Testnet and Devnet use separate
configuration, Prometheus, status logs and component bindings. This document describes code behavior
and does not mean any network has been upgraded.

```text
core /metrics ──────────────────────┐
Alloy / external entry-point probes ┼──> Prometheus ──> scroll-monitor evaluator ──> Instatus
Official Node Sync collector ───────┘         │                 │
                                             └──> Grafana <── result /metrics
                                                    │          │
                                     internal alerts/display   └──> independent Instatus heartbeat
```

## Single owner of runtime rules

- core keeps the [health fact contract](https://github.com/DogeOS69/dogeos-core/blob/feat/core-health-observability/docs/engineering/core-health-observability.md)
  and the [external evaluation guidance](https://github.com/DogeOS69/dogeos-core/blob/feat/core-health-observability/docs/engineering/bridge-health-evaluator.md);
  the executable prototype and its tests are removed.
- `charts/scroll-monitor/scripts/status_page_health.py` owns the rules, PromQL and default thresholds.
  `status-page-delivery.py` gathers evidence, evaluates, applies confirmation windows, persists and
  publishes on a schedule in one process. The original `*-status-delivery` Deployment, Service and PVC
  names are kept so migration does not lose incident identity.
- The CLI generates deployment-specific URLs, chain IDs, networks, namespaces, node membership/replica
  counts, probe targets, component bindings and Secret references. Explicit operational policies are
  validated and passed through unchanged. The CLI does not generate built-in health PromQL and does not
  own failure/recovery defaults.
- Grafana is used for display and internal troubleshooting/alerting. Stopping Grafana, deleting or
  pausing rules, or sending resolved notifications cannot change public status.

This is one evaluation/publication process and one rule module; there is no separate generic rule
service. Other collectors only obtain facts and do not hold public component webhooks. The runtime does
not need an Instatus management API key.

## Decisions and evidence

Each round of queries finishes before the next round waits to start; slow queries do not stack new
rounds. Built-in rules use at most ten distinct queries, and the shared WF query is read only once. At
most eight concurrent HTTP requests run, each with a 10-second timeout and a 1 MiB response limit. The
evaluator queries Prometheus directly, never the core database, and does not trigger business queries
at scrape frequency. `/metrics` and `/health` only read the latest result and do not gather new
evidence.

The Grafana **DogeOS / Status-page health** dashboard shows fresh results, evidence completeness and
persisted incidents. Internal alerts cover loss of the evaluator, incomplete required evidence and
delivery failures, and never notify public components.

Results contain `operational/degraded/unavailable/unknown`, observation completeness, reason, coverage
and validity time. Recovery requires all required evidence to be complete, fresh and continuously
healthy; a confirmed failure can continue to stand while other evidence is missing. Expired or future
timestamps, duplicate sources, query failures and exhausted budgets are neither equivalent to a
business failure nor to recovery. By default failure confirmation takes 5 minutes and recovery
confirmation 10 minutes; restarts, sampling gaps, clock rollbacks and unknown periods all reset the
confirmation window.

The current rules cover public queue deadlines, canonical WF stalls and configured entry-point/node
probes. They are `pipeline` evidence, not proof of end-to-end transfer success. Not every rule in the
core guidance is implemented: when the quorum for new task signatures or the complete online set of
third-party signers lacks a reliable source, it cannot be replaced by the registered count or a single
task's signature count. The evaluator never calls third-party signer management interfaces and never
signs or submits deposits/withdrawals.

`publication.sourceNamespace` limits which core metrics are used; empty means the Helm namespace.
`health.withdrawalProcessorExpectedTargets` and `health.ethDaSubmitterExpectedTargets` each default to
1 and must be set explicitly when several valid instances are deployed. A missing target cannot cause a
false recovery just because Prometheus's current target set shrank. Business deadlines default to 0,
meaning unconfigured; this is neither a default SLA nor an instruction to ignore the dependency.

## Publication, credentials and loss of monitoring

Each component's mode is manual (no evaluation/publication), observe (evaluate without publishing) or
automatic (evaluate and publish). Public webhooks and the optional heartbeat Secret are given only to
the evaluation process. The CLI's management API key is used only for explicit plan/apply. A SQLite
PVC keeps active and pending incidents, and retries reuse the original identity. Unknown does not clear
an active incident; a maintenance window pauses publication and keeps the evidence. When an HTTP result
is ambiguous and health has flipped, the pending incident is kept, an internal alert fires and the
on-call reconciles it; the opposite event is never sent blindly.

Instatus uses the existing per-component webhook templates; public severity is still determined by
the reviewed `affectedStatus`. The evaluator's degraded/unavailable results are observable, but this
change does not add management API calls that modify Instatus templates dynamically. Automatic public
recovery must complete the health confirmation window; deploy manual mode before a manual takeover.

The optional independent heartbeat is sent directly by the evaluator and requires complete
observations for configured non-manual components and no delivery errors. A confirmed business failure
does not stop the heartbeat; missing evidence or loss of monitoring does. Unconfigured observe
components do not gate the heartbeat. The Instatus Cron Monitor notifies the internal on-call
independently; loss of monitoring does not automatically declare a network-wide outage.

## Upgrade

Regenerate the schema v3 configuration with the matching CLI and deploy the new chart. For the old
public Grafana rules/contact points, the CLI generates provisioning that deletes them by their reserved
UIDs, cleaning up only old managed publication resources and keeping internal notification policies.
Keep the same release, PVC, network and component bindings. During the upgrade, stop the old public
rules before enabling the new evaluator so two publishers never coexist. You can first deploy every
component in observe, confirm the old rules are gone and observations are correct, then deploy
automatic. The incident log is preserved across both steps.

See [publication configuration](status-page-publication.md), [health rules](status-page-health-rules.md)
and [production values](../examples/values/scroll-monitor-production.yaml).
