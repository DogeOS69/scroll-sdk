# Component publication and health collection

The implementation spans the scroll-sdk templates, scroll-sdk-cli generation/application,
and dogeos-core business observations. It does not deploy any particular chain.
Mainnet, Testnet and Devnet keep separate monitoring installations and manage their
own eight components on the shared Instatus page. L2Scan is outside this feature.

## Data flow and credentials

```text
Existing Alloy public-entrypoint probes ──metrics──> chain Prometheus <── dogeos-core /metrics
                                               ^
                          official Node Sync collector (inside the chain cluster)
                                               │
                                               v
                                         chain Grafana
                                          │          │
                                component alerts     heartbeat
                                          │          │
                                          v          v
                                delivery verifier   Instatus Cron Monitor
                                          │          │
                                scoped webhooks      internal monitor alerts
                                          v
                                Instatus network components
```

The delivery verifier is a small, single-replica workload in scroll-monitor. It
exists because Grafana can resolve alerts during rule lifecycle changes, and the
bundled Grafana 11.1.5 cannot be assumed to implement newer recovery-period fields.
It checks the same Prometheus health expression, applies a recovery window, retains
a SQLite delivery journal on a PVC, and sends a sanitized Grafana webhook payload.
It holds **only component webhook URLs**. CLI `INSTATUS_API_KEY` manages Instatus
resources and is never placed in values, a ConfigMap or a runtime Pod. The optional
Cron heartbeat URL is a separate, narrowly scoped Secret held by Grafana.

No provider needs access to internal Grafana, Prometheus, application databases or
Kubernetes. The selected first-release path reuses Alloy inside the chain cluster
and its private remote-write connection. No separate public probe Pod is added.
See [Alloy probes](status-page-alloy.md) for exact coverage and heartbeat requirements.
The optional `external` mode uses separate deep probes in independent locations
with private metric collection; its deployment is not required for Alloy mode.

## Component modes

| Mode | Evaluation | Public delivery |
| --- | --- | --- |
| `manual` | Previously provisioned rules remain but are paused | Disabled for this component |
| `observe` | Built-in or custom rule evaluates when required inputs exist | Internal observation receiver only |
| `automatic` | Requires configured health inputs and an applied component binding | Verified failure and, when delivery is enabled, verified recovery |

All production examples default to `automatic` with `rule.builtin: true`. Explicit `observe` remains an opt-out. Automatic generation rejects missing required inputs rather than downgrading publication. Missing
configuration is reported explicitly; missing observations do not manufacture
`vector(0)` health. CLI readiness is **configuration readiness, not live health**.
Existing values without a publication block retain the legacy bootstrap path.
Existing component configurations retain direct firing-only delivery unless
`publication.delivery.enabled` is selected; new examples enable verified delivery.

`observationContactPointName` must name a real internal Grafana receiver. Its
`grafana-default-email` default does not configure SMTP or recipients. Public rules
have direct notification settings and do not replace the global notification-policy
tree. Legacy public rules/routes are preserved: retire any competing publisher
before activating these component rules.

## Built-in observations

Every health expression yields exactly one unlabelled **0** (healthy), **1**
(affected), or no series (unknown). The outer rule also rejects non-binary, NaN or
multiple results. Missing observations and query errors notify the internal receiver;
they never resolve a public incident.

New examples select `probes.mode: alloy`: HTTP entrypoint availability and response
patterns for Public RPC, Bridge and Blockscout, with coverage exposed in readiness
and public descriptions. This does not prove browser rendering or indexing freshness.
Official continuous sequencers use the reference collector for block-age checks; other sequencing modes require a custom rule. Configured WebSocket RPC uses a supplemental container inside the existing Alloy Pod, with real read-only JSON-RPC exchanges.
Official Node Sync and business rules are unchanged. Details: [Alloy](status-page-alloy.md).

The following table describes the deeper **external** probe mode and the shared
business/Node Sync rules:

