# scroll-monitor

Self-contained observability stack for Scroll SDK. The default profile installs
Grafana, Prometheus/Alertmanager, Loki, and Grafana Alloy in one namespace.

## Architecture

```text
Scroll services -- ServiceMonitor --> Prometheus ----> Grafana --> Slack / Email
                                  \--> Alertmanager (infrastructure rules)
Pod logs -------- Grafana Alloy --> Loki ------------> Grafana
OTLP clients ---- Grafana Alloy --> Prometheus
```

The chart vendors the following dependencies:

| Dependency | Version | Default |
| --- | --- | --- |
| Grafana | 8.5.0 | enabled |
| Loki | 6.10.2 | enabled |
| kube-prometheus-stack | 59.0.0 | enabled |
| Grafana Alloy | 1.0.2 | enabled |

Promtail is not supported. Log and OTLP collection is provided by Grafana Alloy
directly through the official Alloy chart dependency.

## Standalone installation

```shell
helm upgrade --install scroll-monitor ./charts/scroll-monitor \
  --namespace monitoring \
  --create-namespace
```

The default service endpoints assume every component is in the same namespace.
They are configurable under `monitoring.datasources` and
`alloy`.

## Instatus status page

Prometheus supplies core and probe facts to the chart's Python health evaluator.
One process owns evaluation, confirmation windows and durable Instatus delivery;
Grafana consumes metrics for visualization and internal alerts. Runtime policy lives
in `scripts/status_page_health.py`, not in CLI-generated PromQL. Runtime credentials
are scoped component/heartbeat webhooks; no Instatus management API key is needed.

