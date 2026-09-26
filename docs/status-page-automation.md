# Status-page configuration automation

The SDK template and `scroll-sdk-cli` share the `statusPage` contract in
[`examples/values/scroll-monitor-production.yaml`](../examples/values/scroll-monitor-production.yaml).
The chart defaults and chart production profile expose the same inputs.
This first rollout is **DogeOS Testnet only**, with eight components and no L2Scan.
Each deployment directory belongs to exactly one network. Other environments
use their own deployment directories.

## Generate, inspect, apply

Run these commands from the deployment directory, using a CLI build containing
`setup status-page`:

```bash
# Offline: read this deployment's files and update local monitor values.
scrollsdk setup status-page

# Optional: read Instatus and print create/update/unchanged actions.
# Does not modify local files or Instatus; requires INSTATUS_API_KEY in the environment.
scrollsdk setup status-page --plan

# Explicit remote mutation; creates or reconciles the selected page and components.
scrollsdk setup status-page --apply
```

All modes regenerate the desired catalog in memory from current inputs before
using it. Default generation writes only the selected monitor values file.
`--plan` is read-only. `--apply` saves generated values, reconciles Instatus, and
persists returned page/component IDs after each successful operation.
`--plan` and `--apply` are mutually exclusive. `--json` emits structured results.

Paths can be selected explicitly:

```bash
scrollsdk setup status-page --deployment-dir /path/to/deployment \
  --config config.toml --values values/scroll-monitor-production-0.yaml
```

`--config` and `--values` resolve relative to `--deployment-dir`. Source filenames
in `statusPage.sources` resolve relative to the selected monitor file's directory.
This also supports layouts with `frontends-production.yaml` directly in the
working directory. Source files must remain inside that values directory.

`scrollsdk setup prep-charts` also generates this configuration when
`statusPage.enabled=true`, including numbered monitor values. It processes the
source charts before monitor values so the catalog uses their newly generated
ingress hosts. It never contacts Instatus. Older deployments without a
`statusPage` block retain their existing behavior.

Neither command deploys Helm or Kubernetes Secrets. Apply the generated monitor
values through the deployment's existing Helm workflow. The chart validates the
generation contract, renders the public catalog in a ConfigMap, and delegates
contact-point provisioning to the existing Grafana chart. No publisher workload
or periodic management API process is added.

## Inputs and ownership

| Field | Owner / source | Behavior |
| --- | --- | --- |
| `statusPage.enabled` | Operator, default `false` | Explicitly opt into generation and chart validation. |
| `statusPage.environment` | Operator | `testnet`, `mainnet`, or `devnet`. Never inferred from a hostname or Dogecoin's network. First public deployment uses `testnet`. |
| Network name / chain ID | `config.toml`: `general.CHAIN_NAME_L2`, `general.CHAIN_ID_L2` | Generated page name includes the environment when the chain name does not already include it. |
| `sources.frontends` | Selected deployment frontend values | Read `ingress.main.hosts[].host`; append `sources.bridgePath` (default `/bridge`). |
| `sources.publicRpc` | Selected **enabled** public RPC values | Read all HTTP hosts and enabled WebSocket hosts. Default filename is `l2-reth-rpc-public-production.yaml`; select the actual release, including old/numbered layouts if applicable. |
| `sources.blockscout` | Selected deployment Blockscout values | Read `blockscout-stack.frontend.ingress.hostname`; L2Scan is excluded. |
| `sources.scheme` | Operator, default `https` | Actual external protocol; WebSocket uses `wss` for HTTPS. It is explicit because TLS may terminate upstream of ingress. |
| `grafana.orgId` | Organization in **scroll-monitor's Grafana** | Default `1`; use the organization that owns the rules. |
| `grafana.contactPointName` / `receiverUid` | Local naming conventions | Defaults `instatus-public` / `instatus-public-webhook`; reserve unused, stable identities. |
| `grafana.webhookSecretRef.name` / `.key` | Target Kubernetes Secret | Defaults `instatus-grafana-webhook` / `url`; also used by the CLI's private Secret artifact. Only references are written to values. |
| `instatus.pageId` | Instatus | Set an existing dedicated page ID, or leave empty to find/create the fixed environment subdomain. Saved after successful apply. |
| `instatus.subdomain` | CLI, fixed by environment | `mainnet` → `dogeos`, `testnet` → `dogeos-testnet`, `devnet` → `dogeos-devnet`. Leave empty in the input example; the CLI fills it. Existing matching subdomains are reused. A nonempty configured value must match the environment, and the page ID must resolve to that subdomain. |
| `instatus.email` | Operator | Page owner email required only for page creation. |
| `instatus.initialStatus` | Operator override, default `OPERATIONAL` | Initial state for newly created components only. Override for a different known initial condition. It is never sent when updating an existing component. |
| `instatus.showUptime` | Operator, default `false` | Enable once real public status coverage/history is ready. No synthetic history is generated. |
| `instatus.componentIds` | Instatus / CLI | Maps stable component keys to returned IDs. May also explicitly identify existing components before first apply. |
| `catalog` / `generated` | CLI | Derived output and ownership metadata; do not edit by hand. |