| Component | Implemented evidence | Deployment inputs |
| --- | --- | --- |
| Public RPC | Every declared HTTP/WS endpoint: chain ID, block number, block contents; p95 request-sequence latency after at least 10 samples/5 minutes | URLs/chain ID generated; independent locations and latency threshold |
| Transaction Sequencing | Valid RPC observations and latest block age | Explicit `continuous` production mode and appropriate maximum block age |
| Deposits | Confirmed canonical deposits not yet scanned, plus committed deposit messages not yet included by L2; complete indices and canonical RPC checks | New dogeos-core metrics; confirmed processing deadline |
| Withdrawals | Protocol-eligible canonical withdrawal indices not fulfilled; complete unique queue, replay/indexer agreement and canonical RPC checks | New dogeos-core metrics; confirmed processing deadline |
| Batch Publication | Ready, submitted and failed lifecycle batches still awaiting publication confirmation; excludes confirmed/finalized/orphaned work | New dogeos-core metrics; deadline including normal confirmation time |
| Node Sync | Official per-Pod follower height/hash versus the active sequencer, or an explicitly selected external canary | Select effective sequencer, bootnode and RPC sources; see [Node Sync](status-page-node-sync.md). External mode requires canary/dependency checks. |
| Bridge Portal | Chromium renders the deposit UI, produces the expected recipient payload, switches to withdrawal UI, validates runtime chain ID and API JSON through browser fetch | Reviewed required public API checks |
| Block Explorer | Rendered data selector, Blockscout block API, indexed hash verified against canonical RPC and index lag measured by block time | Backend ingress derived when available; reviewed data selector and lag threshold |

External-mode public probes require the configured number of **distinct locations** to report
valid, fresh, binary observations and agree. Disagreement, duplicate reporters,
missing locations and stale/future timestamps produce unknown. A location label
is a deployment assertion: two replicas in the same cluster are not independent.
All configured endpoints within a location contribute to that component's result.

The bundled sequencing probe supports continuous block production. An on-demand
chain must provide a custom expression based on accepted, executable pending work;
absence of blocks on an idle chain is not a failure. Official Node Sync uses a
separate in-cluster collector; internal Pods are not independent probe locations.
In external mode, the node probe observes an
operating canary and its dependencies; it does not create a node or perform a fresh
snapshot/bootstrap on every check. The bridge check does not submit deposits,
withdrawals, connect wallets or prove that a transfer completed; business components
use their separate queue observations.

Business deadlines deliberately default to **0 = unconfigured**. There is no guessed
public SLA. The withdrawal deadline starts at protocol eligibility, not the initial
user transaction; earlier batch/DA delays are observed by the other components.
Jobs must select the actual withdrawal processor role, excluding proof-only workers.

Production examples use `sequencingMode: auto` and `bridgeChecks: auto` with the
selected sequencer and frontend runtime configuration files. These regenerate
from current deployment evidence and preserve explicit overrides. See
[source-derived defaults](status-page-defaults.md) for source fields, API response
contracts, observed Devnet inputs, and why service timers are not public deadlines.

## Configuration and commands

All fields, owners and defaults are in `examples/values/scroll-monitor-production.yaml`.
The local workflow is:

```sh
scrollsdk setup status-page --deployment-dir /path/to/network
scrollsdk setup status-page --deployment-dir /path/to/network --plan --create-webhook
scrollsdk setup status-page --deployment-dir /path/to/network --apply --create-webhook
```

The first command is offline. Alloy mode generates the existing ConfigMap; do not
use `--probe-values` in this mode. Automatic mode requires an enabled internal
heartbeat. Only for `probes.mode: external`, add `--probe-values values/status-page-probe-production.yaml`. That probe export preserves existing top-level image and
location settings while regenerating `config` from the selected deployment. The
operator supplies the built probe image and independent location, then deploys that
chart separately. The proposed external-site delivery is described in
[independent probe deployment](status-page-independent-probes.md); its VM packaging
and image-release workflow are not implemented yet. In external Node Sync mode,
per-location canary addresses can be passed through the probe
chart's `overrides.nodeRpcUrl`. Prometheus needs a scrape path to each location;
set `publication.probes.metricsTargets` to generate its private scrape job, or
use existing federation. See the separate probe chart README. `--plan` only reads, including Cron Monitor
lookups; it does not write output files. `--apply` applies Instatus metadata,
component integrations and the optional heartbeat. **It does not deploy Kubernetes.**

