# scroll-monitor configuration generation contract

Use [values/scroll-monitor-production.yaml](values/scroll-monitor-production.yaml)
as the operator-facing input/output example for the configuration generator.
The matching chart production profile exposes the same monitoring fields.
Replace `<TODO>` with deployment facts; do not copy testnet addresses, provider
URLs or chain IDs from an investigation report into generic generated values.
The Sepolia example explicitly uses the user-selected
`https://ethereum-sepolia-rpc.publicnode.com`, matching
`config.toml.example`'s `ethereumDa.submitterRpcUrl`. Other deployments must
generate their own network's URL and chain ID.

## Default Slack destination

Grafana itself creates the initial `grafana-default-email` contact point and
notification policy. Installing a Slack contact point alone does not change that
policy. The chart's existing `seed-grafana-alerts.py` Job now bootstraps the
operator-configured default destination before importing rules and scoped routes:

```yaml
grafanaAlerting:
  defaultContactPoint:
    enabled: true
    name: slack-alerts
  notificationTemplate:
    enabled: true
    bindDefaultContactPoint: true
```

The example contains only configuration; the script and Job live in the chart.
No Slack webhook or Slack Secret is required to install. The seeder creates an
empty, UI-editable `slack-alerts` contact point and switches only the built-in
`grafana-default-email` default to it. An empty destination sends no messages;
alerts still evaluate and remain visible in Grafana. No invalid Slack integration
or dummy webhook is created.

To enable delivery, open **Alerting > Contact points**, edit **slack-alerts**,
and add a **Slack** integration with the real incoming webhook URL. Save it,
verify the default receiver in **Notification policies**, and use **Test** to
check delivery. On the next chart upgrade, blank Title and Text Body fields
automatically reference `scroll-monitor.slack.title` and `scroll-monitor.slack.text`.
To bind them immediately, enter `{{ template "scroll-monitor.slack.title" . }}`
and `{{ template "scroll-monitor.slack.text" . }}` in those fields.
Store the webhook in the UI, not in values or Git. Notifications omitted while
the destination was empty are not a replayable message queue.

Repeated upgrades preserve webhook secrets, custom nonblank Title/Text Body,
UI-edited templates, child policies, and custom default receivers. Untouched
chart templates follow chart upgrades. Set
`notificationTemplate.bindDefaultContactPoint: false` to opt out of new bindings.
If an existing installation already
uses a custom default, change that default in the UI when Slack should replace it.
Set `defaultContactPoint.enabled: false` when another provisioning system owns
these resources. The seeder reuses its existing Grafana credentials and targets
organization 1; the full-configuration UI API requires organization-admin access.
It never logs configuration payloads or credentials.

The example and chart production profile route Pod, disk and resource alerts to
`slack-alerts` with category/resource/severity grouping. The seeder accepts its
own empty bootstrap destination before a Slack integration exists; other named
Slack destinations still require an existing Slack integration. Existing rule
labels and routes remain UI-owned. The separate Prometheus Alertmanager is
configured independently as described below.

## Public health and collection templates

The [health-rule design](../docs/status-page-health-rules.md) defines failure,
recovery, missing-data behavior and evidence requirements for all eight public
components. Thresholds there are proposed operating values, not deployed alerts.
Keep each chain's working directory and Grafana independent.

The production templates expose namespace-scoped `podMonitorSelector` and
`podMonitorNamespaceSelector` under `kube-prometheus-stack.prometheus.prometheusSpec`.
They include Blockscout's application-owned frontend PodMonitor without opening
cross-namespace discovery. Eager materializer's own production values enable its
ServiceMonitor; install only for deployments that actually use that optional
service. Do not add duplicate supplemental monitors in scroll-monitor.

## Instatus native webhook configuration

The runtime integration uses **Grafana component alerts → delivery verifier →
Instatus's native Grafana webhook**. The verifier confirms continuous recovery
and keeps a durable delivery journal. No public Prometheus endpoint or numeric
series upload is added. The management API key belongs only to the explicit CLI
planning/application step; it is never injected into the chart.

Enable the `statusPage` block in the chart production profile or
[operator example](values/scroll-monitor-production.yaml), set `environment` to this directory’s `mainnet`, `testnet`, or `devnet`,
and run `scrollsdk setup status-page` (offline). `setup prep-charts` also generates
it during normal chart preparation. The resulting values contain the public
component catalog, native `grafana.envValueFrom` and `grafana.alerting` fields.
All three deployments target workspace `6wxpx` and page `dogeos`, using the
Mainnet / Testnet / Devnet component groups. Initialize each group with a Public RPC
component in the Instatus console once. Page branding is shared; endpoints and
webhooks remain deployment-specific. Keep shared name/branding settings identical.
Defaults remain disabled, with no required Secret or public notification route.
The commented native blocks below `grafana` remain a manual alternative when
`statusPage.enabled=false`; do not uncomment them for automatic generation.