Production profiles keep status-page automation disabled until configured. When
enabled, components default to automatic, requiring reviewed inputs and bindings.
CLI emits deployment parameters and exact cleanup of previous managed Grafana
public publishers. See the two-stage migration in the architecture guide.
See the [configuration and Secret inventory](../../examples/scroll-monitor-configuration.md#instatus-native-webhook-configuration)
and [architecture](../../docs/status-page-architecture.md).

## Dashboard and alert assets

Dashboard ConfigMaps are controlled by `dashboards.bundled.enabled` and are
rendered independently of `grafana.enabled`, allowing an external Grafana
sidecar to discover them.

Application alerts are **Grafana-managed**. The original business, funding,
progress, and log rules are enabled by default. The extended service diagnostic
catalog starts **paused**. A Helm
post-install/post-upgrade Job seeds the rules into **Scroll Monitor Alerts**
using the HTTP API with `X-Disable-Provenance: true`. You can edit and
pause/resume them directly in **Alerting > Alert rules**, without making copies.
This follows Grafana's [editable API provisioning](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/).
The Job adds missing bundled rules and preserves existing expressions, labels,
notification settings, evaluation intervals, and pause state on upgrades. UI
changes and contact points are stored on the Grafana PVC. Deleting a bundled
rule causes it to be recreated on the next upgrade; pause it to keep it disabled.
Changes to bundled defaults apply to new rules; existing rules remain UI-owned.
Known shipped query defects can carry an exact-expression migration. These
migrate only matching managed rules; customized queries remain untouched.

### Workload and resource alert policy (enabled by default)

The chart supplies 35 active workload/resource rules in three configuration sections,
independently of the paused service diagnostic catalog. They use `alert_scope` for
routing and `alert_category` for classification. These are starting thresholds for
this deployment, not universal SLOs; tune them against workload baselines and the
time needed to recover or expand capacity.

| Category | Warning | Critical |
| --- | --- | --- |
| `pod-health` | Any observed restart/abnormal exit/failed non-Job pod; three restarts in 10m; crash-loop evidence with continuously unready pod for 5m; other unready pods for 10m | Controller availability rules below |
| `availability` | Deployment, StatefulSet or DaemonSet has some ready replicas but fewer than desired for 10m | Desired replicas >0 and no available/ready replicas for 2m |
| `job-health` | Job condition Failed=true, without an extra pending period | Classify business-critical job outcomes separately |
| `disk-capacity` | Node filesystem/PVC usage >=80% for 5m; or predicted exhaustion in 4–24h for 30m | Usage >=95% for 5m; or predicted exhaustion in <4h for 5m |
| `disk-inodes` | Inodes >=90% used for 5m | Inodes >=95% used for 5m |
| `disk-health` | — | Persistent node filesystem read-only for 2m |
| `memory` | Node unavailable memory >=90%, container working set/limit >=85%, for 10m | Either ratio >=95% for 5m |
| `cpu` | Node or container CPU >=90%, or container throttled periods >=25%, for 15m | Use service availability, latency and backlog to identify urgent impact |
| `node-pressure` | — | Kubernetes MemoryPressure or DiskPressure for 2m |

Warning and critical bands for the same utilization/forecast metric are mutually
exclusive. A transition starts the new severity's pending period. Capacity and
forecast checks can both fire; notification grouping combines their symptoms.
Pod failures and memory/CPU pressure can also be related; grouping does not infer
root cause or inhibit alerts across different categories.

#### Scope and prerequisites

- `businessPodAlerts`: Pod health in the release namespace, including init containers.
  `podNameRegex` and `excludePodNameRegex` select pods. Controller and final Job
  checks independently use `workloadNameRegex` within the same namespace. Desired
  replicas of zero are excluded. Jobs are excluded from individual pod-failure
  rules; their terminal Failed condition is monitored instead of failed attempts.
  Pod readiness checks exclude terminating pods. Disruptive controller rollouts
  may still cause availability alerts; use an appropriate maintenance mute.
- `diskAlerts`: Node filesystems throughout the collected cluster and PVCs only in
  the release namespace. `excludeMountpointRegex` excludes intentionally read-only
  or unmanaged node mounts; it does not filter PVCs. Memory/pseudo filesystems and
  zero capacities are excluded. Read-only filesystems use their own fault rule.
- `resourceAlerts`: Node memory, CPU and pressure throughout the collected cluster;
  business containers in the release namespace use the pod selectors above.
  Container resource ratios cover regular application/sidecar containers with
  positive limits; absent/zero limits are excluded. Init-container failure remains
  covered by pod-health rules, but init-container limit ratios are not included.

Node metrics require node-exporter, container utilization requires kubelet cAdvisor,
and workload/limit/pressure metrics require kube-state-metrics. The bundled stack
collects these by default. These rules do not depend on kube-prometheus recording
rules, so Grafana and Prometheus fallback use the same expressions.

Node memory uses `1 - MemAvailable / MemTotal`, allowing for reclaimable cache.
Container memory uses working set divided by **that container's limit**, not its
request and not the node's total memory. This is a headroom heuristic, not an exact
OOM predictor; recent OOM exits are additionally covered by pod-health rules.
Container CPU uses a five-minute CPU rate divided by its CPU limit. CPU throttling
is the fraction of scheduling periods with throttling, not percent CPU time lost.
High CPU alone is warning-level, since batch/proof/sync work can legitimately
saturate CPU. Scrape replicas are deduplicated before container/limit joins.

Node disk usage is `100 * (size - available) / size`, including reserved space
unavailable to applications. PVC usage is `100 * used / capacity`. Compute each
kubelet ratio before taking the maximum per PVC to avoid double-counting mounts.
Forecasts use current available bytes divided by the negative six-hour slope;
they require declining free space, <40% available, a sample six hours ago, at
least 60 samples in the window, and unchanged capacity throughout that window.
Expansion suppresses forecasts until a stable history returns. Static capacity
alerts clear as soon as the reported ratio falls below the threshold.

PVC capacity/inode/forecast coverage requires mounted filesystem volumes and a
storage driver exposing the respective kubelet volume statistics. Raw block
volumes, unmounted disks and unsupported metrics need storage-specific collectors.
Missing metrics do not mean healthy storage and do not fire capacity rules; retain
collector/target-health monitoring. External dstack GPU hosts retain their own
optional host rules and configured thresholds.

Single observed restarts/abnormal exits remain warning notifications even after
recovery, with a ten-minute observation window. Successful process exits followed
by a restart count as restarts. Crash-loop alerts also require current unready
status for the pending period, so a recovered pod does not trigger a delayed
crash-loop alert just because a historical event remains in the lookback window.
These are incident alerts, not a durable event stream: scrapes may miss very short
lived pods and multiple failures may be grouped into one incident.

#### Grafana Slack routing

Both production profiles set `businessPodAlerts.contactPoint`,
`diskAlerts.contactPoint` and `resourceAlerts.contactPoint` to `slack-alerts`.
Create that existing Slack contact in Grafana first, or configure the name of
your existing contact. The seed Job validates every referenced Slack contact
before writing rules; webhook credentials are not stored in values.

The seed Job adds three narrowly scoped notification-policy branches, matching
`managed_by=scroll-monitor` and a folder/scope-specific `scroll_monitor_route`
label attached only to these new rules. It reads and preserves the existing root
and all unrelated branches; previously created branches and UI edits are preserved
on later upgrades. The seeder account needs notification-policy read/write access.
Grafana 11 per-rule notification settings require grouping by alert name, so these
rules use policy routing to group by category, severity and resource identity. For example, restart and abnormal-exit symptoms for the same pod
UID share a group. Different PVCs, workloads and container resources remain
separate. Warnings wait 30s to collect related symptoms; critical groups add no
initial grouping delay. Group updates are spaced 5m apart and ongoing incidents
repeat every 4h. Severity is part of the group key so a critical incident does not
wait behind a warning's group interval. The shared Slack template displays all
included alert summaries and their resource labels.

Actual detection also waits for scraping and rule evaluation (normally 1m), plus
the pending period above. Existing Grafana routing, labels and pause state remain
UI-owned on upgrades; existing rules need their category/severity/routing updated
in the UI if created with a previous policy. Rules with an older direct contact
need to switch to policy routing and carry the matching `scroll_monitor_route`
label to use the new grouped policy. Untouched chart-managed expressions
and pending periods reconcile using the seeder's stored baseline. An empty contact
point (chart defaults) inherits Grafana policies. These scoped routes are independent
of the infrastructure Alertmanager's default null receiver. With Grafana alerting
disabled, configure Prometheus/Alertmanager notification receivers separately.
If both systems notify overlapping infrastructure alerts, choose one notification
owner or configure appropriate suppression to avoid duplicate incidents.

Offline tests verify expression behavior and routing configuration, not live Slack
delivery. Validate delivery in the deployed Grafana; mutes and contact failures
still apply. No automatic escalation from warning to a paging system is implied
by a severity label alone.

References: [node-exporter defaults](https://github.com/prometheus/node_exporter/blob/master/docs/node-mixin/config.libsonnet),
[Kubernetes resource limits](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/),
[Job metrics](https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/workload/job-metrics.md).

### Extended service diagnostics (paused by default)

`serviceAlerts.enabled: true` imports 107 additional rules for
withdrawal-processor, tso-service, proof-coordinator, l2-reth nodes, l1-interface,
eth-da-submitter, cubesigner-signer, and fee-oracle. `serviceAlerts.paused: true`
makes every new rule in this catalog start paused. Review and resume individual
rules directly in Grafana; upgrades preserve your choices. Existing business,
balance, progress, and log rules retain their prior defaults.

See [the service alert review](SERVICE_ALERT_REVIEW.md) for the complete catalog,
source commits, thresholds, and implementation prerequisites. In particular,
the complete proof-coordinator metrics endpoint is on an observability branch
that is not yet merged into the reviewed dogeos-core mainline. Rules depending
on that endpoint need an image containing its implementation before activation.
Service metric definitions and exposition examples belong in the service source
repositories; this chart maintains alert queries and their behavior tests.

Prometheus has no rule pause state. The native fallback omits this catalog while
`serviceAlerts.paused` is true. Set it to false explicitly to activate the catalog
in that backend. Changing the value does not overwrite saved Grafana pause states.

The Job uses the Grafana admin Secret (including `grafana.admin.existingSecret`).
Its credentials must match the running Grafana database; changing the Helm
admin password does not reset a password already stored in Grafana. Alternatively,
set `grafanaAlerting.authSecret` to a Secret containing a `token` for a Grafana
service account with permission to create folders and manage alert rules in
organization 1. Use `grafanaAlerting.url` for a custom service URL or subpath.

`grafanaAlerting.enabled: false` restores native Prometheus application rules
when `prometheusRules.enabled` is true. Native rules are also used when bundled
Grafana is disabled. Only one application-rule backend is rendered at a time.
Switching away from Grafana does not delete rules stored in its database: pause
or remove them in the UI before switching to avoid duplicate evaluation.
Kubernetes rules and `kube-prometheus-stack.additionalPrometheusRules` continue
to use Prometheus/Alertmanager and are not editable Grafana rules.

### Slack channels and email recipients

1. Sign in to Grafana as an administrator, open **Alerting > Contact points**,
   and select the built-in **Grafana** Alertmanager.
2. Create a contact point, for example `scroll-ops`. Add a **Slack** integration
   with a webhook URL for the desired channel, or a Slack bot token and channel
   recipient. Add integrations for additional channels as needed.
3. Add an **Email** integration to the same contact point. Enter the recipient
   list separated by semicolons or newlines. Slack and email can receive the same
   alert. Use **Test** for each integration and save the contact point.
4. In **Alerting > Notification policies**, add a policy matching
   `managed_by = scroll-monitor` and select `scroll-ops`, or change the default
   policy's contact point if it should receive all Grafana alerts.

By default, the chart does not provision contact points or notification policies,
so UI-created resources remain editable and Helm upgrades preserve them. The
optional Instatus file configuration above makes only that contact point
file-managed and read-only in the UI; it does not provision notification policies.
Creating a contact point alone does not route application alerts to it; complete
step 4. Existing external
Alertmanager receivers are not copied to Grafana automatically.

Grafana OSS needs an SMTP transport before it can send email. Configure the
transport once at deployment time; manage recipient lists in the UI afterward:

```yaml
grafana:
  smtp:
    existingSecret: grafana-smtp # Existing Secret with keys user and password
  grafana.ini:
    smtp:
      enabled: true
      host: smtp.example.com:587
      from_address: alerts@example.com
      from_name: Scroll Monitor
      startTLS_policy: MandatoryStartTLS
```

Store SMTP credentials in the referenced Kubernetes Secret. Slack credentials
are entered in the Grafana contact point. See the official
[Slack](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-slack/)
and [email](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-email/)
integration documentation. The production values include commented SMTP fields.

### Retired rules

The old six fixed-address `ether_balance_of_*` rules have been removed from both
production profiles: `balance-checker` is no longer deployed, and two of their
thresholds were `< 0`. See [the business alert review](ALERTING_REVIEW.md) for
the rules and source references for the current DogeOS workflow.

### Business and funding alerts

`TSONoRegisteredSigners` and `FeeOracleStale` require an observed signer count
or computation timestamp. Missing metrics instead trigger the warning rules
`TSOSignerMetricMissing` and `FeeOracleMetricMissing` after five minutes. This
distinguishes a missing scrape target or undeployed service from an observed
business failure. Missing telemetry remains actionable and is not replaced by
zero. If fee-oracle is intentionally absent, pause its rules in Grafana.

Upgrading from the previous bundled queries removes their `or absent(...)`
branches only when the stable UID, managed label, datasource UID and exact old
expression match. The seeder also corrects the old description if it is still
unchanged. Pause state, notification settings, group interval, custom
annotations and other operator settings survive. Migration metadata is omitted
from native Prometheus rules. See [the missing-metrics investigation](MISSING_METRICS_REVIEW.md)
for the read-only testnet evidence and deployment prerequisites.

`DogecoinIndexerLag` now alerts when `indexer_dogecoin_last_synced_block`
remains unchanged for two minutes, separately for each namespace, job and instance.
The default `dogecoinIndexerAlerts.jobRegex` selects `l1-interface` and
`withdrawal-processor`; change it if the deployment uses different job names.
No node-tip metric or confirmation configuration is needed. The rule observes
changes to the confirmed processed height, so a confirmation-policy change or
lack of new Dogecoin blocks can also leave it unchanged and trigger the rule.

The query requires two minutes of history, multiple samples in the window, and
a currently present series. It compares the window's left boundary as well as
changes within the window to avoid firing early after a recent height update.
Missing metrics do not count as a stall. Any observed height change, including
a decrease, resets this unchanged-value condition. The rolling window already
provides the two-minute delay, so `for` is `0s`; the one-minute evaluation
interval determines when the condition is next checked.

The name is retained to preserve the existing Grafana UID. Both the original
raw-gap query and the shipped confirmation-adjusted query have exact migrations;
unchanged descriptions and the old default `for: 10m` migrate with them.
Operator-edited queries, pending periods, pause state and notification settings
are preserved. Retain old `confirmationsByJob` / `maxExcessLagBlocks` values during
an upgrade if they were customized: they only reconstruct the old query for
migration and do not affect the new rule. If they are no longer available or the
saved query was edited, update the existing Grafana rule explicitly.

`businessAlerts.enabled` installs the accepted safety, proof-work, WF job,
replay/reorg recovery, signer, TSO progress, and DA publication alerts. The
canonicality observation counter has its own warning rule and is no longer
included in the generic DA failure counter. Time thresholds are configurable
under `businessAlerts`; see [the alert review](ALERTING_REVIEW.md) for the
underlying failure modes.

TSO runtime alerts use the current exported states `proposed`,
`collecting_signatures`, and `collecting_p2pkh`. They detect pending signing work
without completed signing cycles and recurring dispatch failures, timeouts, or
rejections. For exact role-count checks, populate
`businessAlerts.requiredSignersByRole` from the active bridge policy, for example
`{Correctness: 2, Attestation: 3}` only if those are the actual requirements.
There is no universal quorum threshold, so the map defaults to empty. Role names
are case-sensitive and must match `tso_core_registered_signers_by_role`.

Funding alerts are controlled by `balanceMonitoring.enabled`:

| Account | Source | Default low-balance threshold |
| --- | --- | --- |
| Dogecoin fee wallet | `fee_wallet_total_unredeemed_utxo_amount / 1e8`, scoped to the WP job | Less than 100 DOGE; configurable initial threshold |
| Fee oracle | `eth_getBalance` through the service's L2 RPC | Less than 5 native units, expressed as ETH / 1e18 wei |
| Ethereum DA submitter | `eth_getBalance` through the Ethereum RPC | Less than 0.1 ETH |

The fee-wallet gauge already exists in dogeos-core and the bundled dashboards.
The embedded Dogecoin indexer sums canonical, non-orphaned UTXOs with
`redeemed=false`, in satoshis, after successful block processing. It does **not**
deduct WP reservations or certify immediate spendability. The low-balance rule
uses this existing inventory metric. Indexer health/lag and the missing-balance
rule help identify observation failures. Configure `minimumDoge` to the desired
funding reserve.

The bundled account-balance exporter performs only `eth_chainId` and
`eth_getBalance(address, "latest")` calls. It polls every 60 seconds and exposes
Prometheus metrics through its ServiceMonitor. It needs public addresses and RPC
endpoints, with no signing keys or KMS access. Fee oracle must use the L2 chain
where its oracle update transactions are sent; the DA submitter must use the
Ethereum network where it publishes blobs. An optional expected chain ID rejects
observations from the wrong network.

Configuration generators should populate these fields in production values:

The matching `scroll-sdk-cli` `setup prep-charts` command generates this block
from the real service signers in doge-config. It takes the fee-oracle RPC and
chain ID from `config.toml` `general.L2_RPC_ENDPOINT` / `general.CHAIN_ID_L2`,
and the DA RPC and chain ID from doge-config `ethereumDa.submitterRpcUrl` /
`ethereumDa.chainId`. KMS expected addresses must match the canonical account
addresses. Repeated generation refreshes these deployment facts and preserves
operator thresholds. An explicit empty `rpcUrl` with `exporter.envFromSecret`
set remains Secret-owned; addresses and expected chain IDs remain generated.

```yaml
balanceMonitoring:
  enabled: true
  feeWallet:
    minimumDoge: 100
  ethereum:
    feeOracle:
      address: "<FEE_ORACLE_PUBLIC_ADDRESS>"
      rpcUrl: http://l2-rpc:8545
      expectedChainId: "<L2_CHAIN_ID>"
      minimumEth: 5
    ethDaSubmitter:
      address: "<ETH_DA_SUBMITTER_PUBLIC_ADDRESS>"
      rpcUrl: "<ETHEREUM_RPC_URL>"
      expectedChainId: "<ETHEREUM_CHAIN_ID>"
      minimumEth: 0.1
```

The chart maps these fields to the following exporter environment variables:

| Values path under `balanceMonitoring.ethereum` | Environment variable |
| --- | --- |
| `feeOracle.address` | `SCROLL_BALANCE_FEE_ORACLE_ADDRESS` |
| `feeOracle.rpcUrl` | `SCROLL_BALANCE_FEE_ORACLE_RPC_URL` |
| `feeOracle.expectedChainId` | `SCROLL_BALANCE_FEE_ORACLE_EXPECTED_CHAIN_ID` |
| `ethDaSubmitter.address` | `SCROLL_BALANCE_ETH_DA_SUBMITTER_ADDRESS` |
| `ethDaSubmitter.rpcUrl` | `SCROLL_BALANCE_ETH_DA_SUBMITTER_RPC_URL` |
| `ethDaSubmitter.expectedChainId` | `SCROLL_BALANCE_ETH_DA_SUBMITTER_EXPECTED_CHAIN_ID` |

For credentialed RPC URLs, set `balanceMonitoring.exporter.envFromSecret` to an
existing Secret containing these environment-variable keys, and leave the
corresponding values fields empty. Explicit nonempty values take precedence over
the Secret. Restart the exporter after changing a Secret; values changes update
the Deployment automatically. Expected chain IDs accept decimal or `0x` hex.

Missing or invalid addresses/RPCs are reported as collection failures. Failed
collections omit the balance sample, retain the last-success timestamp, and
expose a bounded error reason. They never convert an RPC failure to a zero
balance. Separate alerts detect failed/stale collection and missing monitoring
for either account. The production examples use `<TODO>` address, L2 RPC and
chain-ID placeholders; the generator must replace them before deployment.
Their Sepolia RPC is the user-selected `https://ethereum-sepolia-rpc.publicnode.com`;
the generator must still select the endpoint for the deployment's actual network.

Inspect `scroll_account_balance_collection_status{reason!="none"}` when collection
fails. HTTP 401/403 maps to `rpc_access_denied`, HTTP 429 to `rpc_rate_limited`,
and other HTTP failures to `rpc_http_error`. Transport failures remain
`rpc_unavailable`; JSON-RPC errors use `rpc_error`. Provider response bodies and
credentialed URLs are never exposed in these labels. Increasing the timeout
cannot repair an access denial; configure an RPC endpoint that allows the
exporter's read requests from the deployment network.
The exporter sends `User-Agent: scroll-monitor-account-balances/0.1` to identify
itself. The read-only investigation reproduced Cloudflare 403 / 1010 for Python's
generic User-Agent at both tested public RPCs; the explicit exporter identity
allowed the reads. Switching RPC URLs alone did not repair the generic client.

Low-balance rules have no pending period: they fire on the next one-minute rule
evaluation after a low balance is observed. Notification delivery also follows
the configured notification policy. Helm threshold values initialize new
Grafana rules; existing rules remain editable in Grafana and retain their saved
thresholds on upgrade. For the native Prometheus fallback, Helm updates thresholds
directly. Disable only `balanceMonitoring.exporter.enabled` when another exporter
already supplies the same account metrics and labels.

### Progress alerts

| Rule | Dashboard metric | Coverage |
| --- | --- | --- |
| `ProtocolStateWFTxNumberStalled` | Protocol State WF Tx Number | l1-interface and withdrawal-processor |
| `ReplayHeadWFTxNumberStalled` | Replay Head WF Tx Number | withdrawal-processor |
| `L2BatchHeightStalled` | L2 Batch Height | l1-interface and withdrawal-processor |

These critical alerts fire when the gauge has no positive step in a rolling
60-minute window, sampled every minute. They evaluate independently per
`namespace` and `job`, using the maximum across replicas of each service.
Decreases are not progress, and resumed growth clears the condition at the next
evaluation. An hour of history and a currently present series are required;
there is no additional pending hour. This also alerts during a traffic-free
hour, as it does not depend on a backlog. Missing metrics are not classified as
stalled progress; existing readiness/up alerts cover service availability.

### Error and panic log alerts

`ServiceErrorOrPanickedLogs` checks **every service** whose logs reach Loki in
the Alloy namespace allowlist (`alloy.logs.namespaces`, defaulting to the release
namespace), except the retired `rollup-explorer-backend`. Every minute it counts
JSON `level`/`severity` and logfmt level fields set to `error`, `fatal`, or `panic`,
plus plain error/fatal prefixes and Go/Rust panic headers, ignoring case, over
the last 5 minutes. ANSI colors are removed before matching; timestamp-prefixed
Rust tracing and geth-style `ERROR[...]` lines are supported. One matching line fires
the critical alert with no pending period. Notification delivery also follows
the notification policy's group wait and repeat interval.

Words inside INFO/WARN messages, query expressions, URLs and recovery messages
do not establish an error level. In particular, Grafana and Loki's successful
query logs must not trigger this rule simply because they contain its query.
Unstructured application messages without a recognized error/panic prefix are
not classified by this rule. JSON and logfmt parsing errors on other formats
are removed before counting, so plain-text logs do not fail metric evaluation.

The retired `rollup-last-batch-indexes` exporter module is excluded by its exact
module field. Other exporter errors remain monitored. This chart
has no rollup-explorer-specific metric alerts or dashboard panels. Its HTTP
polling module belonged to the separate `metrics-exporter` chart and is no longer
generated as of its version 0.1.9. This exclusion also covers installations still
running older exporter charts; changing the alert alone does not stop a poller.

Instances are grouped by `namespace`, `service`, `pod`, and `container` so the
notification identifies the affected workload. The same `managed_by =
scroll-monitor` policy routes these alerts to Slack and email. The alert clears
once the matching logs leave the window. Set `grafanaAlerting.logs.enabled:
false` to skip installing it; disabling the Loki datasource also skips it. For
rules already stored in Grafana, pause them in the UI. External services need
their logs shipped to Loki with these labels before this rule can cover them.

On upgrade, the seeding Job replaces the previous broad whole-word query only
when its stable rule UID, `managed_by=scroll-monitor`, datasource UID and exact
previous expression match. It changes only query A's expression, preserving
pause state, notification settings, labels, annotations and group interval.
Operator-customized queries are left intact and need manual review. A paused
rule remains paused after migration. Repeated upgrades do not rewrite it.

Upgrades from native Prometheus application rules remove that chart resource
and seed Grafana rules. If an older installation still mounts alert provisioning
files through custom `grafana.alerting`, a sidecar, or extra volumes, remove that
configuration and restart Grafana first. File-provisioned rules cannot be
unlocked by an API header. Review old rules and any previously made copies in
Grafana before removing duplicates; this Job does not delete unrelated rules.

Validate changes locally with:

```shell
helm lint charts/scroll-monitor
# The test runner uses PyYAML, Helm, and Docker with the pinned Prometheus image.
python3 -m unittest discover -s charts/scroll-monitor/tests -p 'test_*.py'
SCROLL_MONITOR_LOKI_TEST=1 python3 -m unittest discover -s charts/scroll-monitor/tests -p 'test_log_alerts.py'
python3 charts/scroll-monitor/tests/run-alert-tests.py
```

The provisioned datasource UIDs are stable:

- Prometheus: `scroll-prometheus`
- Loki: `scroll-loki`

The bundled DogeOS dashboards are scoped to the services deployed by the
production stack:

| Dashboard coverage | Services | Source |
| --- | --- | --- |
| Native application metrics | `tso-service`, `withdrawal-processor`, `l1-interface`, `eth-da-submitter`, `cubesigner-signer`, `fee-oracle-0` | Prometheus ServiceMonitor or operator-managed scrape target |
| External native application metrics | `attestation-signer` | Operator-managed Prometheus scrape target |
| Exporter-backed application metrics | `dogecoin` | Prometheus metrics exporter |
| Runtime health and logs | All Kubernetes workloads | kube-state-metrics, cAdvisor, and Loki |

Dedicated dashboards cover `attestation-signer`, `proof-coordinator`, and
`cubesigner-signer`. Proof queue depth and age remain sourced from
`withdrawal-processor`, which owns and exports the durable work-item gauges;
the coordinator dashboard does not manufacture a second queue authority.

The signer dashboards and the coordinator's optional application panels select
application metrics through Prometheus `job` and
`instance` labels instead of Kubernetes-only labels. This lets the same panels
work for in-cluster ServiceMonitors and for Attestation Signers on external EC2
hosts. External scrape targets are deliberately not configured by this chart:
add them to the Prometheus instance through an operator-managed scrape config,
using a stable job name such as `attestation-signer`. Prometheus supplies the
`instance` label from each target automatically, so no host address needs to be
committed to Helm values or dashboard JSON.

For example, keep the three external targets in Prometheus' operator-managed
`additionalScrapeConfigs` (or the equivalent configuration managed by your
cluster), outside this chart:

```yaml
- job_name: attestation-signer
  metrics_path: /metrics
  static_configs:
    - targets:
        - <signer-1-host>:<metrics-port>
        - <signer-2-host>:<metrics-port>
        - <signer-3-host>:<metrics-port>
```

Replace the placeholders only in the cluster-managed configuration. Do not add
those host addresses to this chart. After Prometheus reloads successfully, the
Attestation Signer dashboard discovers the job and all three `instance` values
and shows their individual `up` status.

The current dogeos-core metrics initializer exports Rust time histograms ending
in `_seconds` or `_latency_ms` as Prometheus buckets. Latency panels use
`histogram_quantile()` over bucket rates, with seconds and milliseconds kept in
their original units. Non-time distributions still need their exporter checked:
DA batch sizes use per-instance summary quantiles; Attestation Signer artifact
sizes use summaries in the current baseline and buckets in
[dogeos-core #1007](https://github.com/DogeOS69/dogeos-core/pull/1007). The artifact
size panel supports both without combining summary quantiles across instances.

The extended Attestation Signer queue/freshness panels and Proof Coordinator
application panels require #1007 and an image exposing its metrics. They remain
in clearly labelled collapsed rows. The coordinator's always-visible panels use
Kubernetes runtime state and WP-owned queues; Pod readiness is not claim-plane
readiness. Request-lifetime and work-attempt panels describe their different
timing boundaries explicitly.

See [the dashboard source review](DASHBOARD_REVIEW.md) for the per-dashboard
findings, source revisions, verification and remaining rollout requirements.
Service metric exposition examples belong in dogeos-core, not this repository.
The CubeSigner dashboard follows the metric contract merged in dogeos-core
#1009: it shows proof-fallback signs, policy denials, live policy evaluations,
the observed policy rule identity, and the two integrity counters that must
remain zero. CubeSigner deliberately does not register default Node.js process
metrics, so the dashboard does not query them.

All service dashboards provide a Prometheus datasource selector. Kubernetes
service dashboards use namespace variables; the signer/coordinator dashboards
use `job` and `instance` so they also work for external scrape targets.
Embedded indexer queries are additionally constrained to their owning service
job so identically named metrics from `l1-interface` and
`withdrawal-processor` are not merged accidentally.

The dedicated `reth` folder monitors the six Scroll L2 rollup-node workloads
deployed by the production example: two sequencers, two bootnodes, the internal
RPC service, and the public RPC service. Use **Scroll L2 Reth Fleet** for
multi-node health, chain-height divergence, derivation/L1-watcher progress,
resources, and logs. The other five dashboards are intended for a single-pod
drill-down.

The drill-down dashboards are Kubernetes adaptations of the official
`scroll-tech/rollup-node` dashboards at tag `v1.0.7-rc6` (commit
`bc3d5006c41b38cc442ebe92d1afc4285fc43ca1`), matching the rollup-node image
version used by the production values. The import is pinned and reproducible:

```shell
node charts/scroll-monitor/scripts/import-rollup-node-dashboards.mjs
```

Upstream source:
<https://github.com/scroll-tech/rollup-node/tree/v1.0.7-rc6/docker-compose/resource/dashboards>

## Discovery boundaries

Prometheus selects Helm-managed ServiceMonitors in its own namespace. This
keeps discovery scoped to the Scroll deployment namespace without requiring
monitoring-specific labels or version bumps in application charts.

An absent ServiceMonitor produces no `up` series at all; changing the Prometheus
selector cannot create a missing monitor. When an application's chart does not
provide one, `additionalServiceMonitors` can supply a monitor owned by this chart.
The bundled TSO entry is enabled by default because the TSO chart does not
create its own monitor. Disable this supplemental entry when TSO is intentionally
absent or another owner already scrapes it. The default is:

```yaml
additionalServiceMonitors:
  tso:
    enabled: true
```

The monitor selects the `tso-service` application/instance labels in the Helm
release namespace and scrapes `/metrics` every 30 seconds. Override `selector`
and `endpoints` for different service labels or named ports, or add other map
entries with the same structure. Ensure exactly one monitor owns each endpoint.
For an external Prometheus, its selector must include these monitors' labels
and namespace. Verify `up{job="tso-service"}` and
`tso_core_registered_signers_count` after an authorized deployment.

Alloy limits pod-log discovery to the release namespace by default. Set
`alloy.logs.namespaces` for an explicit namespace allowlist and
`alloy.logs.podLabels` to require matching pod labels.

## Required cluster services

The chart does not install an ingress controller or a dynamic volume
provisioner. The configured Grafana ingress requires nginx, and persistent
components require a usable StorageClass.

## Public health rules and collection coverage

See [the public status health design](../../docs/status-page-health-rules.md) for
the eight implemented component contracts, configurable failure/recovery windows,
missing-data handling, source inventory, and activation tests. Existing internal alert rules are not
implicitly suitable for public status or automatic recovery.

PodMonitor discovery now follows ServiceMonitor discovery: Helm instance labels
in the release namespace. This includes Blockscout's existing frontend
`/node-api/metrics` PodMonitor, which has no `release=scroll-monitor` label.
The eager-materializer production example enables its application-owned
ServiceMonitor; no supplemental duplicate is added here. These collection fixes
provide telemetry, not an end-to-end proof of user-facing availability.

The inspected proof-coordinator application revision has no production metrics
endpoint. Keep its diagnostic rules paused until a supporting application image
and scrape target exist; a ServiceMonitor cannot add an application endpoint.
External public RPC/browser probes and monitor-loss detection remain prerequisites
for reliable public automation. None of this requires exposing private monitoring.


Component publication generation is available through `statusPage.publication`.
Each component defaults to automatic and may explicitly use manual or observe
mode. See [the publication configuration guide](../../docs/status-page-publication.md)
for the health-expression contract, private component bindings, evaluator publication,
verified recovery, private probe collection and independent heartbeat. No public rule is activated merely by
installing the default values.

## Dstack and GPU monitoring

Internal controller alerts, controller logs and ServiceMonitor discovery in
`dstack-system` are enabled by default. Apply the CLI-generated
`scroll-monitor-dstack.yaml` after production values to select a different
controller namespace. Set `dstack.enabled: false` to disable this integration. The Dstack/GPU dashboard is included with bundled dashboards,
even when dstack monitoring is disabled; unconnected panels show No data.
See [the integration guide](../../examples/dstack-monitoring/README.md).
This does not configure public status-page routing.

## Bridge health metrics adapter

The optional `bridgeHealth` adapter consumes core signing snapshot v1 through
Prometheus, with explicit target completeness and freshness checks. It supplies
read-only signing evidence and does not publish a global bridge status. See
[configuration, contract and tests](BRIDGE_HEALTH_ADAPTER.md).

### Core PR #1358 compatibility

Chart `0.1.41-dogeos` targets the core metrics contract at `7e3ee2877`.
Cached WP/TSO facts are filtered by source validity and success time before use;
removed historical totals and terminal inventory are no longer queried. See
[DASHBOARD_REVIEW.md](DASHBOARD_REVIEW.md#pr-1358-snapshot-contract-2026-10-02)
for the source mapping. The signing adapter still consumes schema v1 from
Prometheus. No new URL, credential or scroll-sdk-cli parameter is needed.

Run the semantic tests as well as the chart and Python checks:

```sh
SCROLL_STATUS_RUNTIME_TEST=1 python3 -m unittest discover -s charts/scroll-monitor/tests
python3 charts/scroll-monitor/tests/run-alert-tests.py
python3 charts/scroll-monitor/tests/check_dstack_alerts.py
helm lint charts/scroll-monitor
```