Private files in this single-network work directory:

```text
secrets/status-page/
  public-rpc.binding.json
  public-rpc.secret.yaml
  ...one pair for each automatic component...
  heartbeat.json                 # optional private Cron Monitor receipt
  heartbeat.secret.yaml
```

Apply the generated Secrets through the deployment's Secret workflow into the
monitoring namespace, then deploy the generated monitor values. Files have mode
0600, the directory 0700, and a Git exclusion. Creation intent is durably saved
before POST. Ambiguous responses, lost receipts, changed targets, existing remote
heartbeat names and duplicate bindings block a second creation. Restore private
backups instead of deleting ownership metadata to force recreation.

Bindings created by older CLI versions may lack the template IDs. Restore those
IDs from the existing integration before applying; never create a replacement to
repair missing private state. Managed updates verify both the template and
integration subscriber flags: setting template `notify: false` alone is insufficient.
Use `--webhook-component` and `--webhook-url-file` with private JSON `{integrationId,url,createTemplateId,resolveTemplateId}`.

With `incidents.manageTemplates: true`, apply sends component-scoped creation and
resolution templates using the published Instatus integration/template contracts.
The default affected status is Degraded Performance; subscriber notifications default
to false. `--plan` exposes the incident policy. These provider contracts are covered
by transport tests and a [Devnet acceptance run](status-page-devnet-acceptance-2026-09-28.md).
Each new deployment still needs scope and delivery verification before public
activation. Local validation does not create public incidents.

## Failure, recovery and delivery state

Grafana's `for` and the verifier both require persistent failure evidence. The verifier
only starts a new incident after a matching Grafana firing signal and its own continuous
bad observations. The default recovery requirement is **10 minutes** of continuous
fresh health. Unknown samples, query failures, excessive sampling gaps, clock rollback
and process restart reset confirmation windows. Rule pause/delete/NoData resolution
messages do not constitute recovery. Dynamic Grafana labels, annotations, internal
URLs and raw error details are not forwarded in component notifications.

The PVC retains active and pending events; process restarts recheck the full window
before resuming. Retries use the same payload, start time and component identity. This
is at-least-once transport, not an exactly-once provider guarantee. If an HTTP response
was ambiguous and health changes before its event is confirmed, the journal remains
pending and raises an internal delivery alert; an operator reconciles that incident.
An uncertain event is never blindly replaced by an opposite event. Back up the PVC;
losing it requires reconciling existing incidents before enabling automatic delivery.

Changing a component to manual/observe and deploying stops its verifier activity and
switches/pauses the managed rule. Editing local YAML or metadata-only apply does not
change a running Grafana. Receivers, bindings, journals and incidents are retained.
Use manual mode before taking over an incident. UI silences alone do not remove an
already accepted event from the verifier; component mode is the publication control.

## Independent monitoring-loss detection

`heartbeat.enabled: true` requires Instatus **monitor alert destination IDs** in
`heartbeat.alertIds`. These are provider-side internal alert destinations, distinct
from Grafana contact points and from public page subscribers. Grafana evaluates a
Prometheus freshness query and requests a Cron Monitor heartbeat every minute; group scheduling may deliver every two minutes.
Datasource errors/NoData stop the heartbeat. When verified delivery is active,
the heartbeat also requires a fresh verifier tick and no delivery error. Instatus checks a 180-second period with
180-second grace, independently of the chain cluster. It creates no extra public
component or incident and does not claim that monitoring loss means chain downtime.
The first delivered ping activates provider-side timing. Verify the selected internal
notification destination and first ping during rollout. Disabling it and applying
pauses the remote monitor; deploying pauses the retained Grafana rule.

