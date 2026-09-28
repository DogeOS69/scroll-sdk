# Devnet status-page acceptance — 2026-09-28

## Scope and configuration

Deployment directory: `/mnt/wsl/data/github/dogeos69/dogeos-aws-devnet`.
Cluster: `dogeos-devnet-cluster`; all commands selected its explicit kube context.
Namespace: `default`; Helm release: `scroll-monitor`.
Final release: revision 10, chart `scroll-monitor-0.1.33-dogeos`, deployed successfully.

The operator authorized changes only to scroll-monitor configuration and resources,
including reinstall/upgrade of that release. Other chain configuration and service
releases were not changed. SHA-256 comparison covers 61 pre-existing configuration
files outside scroll-monitor and found no changes during the acceptance run.

The shared Instatus page is `dogeos.instatus.com`; this deployment owns only its
existing Devnet group. The run reused that page and all eight component IDs.
Management credentials remained in an ignored local file and were not added to
Helm values, runtime Pods or source files. Monitor-owned webhook/heartbeat receipts
and Secret manifests use the deployment's existing `secrets/status-page/` directory.

The operator confirmed these configurable business deadlines:

| Rule | Seconds | Meaning |
| --- | ---: | --- |
| Deposits | 900 | Eligible deposit wait after required confirmations |
| Withdrawals | 3600 | Wait after protocol eligibility |
| Batch Publication | 1800 | Batch creation to confirmation; reconfirmed as 30 minutes |

Normal failure confirmation is 5 minutes. Normal recovery requires 10 continuous
minutes of fresh healthy observations. These windows are separate from business
deadlines and the 30-second collection interval.

## Real observations

| Component | Observation | Publication |
| --- | --- | --- |
| Public RPC | HTTP chain ID and block-number checks succeed; configured WebSocket is not covered by Alloy | Observe; built-in component unready |
| Transaction Sequencing | No accepted sequencing-progress expression is configured | Observe; built-in component unready |
| Deposits | Public deposit snapshot validity is 0; eligible queue evidence absent | Observe; unknown, never mapped to healthy |
| Withdrawals | Public withdrawal snapshot validity is 0; eligible queue evidence absent | Observe; unknown, never mapped to healthy |
| Batch Publication | Built-in DA health returns one fresh value 0 | Automatic, component-specific integration |
| Node Sync | Built-in comparison returns one fresh value 0; active sequencer and four official followers configured | Observe |
| Bridge Portal | Portal page succeeds; Bridge API fails TLS validation with a self-signed certificate | Observe; affected |
| Block Explorer | Blockscout fails TLS validation because its certificate is expired | Observe; affected |

Alloy probes run in the existing cluster through configured public domains. They
are not an independent geographic vantage point or browser rendering test. TLS
validation remains enabled. Certificate/service fixes are outside this run's
allowed configuration scope.

An independent Instatus Cron monitor receives Grafana heartbeats. It is internal,
has no public component, and cannot create public incidents. Its configured email
recipient is the operator-selected internal address. The period is 180 seconds
with 180 seconds grace. Normal one-minute Grafana repeats were observed arriving
at two-minute intervals; the original 60-second period produced false degradation.
During the outbound delivery failure, provider statistics recorded a missed
heartbeat at 04:36:44 UTC and recovery at 04:41:19 UTC. This independently detected
monitoring delivery loss without creating a public incident. Email inbox delivery
itself was not verified.

Existing Grafana SMTP is unconfigured. Observation alerts are evaluated and visible
in Grafana, but the existing default email contact point cannot deliver them.
The separate Instatus heartbeat notification does not depend on Grafana SMTP.

## Authorized E2E event

The operator explicitly authorized a public `[E2E TEST]` event for Devnet with
subscriber notifications disabled. Both Instatus template `notify` and integration
`onFailNotifySubscribers` / `onRecoverNotifySubscribers` were read back as false.
Only Devnet Batch Publication was bound to the test integration.

A temporary, time-bounded monitor expression simulated failure without interrupting
DA or any chain service. Grafana entered firing, armed the delivery verifier, and
the verifier persisted a single event identity to its PVC. A diagnostic replay of
that same queued event with an explicit User-Agent succeeded while debugging the
outbound client. The corrected worker subsequently retried and acknowledged the
same event automatically: pending=0, error=0, active=1. Instatus contained one event,
not a second incident after restart/retry.

Incident: `cmukra0l80ds21blcixbapkkw`.
Created: `2026-09-28T04:37:00.668Z`.
Title: `[E2E TEST] Devnet Batch Publication: simulated disruption`.

The temporary rule was replaced with real DA health, normal 5-minute failure and
10-minute recovery windows, and the confirmed 1800-second DA deadline. Recovery
verification started with the replacement delivery Pod at approximately 04:44 UTC.
Instatus automatically marked the same incident `RESOLVED` at
`2026-09-28T04:54:14.681Z`. The verifier's error, pending and active-incident metrics
all returned to 0. No direct management-API incident resolution was used.
Mainnet/Testnet component identity and status matched the pre-test snapshot.

After recovery, the CLI successfully reapplied the ordinary managed templates while retaining
`notifySubscribers: false`, the same integration/template IDs, and the existing
heartbeat. A final provider read confirmed eight Devnet components and Batch
Publication `OPERATIONAL`. The E2E event remains as a resolved historical record.

## Fixes discovered by live acceptance

- Add the Prometheus-selected instance label to Node Sync and delivery ServiceMonitors.
- Send the explicit delivery client User-Agent accepted by the provider.
- Check Blockscout's JSON `/api/v2/stats` endpoint when discovery returns a backend root URL.
- Persist the integration's create/resolve template IDs in its private receipt.
- Encode integration templates using `name.default.value` and `message.default.value`.
- Reconcile and verify subscriber flags on both the templates and the integration.
- Verify automatic create/publish/recovery flags and template component ownership.
- Allow heartbeat scheduling jitter with a 180-second period rather than 60 seconds.

The current public integration API behaves differently from its short documentation
example: minimal label-only/template requests returned HTTP 500 validation errors.
The corrected shape was verified against this account; the CLI also verifies the
resulting template and integration policy before producing deployable credentials.
Older component bindings lacking template IDs require recovery of those IDs from
the existing integration, not creation of another integration.

## Validation and remaining work

- SDK: 24 status-page template, Node Sync and durable-delivery tests passed.
- CLI: 57 tests passed with Helm rendering, Prometheus expression scenarios and
  Alloy runtime checks enabled; final typed-client/policy unit regression passed.
- CLI TypeScript build passed; targeted ESLint has zero errors.
- Actual devnet Prometheus, Grafana, official-node collector and Instatus account
  were used; no chain service fault was injected.

This is not evidence that every public component is automatically updated or
healthy. WebSocket coverage, sequencing progress, valid withdrawal-processor
business snapshots, affected public TLS endpoints, and a working internal Grafana
notification destination still need resolution before enabling those components.
Planned-maintenance suppression remains deferred as previously agreed. Dstack
monitoring is a separate internal-only feature; no dstack/GPU runtime was deployed
in this acceptance run.
