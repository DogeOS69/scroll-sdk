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

The chart does not provision contact points or notification policies, so they
remain editable and Helm upgrades preserve them. Creating a contact point alone
does not route application alerts to it; complete step 4. Existing external
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
for either account. The production examples intentionally use `<TODO>` address
and Ethereum RPC placeholders; the generator must replace them before deployment.

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
namespace). Every minute it counts log lines containing the whole word `ERROR`
or `panicked`, ignoring case, over the last 5 minutes. One matching line fires
the critical alert with no pending period. Notification delivery also follows
the notification policy's group wait and repeat interval.

Instances are grouped by `namespace`, `service`, `pod`, and `container` so the
notification identifies the affected workload. The same `managed_by =
scroll-monitor` policy routes these alerts to Slack and email. The alert clears
once the matching logs leave the window. Set `grafanaAlerting.logs.enabled:
false` to skip installing it; disabling the Loki datasource also skips it. For
rules already stored in Grafana, pause them in the UI. External services need
their logs shipped to Loki with these labels before this rule can cover them.

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
python3 charts/scroll-monitor/tests/run-alert-tests.py
```

The provisioned datasource UIDs are stable:

- Prometheus: `scroll-prometheus`
- Loki: `scroll-loki`

The bundled DogeOS dashboards are scoped to the services deployed by the
production stack:

| Dashboard coverage | Services | Source |
| --- | --- | --- |
| Native application metrics | `tso-service`, `withdrawal-processor`, `l1-interface`, `proof-coordinator`, `eth-da-submitter`, `cubesigner-signer`, `fee-oracle-0` | Prometheus ServiceMonitor or operator-managed scrape target |
| External native application metrics | `attestation-signer` | Operator-managed Prometheus scrape target |
| Exporter-backed application metrics | `dogecoin` | Prometheus metrics exporter |
| Runtime health and logs | All Kubernetes workloads | kube-state-metrics, cAdvisor, and Loki |

Dedicated dashboards cover `attestation-signer`, `proof-coordinator`, and
`cubesigner-signer`. Proof queue depth and age remain sourced from
`withdrawal-processor`, which owns and exports the durable work-item gauges;
the coordinator dashboard does not manufacture a second queue authority.

The three dashboards select application metrics through Prometheus `job` and
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

The Attestation Signer exports latency and payload-size observations as
Prometheus summaries. Its dashboard reads the exported `quantile` series
directly and preserves the `instance` label because summary quantiles cannot be
aggregated across signers. The `_sum / _count` series remain available for
average calculations. The CubeSigner and coordinator dashboards use their own
native metric types. The dashboards also expose bounded request, worker,
signing, callback, replay, and policy outcome counters as rates so throughput
and failure-volume changes remain visible.
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

Alloy limits pod-log discovery to the release namespace by default. Set
`alloy.logs.namespaces` for an explicit namespace allowlist and
`alloy.logs.podLabels` to require matching pod labels.

## Required cluster services

The chart does not install an ingress controller or a dynamic volume
provisioner. The configured Grafana ingress requires nginx, and persistent
components require a usable StorageClass.
