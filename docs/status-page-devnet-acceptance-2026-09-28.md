# Devnet status-page acceptance — 2026-09-28

The local scroll-monitor chart `0.1.37-dogeos` was applied to the
`dogeos-devnet-cluster` EKS cluster, namespace `default`, release `scroll-monitor`.
The E2E cleanup Helm revision is **17**; the automatic activation follow-up below
uses revision **18**. This is a local deployment result,
not evidence that the SDK/CLI changes have been committed, published or passed
remote CI.

## Scope and environment preservation

- Compared all 59 non-monitor files under the deployment's `values/` directory:
  no changes.
- Compared container images in all 20 non-monitor Deployments/StatefulSets:
  no changes. No dogeos-core image upgrade was performed.
- Changed the scroll-monitor values, its component binding receipts and Secrets.
  Reused the existing Instatus page and Devnet components.
- Slack webhook and channel remain empty for the operator to fill manually.
  No real Slack message was sent. SMTP remains disabled; email was not tested.
- Proof Coordinator remains **No data** until its new image is available.
  Image-dependent dashboard/alert/business-metric checks were skipped.
- Captured credentials, provider responses and live telemetry stay outside the
  repository. This document contains results, not example service metrics.

## Component results after E2E cleanup, before automatic activation

| Component | Automatic delivery acceptance | Real observation after cleanup | Final mode |
| --- | --- | --- | --- |
| Public RPC | Failure and recovery passed | HTTP and WebSocket checks healthy | observe |
| Transaction Sequencing | Failure and recovery passed | Continuous reference-node block age healthy | observe |
| Node Sync | Failure and recovery passed | Selected official followers healthy | observe |
| Bridge Portal | Failure and recovery passed | Availability rule affected; some configured checks fail | observe |
| Block Explorer | Failure and recovery passed | Availability rule affected; some configured checks fail | observe |
| Deposits | Skipped: deployed image lacks required complete evidence | Not re-evaluated | observe |
| Withdrawals | Skipped: deployed image lacks required complete evidence | Not re-evaluated | observe |
| Batch Publication | Previously accepted; retained | Delivery has no active/pending event or error | automatic |

The five new tests used temporary synthetic fault/recovery expressions in the
monitor's configuration. Each created exactly one `[E2E TEST]` incident and
automatically resolved that same incident. Public subscriber notification was
disabled. No business transaction or service failure was injected. This verifies
the publication pipeline, not a real business outage or business recovery.

All five incidents were resolved before cleanup. The normal Instatus templates,
real built-in rules, original publication modes, 5-minute failure confirmation and
10-minute recovery confirmation were restored. Batch Publication's deadline is
30 minutes. No synthetic constant expression remains in component rule inputs.
The other three existing components retained their identities and statuses.
New private webhook bindings remain reusable for later component activation.

The public page does not automatically follow the seven components left in
`observe`. In particular, resolution of the Bridge/Explorer **test incidents**
does not declare their actual checks healthy.

## Implementation and validation

- WebSocket RPC: read-only chain-ID/block-number exchanges from an auxiliary
  container in the existing Alloy Pod, with bounded request time, chain checking,
  freshness and missing-data protection. No additional probe Pod is needed.
- Continuous sequencing: reference-node evidence collected independently of
  follower failures by the existing official Node Sync collector.
- Scheduled maintenance: local component delivery suppression with fresh
  confirmation after the window. See [maintenance windows](status-page-maintenance.md).
  Automatic synchronization of Instatus maintenance notices is still separate;
  operators publish those notices themselves.
- SDK status-page Python suite: 29 passed. WebSocket socket/startup tests: 3 passed.
  Helm lint passed. CLI full status-page suite: 90 passed, including runtime
  Prometheus/Alloy/Grafana and local SDK rendering. TypeScript and targeted lint
  passed (existing complexity warnings remain).
- The SDK and CLI must be released together. When committing these changes,
  update the CLI acceptance workflow's immutable SDK commit pin to the newly
  published SDK commit before submitting the CLI changes.

Pending operator actions are Slack configuration and notification acceptance,
future business-image-dependent acceptance, and deliberate activation of each
component after its real checks are satisfactory. These were not bypassed with
fabricated healthy metrics.

## Automatic activation follow-up

The operator subsequently authorized automatic publication wherever prerequisites
were met. Revision **18** enables `automatic` for Public RPC, Transaction
Sequencing, Node Sync, Bridge Portal and Block Explorer. Batch Publication remains
automatic; Deposits and Withdrawals remain in observe mode because the deployed
business images do not provide the required verified evidence.

The activation gate is trustworthy health evidence and working scoped delivery,
not a requirement that every service be healthy. Independent HTTPS requests
confirmed the failing Bridge API certificate is self-signed and Blockscout's
certificate has expired. These are real public-access failures, not missing
metrics or probe regex errors. They are eligible for automatic incident reporting.
No certificate, ingress or business service was modified.

The five existing webhook bindings and normal single-component templates were
verified and reused. Grafana's live rules route to their matching public receivers;
the verifier tracks all six automatic components. Failure confirmation remains
5 minutes and recovery confirmation 10 minutes. Public subscriber notifications
remain disabled. Slack remains empty, SMTP disabled, and Proof Coordinator's
image-dependent checks remain skipped.

Only `values/scroll-monitor-production.yaml` changed in the deployment values
directory. All 20 non-monitor workload image sets remain unchanged. This follow-up
does not change the shared templates' safe default of observe mode for new chains.

At 10:39 UTC, real automatic publication was verified: Bridge Portal and Block
Explorer each entered `DEGRADEDPERFORMANCE` with one `INVESTIGATING` incident.
Their incident IDs are `cmul47kp803ih0xo8kdvj6210` and
`cmul47jzv00fv1mpcctofraw5`, respectively. These are genuine certificate-related
incidents, not E2E test events, and were left active for observed recovery.
Public RPC, Sequencing and Node Sync remained `OPERATIONAL`. No temporary fault
or recovery expressions were used for this activation.

## Severity correction

The initial `DEGRADEDPERFORMANCE` classification above came from an inappropriate
global template default, not measured slow performance. Both current incidents
were corrected in place after the endpoint failures were independently reproduced:
Bridge Portal is `PARTIALOUTAGE`; Block Explorer is `MAJOROUTAGE`. Their original
IDs and start times remain intact and both are still under investigation. No
recovery or replacement incident was manufactured, and subscribers were not notified.

The existing creation templates now use these explicit component policies. The
CLI rejects the old global `incidents.affectedStatus` and requires reviewed
per-component severity for managed automatic publication. Other existing policies
were preserved explicitly; this migration does not assert they can classify all
possible failures. See [severity semantics and remaining dynamic-classification
work](status-page-severity.md). Fixed template policies remain a limitation of the
current binary-health publication path.

The severity-policy configuration was applied successfully as Helm revision
**19**. Business workload images are unchanged. Validation passed: 91 CLI
status-page tests, 29 SDK status-page tests, TypeScript compilation and targeted
lint (complexity warnings remain). Mainnet/Testnet component identities and
statuses are unchanged; the corrected public component statuses and future
creation templates were both read back from Instatus.