Use `scrollsdk setup status-page --plan` for a read-only remote comparison and
`--apply` to create/reconcile Instatus resources. Both read `INSTATUS_API_KEY`
from the command environment. See the complete
[automation contract and field ownership](../docs/status-page-automation.md)
for page creation, input paths, ID persistence, failure recovery and teardown.
First webhook initialization uses `--plan --create-webhook`, then
`--apply --create-webhook`. The URL and a Kubernetes Secret artifact are saved
privately under `secrets/status-page/`; ordinary `--apply` reuses
that binding. Apply the Secret separately to the existing Grafana namespace.

### Field ownership

| Field / value | Source | Handling |
| --- | --- | --- |
| Webhook URL (Secret value only) | Returned by Instatus's integration-create API via CLI `--apply --create-webhook`, or generated in Apps → Grafana | Environment-specific credential; provision outside Git and Helm values. Do not construct it from a page ID or reuse the REST API key. |
| `grafana.envValueFrom.INSTATUS_GRAFANA_WEBHOOK_URL.secretKeyRef.name` | Operator supplies an existing Secret in Grafana's namespace | Example convention: `instatus-grafana-webhook`; preserve on regeneration. |
| `…secretKeyRef.key` | Operator supplies the matching Secret data key | Example convention: `url`; preserve on regeneration. |
| `grafana.alerting.instatus-contact-points.yaml` | Local provisioning filename | Stable convention, not assigned by Instatus. |
| `apiVersion`, receiver `type`, `httpMethod` | Integration protocol | Keep `1`, `webhook`, and `POST`. |
| `contactPoints[].orgId` | Actual Grafana organization containing the rules | Default `1`, matching bundled alert seeding; customize if using a different organization. |
| Contact point `name` / receiver `uid` | Operator naming convention | Examples: `instatus-public` / `instatus-public-webhook`; choose unused identities and keep stable. Future policies reference the name. |
| Receiver `disableResolveMessage` | Recovery behavior | Keep `false` to send recovery notifications. |
| Receiver `settings.url` | Grafana environment interpolation | Keep literal `$INSTATUS_GRAFANA_WEBHOOK_URL`; Grafana resolves it at startup from the Secret-backed environment. |
| Public alert routing and Instatus component/incident templates | Later operational configuration | Not prefilled or automatically enabled. Do not route all `managed_by=scroll-monitor` alerts to the public page. |

The CLI dynamically derives URLs and chain identity from the selected deployment.
Instatus supplies page/component IDs and the integration webhook URL. Secret
names, data keys and Grafana organization are deployment inputs; protocol values
and default contact-point identities are stable conventions. API key and webhook
URL values must remain outside production YAML.

### Setup and ownership

1. Initialize the intended environment's Grafana integration with CLI
   `--apply --create-webhook`, or create it in the Instatus dashboard and adopt
   its URL using `--apply --webhook-url-file /private/instatus-grafana.url`. Store
   its generated URL through the private Secret artifact or existing secret-management workflow as key `url`
   in Secret `instatus-grafana-webhook` in Grafana's namespace (or use your own
   matching names). The complete URL is a credential.
2. Generate values with `scrollsdk setup status-page`, review/apply the Instatus
   metadata separately, and deploy the chart through the existing Helm workflow.
   The runtime change provisions a contact point only. Leave notification routes unconfigured
   until the public alert selection and payload review are complete.
3. Later, configure explicit notification policies or rule routing in Grafana,
   plus the target component and incident behavior in Instatus. Keep the existing
   internal Slack/email routes. Do not replace the entire notification policy
   tree just to add the public destination.
4. Validate firing and recovery on a separate test status page before enabling
   production routing. Grafana's **Test** sends an actual webhook and can trigger
   a real incident; it is not a dry-run.

File-provisioned contact points are read-only in the Grafana UI. Alternatively,
leave both YAML blocks commented and create the webhook contact point entirely
in **Alerting → Contact points**, entering the actual URL there. UI-managed
configuration persists in the existing Grafana database/PVC. Choose one owner for
a contact point; do not import over an existing UI-created resource with the same
identity. The `$INSTATUS_GRAFANA_WEBHOOK_URL` placeholder is for file provisioning,
not a promise of environment expansion in the UI.

