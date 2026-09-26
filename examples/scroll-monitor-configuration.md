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

`additionalServiceMonitors.tso` is a supplemental monitor owned by scroll-monitor.
The generator/operator must select exactly one owner for TSO scraping:

- When generated TSO values enable their own ServiceMonitor, leave the
  supplemental entry disabled. This is the current TSO production example.
- For a legacy TSO deployment without its own monitor, set
  `additionalServiceMonitors.tso.enabled: true` in scroll-monitor values.
  Populate `selector.matchLabels` from the actual generated Service labels and
  `endpoints[].port` from the **named Service port**, normally `http`.
  The normal path is `/metrics`, with a 30-second interval and 10-second timeout.
- Keep the entry disabled if TSO is not part of the deployment. Supplemental
  monitors discover Services only in the scroll-monitor release namespace.

The existing balance reconciler does not infer this new ServiceMonitor ownership
decision. The explicit example supplies the field contract for the generator
and operator to retain/populate; no separate CLI repository was changed here.

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

If fee-oracle is intentionally not deployed, review and pause its Grafana rules,
including funding rules for any account that is no longer used. Missing metrics
produce warning rules rather than false claims of zero signers or stale oracle
values. The chart does not silently turn off monitoring when a service disappears.
Existing Grafana rules retain user edits and pause choices on upgrades, apart
from exact migrations of known shipped query defects.

## Component publication v2

See [component publication controls](../docs/status-page-publication.md) for independent manual/observe/automatic modes, one integration per automatic component, generated Secret references, and migration from the legacy bootstrap described above. Production templates default to observe with built-in health rules; missing required inputs report not ready. Verified recovery is enabled in the new examples; direct legacy delivery retains manual recovery. External probes and business deadlines must be configured per deployment.