References: [Grafana webhook format](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/),
[Instatus monitoring integrations](https://instatus.com/help/api/monitoring-integrations),
[incident templates](https://instatus.com/help/api/templates), and
[Cron Monitors](https://instatus.com/help/api/monitors).

## Reproducing local acceptance

From scroll-sdk-cli, with the SDK checkout alongside it:

```sh
SCROLL_STATUS_RUNTIME_TEST=1 \
SCROLL_STATUS_CHART=../scroll-sdk/charts/scroll-monitor \
SCROLL_STATUS_GRAFANA_TEST=1 \
npx mocha 'test/utils/status-page*.test.ts' 'test/commands/setup/status-page.test.ts'
```

The Grafana test runs the generated provisioning in Grafana 11.1.5 and uses local
Prometheus API and provider fixtures. It verifies firing, NoData holding the active
incident, an independent recovery window and stable sanitized event identity.
PromQL cases use the real Prometheus 2.52 promtool. Neither test uses Instatus
credentials. Python delivery/Helm tests live in `charts/scroll-monitor/tests`;
independent probe tests live in `charts/status-page-probe/tests`.

The SDK `Test status page` workflow runs chart/delivery tests and the real Chromium
probe cases on relevant pull requests and pushes. The CLI `Status page acceptance`
workflow enables all three runtime flags above against a pinned SDK commit, real
Prometheus and Grafana. Update that SDK pin deliberately when changing the shared
generation contract. CI uses local receiver/API fixtures and no Instatus credentials.

Core images must contain the merged fixes in [core #1312](https://github.com/DogeOS69/dogeos-core/pull/1312)
(merge `c579df82ce2c8377ccde8001c91ad10d67f040c6`) and
[core #1314](https://github.com/DogeOS69/dogeos-core/pull/1314)
(merge `421806bbdb83b45b230d1f2359d62d1fc39e0387`), or equivalent later changes.
Both merges were verified on 2026-09-28. These supply indexer-confirmation-aligned
coverage, replay ages that survive unchanged canonical rewrites, and DA waiting
ages that survive retries. **Merging #1304 is not a deployment prerequisite.**
Verify the built image's source revision and live metric contract; a PR merge or
CLI configuration-ready result does not prove that the running image has it.
Performance follow-up is handled separately and is not evidence of live acceptance.

The indexed deposit observation boundary and the deployed confirmation settings
must be included when choosing the processing deadline. Old timestamps already
overwritten by earlier images cannot be reconstructed automatically.

## Delivery priorities

The operator confirmed that the Mainnet/Testnet/Devnet groups already exist. Reuse
them; group creation automation is not an outstanding delivery item. Maintenance
window integration is deferred until after the probe deployment and live public
failure/recovery acceptance. Until then, deploy a component in `manual` before
operator-led maintenance or incident takeover; changing Instatus alone does not
pause local automatic delivery. Scheduled per-component suppression is available through `publication.maintenanceWindows`; see [maintenance windows](status-page-maintenance.md). Publish the corresponding Instatus notice separately.

WF stalls are included in both deposit and withdrawal health. A fresh, online WP
with overdue active work and no WF progress for `health.wfStallSeconds` (3600 by
default) produces a public failure even when the corresponding business snapshot
is invalid, provided the independent workflow evidence is still valid. The CLI
uses core's persisted canonical-head observation time and process-local continuous
unchanged duration, with fresh jobs evidence; it no longer needs one hour of a
new Pod IP's Prometheus history. Restarted idle/recently progressing writers can
be evaluated immediately. Old overdue work without recent progress remains unknown
until continuity proves a stall. Upgrade core before regenerating these rules.
An idle WF is not an outage. Both WF and business health must be known
healthy to recover. See [the WF rule contract](status-page-health-rules.md#wf-停滞影响充值和提现).