On rotation, update the Secret and restart the Grafana Pod to refresh its
environment and provisioning. Reloading provisioning files alone cannot refresh
a running process's environment. The actual URL stays out of Helm-rendered
ConfigMaps, but Grafana's runtime database and authorized contact-point readers
may expose it; control access to Grafana and its backups accordingly.

### Optional Alertmanager path

If selected infrastructure alerts need to become public later, use Instatus's
separate **Prometheus** integration webhook in the existing Alertmanager. This is
an alternative source, not a relay after Grafana. Mount a separate existing
Secret through `kube-prometheus-stack.alertmanager.alertmanagerSpec.secrets`, and
use a receiver's `webhook_configs[].url_file` with
`/etc/alertmanager/secrets/<secret-name>/<key>` and `send_resolved: true`.
Append a selective child route and receiver to the existing configuration;
preserve internal routing and avoid publishing the same event from both engines.
This optional route is not enabled in the production examples.

Only outbound HTTPS to the actual generated webhook host is needed. Do not assume
it is the REST API host `api.instatus.com`. Instatus receives no internal
Prometheus/Grafana credential, and no public monitoring ingress is added.
See the [architecture](../docs/status-page-architecture.md),
[Instatus Grafana integration](https://instatus.com/help/integrations/grafana),
[Instatus Prometheus integration](https://instatus.com/help/integrations/prometheus),
and [Grafana file provisioning](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/).

## Account monitoring inputs

The existing `scrollsdk setup prep-charts` balance reconciler consumes the
canonical signer configuration, `config.toml` and doge-config. The mapping is:

| Output field | User/configuration input |
| --- | --- |
| `balanceMonitoring.ethereum.feeOracle.address` | Canonical public address of the managed `l2GasOracleSender` signer. For KMS, use its validated expected address. |
| `balanceMonitoring.ethereum.feeOracle.rpcUrl` | `config.toml` `general.L2_RPC_ENDPOINT`, reachable from the exporter Pod. |
| `balanceMonitoring.ethereum.feeOracle.expectedChainId` | `config.toml` `general.CHAIN_ID_L2`, serialized as a string. |
| `balanceMonitoring.ethereum.ethDaSubmitter.address` | Canonical public address of the managed `l1CommitSender` signer. For KMS, use its validated expected address. |
| `balanceMonitoring.ethereum.ethDaSubmitter.rpcUrl` | doge-config `ethereumDa.submitterRpcUrl`. It must allow `eth_chainId` and `eth_getBalance` from the deployment network. |
| `balanceMonitoring.ethereum.ethDaSubmitter.expectedChainId` | doge-config `ethereumDa.chainId`, serialized as a string. |
| `balanceMonitoring.ethereum.*.minimumEth` | Operator funding thresholds; preserve on regeneration. |
| `balanceMonitoring.feeWallet.minimumDoge` / `jobRegex` | Operator funding threshold and the generated withdrawal-processor Prometheus job selection. |
| `balanceMonitoring.exporter.envFromSecret` | User-supplied existing Secret name, when RPC URLs require credentials. |

Do not assume that a publicly reachable RPC permits automated balance reads.
Verify the two read methods and chain ID using the deployment's network and
authentication. An HTTP 403 is an access failure; it does not imply zero funds.
No private keys or signing permissions are needed by the exporter.
The bundled exporter identifies itself with
`User-Agent: scroll-monitor-account-balances/0.1`; both the previous Sentio
endpoint and PublicNode rejected the generic Python User-Agent during the
read-only testnet investigation. Deploy the exporter fix with the URL change.

With `exporter.envFromSecret` set, an **explicit empty** `rpcUrl: ""` delegates
that account's URL to the Secret. The existing generator preserves this choice;
it refreshes generated addresses and chain IDs and preserves operator thresholds.
Nonempty values override the Secret, including an unreplaced `<TODO>`.

For example, the user supplies the Secret name and creates its contents through
their secret-management workflow; the generated values contain only the reference:

```yaml
balanceMonitoring:
  ethereum:
    feeOracle:
      address: "<TODO>" # Generated from l2GasOracleSender.
      rpcUrl: "" # Secret-owned.
      expectedChainId: "<TODO>" # Generated L2 chain ID.
    ethDaSubmitter:
      address: "<TODO>" # Generated from l1CommitSender.
      rpcUrl: "" # Secret-owned.
      expectedChainId: "<TODO>" # Generated Ethereum chain ID.
  exporter:
    envFromSecret: "<TODO>" # Existing Secret name, supplied by the user.
```

The Secret keys are `SCROLL_BALANCE_FEE_ORACLE_RPC_URL` and
`SCROLL_BALANCE_ETH_DA_SUBMITTER_RPC_URL`. Supply only the keys delegated to it.
Secret values must not be committed to the example. The example also makes
`intervalSeconds: 60` and `rpcTimeoutSeconds: 10` explicit; valid chart ranges
are 1–120 and 1–15 seconds respectively.

## Metrics discovery inputs

`additionalServiceMonitors.tso` is enabled by default and owned by scroll-monitor.
The TSO production profiles leave the application-owned ServiceMonitor disabled.
No opt-in is required for the standard TSO Service in the release namespace.
If another chart already owns the scrape, set this supplemental monitor to false
so each endpoint has one owner. Its selector must match the Service labels and
its port is the named Service port `http`, not the numeric port `3000`.

A ServiceMonitor does not override NetworkPolicy. On deployments that enforce
TSO's direct-sign isolation, arrange a metrics-only listener or proxy rather than
opening the shared port (which also serves `/propose`) without reviewing access.

## Dogecoin indexer stall monitoring

The example exposes `dogecoinIndexerAlerts.jobRegex`, defaulting to
`l1-interface|withdrawal-processor`. The configuration generator must match the
actual Prometheus job names. No confirmation depth, Dogecoin node address or
RPC URL is required for this rule: it uses each service's exported
`indexer_dogecoin_last_synced_block` directly.

The rule alerts when the value remains unchanged for two minutes, independently
per namespace, job and instance. It requires current and historical samples;
missing telemetry is not treated as an unchanged height. There is no additional
pending period beyond the two-minute observation window.

Do not generate `dogecoinIndexerAlerts.confirmationsByJob` or
`dogecoinIndexerAlerts.maxExcessLagBlocks` for new installations. When upgrading
an installation with customized legacy values, retain those values for the
upgrade so the seeder can exactly recognize its old saved Grafana query. They
are used only for migration. The old default ten-minute pending period is
removed if unchanged; operator-edited pending periods remain under UI control.

An absent `up` series can mean no ServiceMonitor was selected. It is different
from `up == 0`, which means a discovered endpoint failed its scrape. Check both
target discovery and the native metric before relying on an alert.

## Intentionally absent Fee Oracle

Disable its balance collection and explicitly pause the two service-health rules:

```yaml
balanceMonitoring:
  ethereum:
    feeOracle:
      enabled: false
grafanaAlerting:
  pauseRules:
    FeeOracleStale: true
    FeeOracleMetricMissing: true
```

A disabled balance account is not queried and exports no account series. Its
low-balance and missing-balance-monitor rules are automatically paused as well.
`pauseRules` is an explicit override, applied to both new and existing
scroll-monitor-managed Grafana rules. Set an entry to false to resume through
values, or remove it to return pause control to the UI. Removing an override
preserves the current pause state; it does not implicitly resume a rule.
Prometheus fallback omits explicitly paused rules because it has no pause state.
Disabling a balance account alone does not declare the service absent.

## Grafana rule updates and preview

The seeder records hashes of the last chart-managed expression, pending period,
and annotations in the internal `__scroll_monitor_last_applied__` annotation.
An unchanged field follows new values on subsequent upgrades. A field edited in
Grafana is preserved and a `DRIFT <rule>: ...` message identifies the difference.
Pause state, notification routing, labels, title and group interval remain under
UI control, except for explicit `pauseRules` entries.

Existing installations have no baseline. The first upgrade migrates exact known
legacy expressions, adopts fields already matching the desired configuration,
and reports other differences without guessing whether they were UI edits.
Resolve a legacy difference in Grafana to match the desired field; the following
upgrade records the baseline. A future values change can then update it safely.
The seeder does not delete user rules or rules removed from the chart.

Render locally and extract the seed inputs (no Kubernetes access):

```bash
helm template scroll-monitor ./charts/scroll-monitor -n default \
  -f /path/to/scroll-monitor-production.yaml > /tmp/scroll-monitor-rendered.yaml
python3 - <<'PYCODE'
import pathlib, yaml
for doc in yaml.safe_load_all(pathlib.Path('/tmp/scroll-monitor-rendered.yaml').read_text()):
    if doc and doc['kind'] == 'ConfigMap' and doc['metadata']['name'] == 'scroll-monitor-grafana-alerts':
        pathlib.Path('/tmp/scroll-monitor-rules.json').write_text(doc['data']['rules.json'])
PYCODE
```

To compare with a Grafana server, provide `GRAFANA_URL` and a read-capable
`GRAFANA_TOKEN` through the environment, then run:

```bash
python3 charts/scroll-monitor/scripts/seed-grafana-alerts.py \
  /tmp/scroll-monitor-rules.json --dry-run
```

This preview performs GET requests only, reports planned additions/updates and
conflicts, and does not create folders, unlock groups or write rules. The Helm
post-install/post-upgrade Job performs the actual updates when you apply.

## EKS control-plane metrics

The production example and matching chart production profile default to EKS
1.28 or later. They enable `eksControlPlane.enabled`, disable the scheduler and
controller-manager Pod-based ServiceMonitors, and keep the upstream
alert/recording rules enabled. No additional EKS overlay is needed with these
production profiles. The base chart remains provider-neutral; deployments using
only base values can merge `charts/scroll-monitor/values/eks.yaml` to opt in.

For self-managed Kubernetes, override all three settings together:

```yaml
eksControlPlane:
  enabled: false
kube-prometheus-stack:
  kubeScheduler:
    serviceMonitor:
      enabled: true
  kubeControllerManager:
    serviceMonitor:
      enabled: true
```

Existing deployment values must also adopt the EKS settings; updating an example
does not change an installed Helm release.

The generated ClusterRole grants only `get` on `ksh/metrics` and `kcm/metrics` in
`metrics.eks.amazonaws.com`, bound to the actual Prometheus ServiceAccount.
TLS validates the mounted CA and `kubernetes.default.svc` server name.

The ServiceMonitor discovers the `default/kubernetes` Service even when the
monitoring release is in another namespace, and sets the jobs to
`kube-scheduler` / `kube-controller-manager` for the retained upstream rules.
Do not turn off the top-level component `enabled` switches: those also remove
upstream rules. Helm validation rejects duplicate old scrapers in this profile.
See [AWS control-plane metrics](https://docs.aws.amazon.com/eks/latest/userguide/view-raw-metrics.html).

## Infrastructure notification routing

Grafana contact points apply to Grafana-managed application rules. For the
shared Slack message format and alert wording rules, see
[alert notifications](../docs/alert-notifications.md). The bundled
Prometheus infrastructure rules use the bundled Alertmanager, whose upstream
default receiver is `null`. Chart installation does not invent a notification
destination. Helm NOTES flags this configuration; production installations that
require delivery should set `infrastructureAlerts.requireReceiver: true`.

For a webhook receiver, use the following example with a pre-existing Secret
`infrastructure-webhook` containing a `url` key. Supply your actual receiver URL;
never commit it in values when it contains a credential:

```yaml
infrastructureAlerts:
  requireReceiver: true
kube-prometheus-stack:
  alertmanager:
    alertmanagerSpec:
      secrets: [infrastructure-webhook]
    config:
      route:
        receiver: infrastructure
        group_by: [namespace, alertname]
        routes:
          - receiver: "null"
            matchers: ['alertname="Watchdog"']
      receivers:
        - name: "null"
        - name: infrastructure
          webhook_configs:
            - url_file: /etc/alertmanager/secrets/infrastructure-webhook/url
              send_resolved: true
```

This strict check verifies an inline default receiver has an integration; it
cannot establish external delivery or inspect an existing Alertmanager Secret.
If using `alertmanagerSpec.useExistingSecret`, validate that Secret and receiver
separately. SMTP and other channels use the upstream Alertmanager configuration.
After applying, verify routing and delivery with your configured notification
channel; a successful Helm upgrade alone is not delivery confirmation.

## Component publication v2

See [component publication controls](../docs/status-page-publication.md) for independent manual/observe/automatic modes, one integration per automatic component, generated Secret references, and migration from the legacy bootstrap described above. Production templates default to automatic with built-in health rules; missing required inputs report not ready. Verified recovery is enabled in the new examples; direct legacy delivery retains manual recovery. External probes and business deadlines must be configured per deployment.

## Select the independent Alertmanager

Apply `values/scroll-monitor-alertmanager.yaml` after the environment values.
Metric rules then run in Prometheus; Grafana retains LogQL evaluation and forwards
notifications to the independent Alertmanager. See
[the migration guide](../docs/alertmanager-backend.md) before switching an existing
installation. Preserve UI pause states and edited rules during the cutover.