Valid creation states: `OPERATIONAL`, `UNDERMAINTENANCE`,
`DEGRADEDPERFORMANCE`, `PARTIALOUTAGE`, `MAJOROUTAGE`. Instatus has no generic
unknown component state in this API. Omitting `initialStatus` uses `OPERATIONAL`;
the production examples expose this default. This initializes new components and
is not a health-check result. An explicitly empty string still prevents creation;
for older values containing `initialStatus: ""`, remove that field or set it to the
desired initial state. Existing component states are always preserved.

The generated catalog contains Public RPC, Transaction Sequencing, Deposits,
Withdrawals, Batch Publication, Node Sync, Bridge Portal, and Block Explorer.
Endpoints are included in the relevant public component descriptions. The first
automation version uses a dedicated page with a flat list of eight components;
the page title identifies the network. It does not create or move component groups.

## Two distinct credentials

- **Runtime webhook URL:** Instatus creates it in the page's Grafana integration.
  Store the complete URL in the referenced Secret in Grafana's namespace using
  the existing secret-management workflow. Grafana reads it through
  `INSTATUS_GRAFANA_WEBHOOK_URL`; the generated receiver retains that literal
  environment reference. This URL is not an existing scroll-monitor URL.
- **Management API key:** The CLI reads `INSTATUS_API_KEY` only for `--plan` and
  `--apply`. Supply it through the shell/CI secret environment. It is not a CLI
  argument, not saved in YAML, and not injected into the running chart.

Grafana holds the credential for the Instatus endpoint it pushes to. Instatus
receives no internal Grafana or Prometheus API key, and no internal monitoring
endpoint needs public ingress. Normal operation is still
`scroll-monitor → Prometheus → Grafana → Instatus native webhook`.

Provisioning uses fixed Grafana format version `1`, webhook type `webhook`, HTTP
`POST`, `disableResolveMessage: false`, and the literal environment reference.
Rotating the URL requires updating its Secret and restarting Grafana to refresh
the process environment. File-provisioned contact points are read-only in the UI.

## Automatically obtain the Grafana webhook

First initialization is explicit; ordinary redeployment reuses the saved URL:

```bash
scrollsdk setup status-page --plan --create-webhook
scrollsdk setup status-page --apply --create-webhook
# Later deployments:
scrollsdk setup status-page --apply
```

The CLI calls the official `POST /v3/integrations` endpoint with `pageId`,
`integrationType: GRAFANA` and `components: []`. Live validation confirmed that
the response contains `integration.uniqueUrl`, even though the documentation's
short example omits it. The CLI saves the returned URL without reconstructing it.
The integration starts active but has no component associations; alert selection,
component templates and Grafana routes remain a later step. No notification is sent.

Credentials are generated into the deployment directory, outside Helm values:

```text
secrets/status-page/
  .gitignore              # Ignores all files in this directory.
  binding.json            # Private creation journal, page binding, integration ID and URL.
  grafana.secret.yaml     # Kubernetes Secret using webhookSecretRef.name/key.
```

Every network uses the same relative path, `secrets/status-page/`, in its own
deployment directory. The saved network and page must match the current
configuration; a mismatch fails before remote writes. The directory is `0700`,
files `0600`; symlinks and Git-tracked
credential paths are rejected before remote writes. Treat both generated files
as credentials: **the integration ID is embedded in the webhook URL** and base64
Secret data is not encryption. Neither is printed in normal/JSON output or saved
in the public catalog, Helm values, or `.data/status-page-state.json`.

Apply the generated Secret separately, explicitly selecting the context and
namespace of the existing Grafana deployment:

```bash
kubectl --context YOUR_CONTEXT --namespace YOUR_GRAFANA_NAMESPACE \
  apply --server-side --field-manager=scrollsdk-status-page \
  -f secrets/status-page/grafana.secret.yaml
```

