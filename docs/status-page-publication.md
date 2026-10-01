# Component publication and health collection

The implementation spans the scroll-sdk templates, scroll-sdk-cli generation/application,
and dogeos-core business observations. It does not deploy any particular chain.
Mainnet, Testnet and Devnet keep separate monitoring installations and manage their
own eight components on the shared Instatus page. L2Scan is outside this feature.

## Data flow and credentials

```text
core + Alloy / optional external probes + Node Sync -> Prometheus
Prometheus -> scroll-monitor evaluator + durable journal -> Instatus components / heartbeat
Prometheus + evaluator result metrics -> Grafana -> internal notifications
```

The single-replica evaluator ships with scroll-monitor. `status_page_health.py`
owns rules and defaults; `status-page-delivery.py` runs evaluation and publication
in one process. CLI generates deployment inputs and passes explicit policy overrides;
it does not generate built-in health expressions. Grafana is not on the publication path.
The evaluator retains the existing SQLite PVC and component identities. It holds
component webhook URLs and the optional Cron heartbeat URL. The management API key
stays in the CLI environment. See [architecture and migration](status-page-architecture.md).

No provider needs access to internal Grafana, Prometheus, application databases or
Kubernetes. The selected first-release path reuses Alloy inside the chain cluster
and its private remote-write connection. No separate public probe Pod is added.
See [Alloy probes](status-page-alloy.md) for exact coverage and heartbeat requirements.
The optional `external` mode uses separate deep probes in independent locations
with private metric collection; its deployment is not required for Alloy mode.

## Component modes

| Mode | Evaluation | Public delivery |
| --- | --- | --- |
| `manual` | No evaluation | Disabled for this component |
| `observe` | Built-in or custom rule evaluates when required inputs exist | Results available through evaluator metrics; no public publication |
| `automatic` | Requires configured health inputs and an applied component binding | Verified failure and verified recovery; evaluator must be enabled |

All production examples default to `automatic` with `rule.builtin: true`. Explicit `observe` remains an opt-out. Automatic generation rejects missing required inputs rather than downgrading publication. Missing
configuration is reported explicitly; missing observations do not manufacture
`vector(0)` health. CLI readiness is **configuration readiness, not live health**.
Existing values without a publication block retain the legacy bootstrap path.
New generation emits schema v3. Automatic components require `delivery.enabled`.
`observationContactPointName` is retained as migration metadata; it no longer
creates Grafana public rules. Internal notification policies remain operator-owned.
The generated provisioning deletes exact old managed public rule/contact-point UIDs.
Use the two-stage observe/automatic migration in the architecture guide to prevent
old Grafana and new evaluator publishers overlapping during rollout.

## Built-in observations

Every health expression yields exactly one unlabelled **0** (healthy), **1**
(affected), or no series (unknown). The evaluator also rejects non-binary, NaN or
multiple results. Missing observations and query errors are exposed as unknown in evaluator metrics;
they never resolve a public incident. Internal alerts consume these metrics.

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
`publication.sourceNamespace` defaults to the Helm namespace. Expected WP/DA target
counts default to one; set `health.withdrawalProcessorExpectedTargets` and
`health.ethDaSubmitterExpectedTargets` to the actual expected counts (1..32).
A vanished target cannot reduce the required healthy evidence. Policy defaults live
in the chart script; `health: {}` passes no overrides. Unconfigured deadlines reject
automatic built-ins. The guidance catalogue also describes rules not implemented
here, including complete new-work signer quorum; current coverage is pipeline only.

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
Each automatic component needs an explicitly reviewed `affectedStatus`; subscriber
notifications default to false. Instatus severity comes from that fixed component template,
not from dynamic management API writes by the evaluator. `--plan` exposes the incident policy. These provider contracts are covered
by transport tests and a [Devnet acceptance run](status-page-devnet-acceptance-2026-09-28.md).
Each new deployment still needs scope and delivery verification before public
activation. Local validation does not create public incidents.

## Failure, recovery and delivery state

The evaluator requires continuous fresh failure evidence (default 5 minutes) and
continuous fresh recovery evidence (default 10 minutes). It polls Prometheus itself
and accepts no Grafana firing/resolved signals. Unknown samples, query failures,
sampling gaps, clock rollback and process restart reset confirmation windows.
Independent known failure survives missing evidence for another rule; recovery
requires every configured rule. Internal URLs and raw errors are not published.

The PVC retains active and pending events; process restarts recheck the full window
before resuming. Retries use the same payload, start time and component identity. This
is at-least-once transport, not an exactly-once provider guarantee. If an HTTP response
was ambiguous and health changes before its event is confirmed, the journal remains
pending and raises an internal delivery alert; an operator reconciles that incident.
An uncertain event is never blindly replaced by an opposite event. Back up the PVC;
losing it requires reconciling existing incidents before enabling automatic delivery.

Deploying manual/observe stops public delivery; observe continues evaluation.
Local YAML edits or CLI metadata-only apply do not change running Pods. Bindings,
journals and incidents are retained. Use manual before operator takeover. A
Grafana silence is not a publication control.

## Independent monitoring-loss detection

`heartbeat.enabled: true` requires Instatus **monitor alert destination IDs** in
`heartbeat.alertIds`. These are provider-side internal alert destinations, distinct
from Grafana contact points and public subscribers. The evaluator sends the heartbeat
after each complete round, withholds it for incomplete configured evidence or delivery
errors, and excludes manual/unconfigured observe components. Known business failures
still send a heartbeat. Instatus checks a 180-second period plus 180-second grace and
notifies internal destinations without creating public incidents. Verify the first
ping and internal destination during rollout. Disabling and applying pauses the
remote monitor; deploying disables local heartbeat sending.

References: [Grafana webhook format](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/),
[Instatus monitoring integrations](https://instatus.com/help/api/monitoring-integrations),
[incident templates](https://instatus.com/help/api/templates), and
[Cron Monitors](https://instatus.com/help/api/monitors).

## Reproducing local acceptance

From scroll-sdk:

```sh
SCROLL_STATUS_RUNTIME_TEST=1 python3 -m unittest discover -s charts/scroll-monitor/tests -p 'test_status_page*.py' -v
python3 -m unittest discover -s charts/status-page-probe/tests -p 'test_*.py' -v
```

The first command uses Docker with Prometheus 2.52 promtool for real rule semantics.
It also exercises publication/recovery with local HTTP fixtures, no Grafana or Instatus credentials.
From scroll-sdk-cli with a matching SDK checkout:

```sh
SCROLL_STATUS_CHART=../scroll-sdk/charts/scroll-monitor npx mocha 'test/utils/status-page*.test.ts' 'test/commands/setup/status-page.test.ts'
```

The SDK workflow owns rule and evaluator tests; the CLI workflow tests parameter
generation, provider bindings and the matching chart contract. These local checks do
not assert live deployment or public incident acceptance for a particular network.