The CLI does not deploy Kubernetes resources or contact the cluster. Existing
secret-management systems may provision the same name/key instead. These nested
files are deliberately excluded from `setup push-secrets`' root `.env`/`.json`
scan; do not upload the entire binding or Secret manifest as a secret property.

Back up this private directory using encrypted deployment/CI secret storage.
No working public list/get API for monitoring integrations has been verified:
reuse relies on the saved credential and does not verify remote deletion,
deactivation or rotation. A durable creation journal is written before POST.
Timeout or interruption leaves the operation blocked instead of automatically
creating another integration. `generated.webhookRequested` is a nonsecret guard
that also blocks re-creation if the private binding is lost. If both regenerated
values and private state are lost, remote discovery cannot recover this binding;
restore it or import the existing URL rather than repeating first initialization.
CI workspaces must share the private state and serialize applies per environment.

To adopt an existing integration, recover an uncertain creation or rotate the
URL, copy the selected page's URL into a private text file outside Git, then:

```bash
scrollsdk setup status-page --plan --webhook-url-file /private/instatus-grafana.url
scrollsdk setup status-page --apply --webhook-url-file /private/instatus-grafana.url
```

Import checks URL format, but the operator must verify its page association in
Instatus. It does not create an integration or send a notification. These flags
require `--plan` or `--apply` and are mutually exclusive. `--plan` still writes
nothing. Apply the regenerated Secret and restart Grafana after rotation.

## Reconciliation and operational boundaries

Apply matches an explicitly selected page by ID or exact subdomain. Components
match saved IDs first, then exact names on that page. Duplicate names, missing
explicit IDs, archived components, and grouped components fail before writes.
Use a dedicated page and review `--plan` before first adoption of existing components.
Unmatched remote components are left in place; no delete requests are sent.

Only page name and component name, description, order, and uptime-display setting
are reconciled for existing resources. Live status, incidents, maintenance,
subscriptions, branding, and domains remain operationally managed. A fresh page
uses the provider's theme defaults. Page creation sends an empty component list,
then creates only the eight desired components with the explicit initial state.

The API is not transactional: partial success is possible. IDs are saved as each
operation succeeds; a failed or ambiguous write is not blindly retried. Rerun
`--plan`, then `--apply` to reconcile.

The CLI binds each deployment directory to one network and persists its page binding in
`.data/status-page-state.json`, separately from Helm values. It records the fixed
subdomain before creation and the returned page ID immediately afterward. A
regenerated values file recovers this binding. Even in a fresh checkout without
state, the fixed subdomain is searched before creation. The page name, deployment
timestamp and release version never determine a new subdomain. A known page that
is missing/inaccessible fails instead of creating a replacement. Corrupted state
or conflicting page/subdomain settings also fail for explicit resolution.

Keep the state file with deployment backups; it contains identifiers only. A
`.data/status-page-apply.lock` serializes applies sharing a deployment root; a
stale lock must be removed only after its process has stopped. Separate CI
workspaces must serialize operations for the same environment because the API
offers no idempotency token or compare-and-swap guarantee here. Use separate
deployment directories, Secrets and pages for separate environments.

Generation preserves unrelated Grafana provisioning and notification policies.
Conflicting use of the reserved environment variable, provisioning file, contact
point name or receiver UID fails for explicit resolution. Changing the configured
Secret reference regenerates the owned fields. Renaming a provisioned contact
point or changing its organization is a migration: remove the former resource
and its routes deliberately rather than leaving two active destinations.

To disable an already provisioned integration, first remove its public routes
and Grafana contact point, then remove its generated `grafana.envValueFrom` entry,
`grafana.alerting.instatus-contact-points.yaml`, `statusPage.catalog`, and
`statusPage.generated`; set `statusPage.enabled=false`. Merely removing a Grafana
provisioning file does not delete the resource from Grafana's database.

Webhook creation and credential retrieval are supported through the explicit
initialization flow above. Kubernetes application and selective alert/component
mappings remain operational steps. Thresholds, public incident content and alert selection remain
outside this change, as agreed. No alert or incident is sent by configuration
generation or reconciliation.

API reference: [status pages](https://instatus.com/help/api/status-pages),
[components](https://instatus.com/help/api/components),
[monitoring integrations](https://instatus.com/help/api/monitoring-integrations),
[Grafana integration](https://instatus.com/help/integrations/grafana).
