# Public incident severity

Binary health (`0`, `1`, or absent) answers whether the reviewed check is affected.
It does **not** identify whether the impact is slow service, partial unavailability,
or complete unavailability. Never infer `DEGRADEDPERFORMANCE` simply from `1`.

The generator no longer supplies a global default for affected status. With
`publication.incidents.manageTemplates: true`, every automatic component must
explicitly set `publication.components.<key>.affectedStatus` to one of:

| Status | Required interpretation |
| --- | --- |
| `DEGRADEDPERFORMANCE` | Service still works but verified performance or processing timeliness has deteriorated |
| `PARTIALOUTAGE` | A verified subset of the component's public functionality is unavailable |
| `MAJOROUTAGE` | The component's principal public function is unavailable |

There is no severity default. An empty field is permitted for observe/manual
components. Operator-managed remote templates (`manageTemplates: false`) are not
overwritten by the CLI; their severity must be reviewed in Instatus itself.

Move the old `publication.incidents.affectedStatus` to the appropriate component
inputs after reviewing their rules. Old global configuration is rejected with a
migration error rather than silently applied to every component. Offline
generation changes local configuration only; use `--plan` and `--apply` to update
the existing integration templates. Applying a new template does not reclassify
an already open incident. Update that same incident explicitly without reporting
a recovery or creating a replacement.

## Current limitation: fixed template policy is not dynamic classification

The native Grafana integration currently has one creation template per component.
The configured severity is fixed for that rule. A rule combining latency and
availability failures cannot accurately classify all those outcomes with one
fixed severity. Per-component configuration prevents a hidden universal default;
it does not solve this information loss or make all built-ins severity-aware.

Dynamic classification still requires separate, complete, fresh evidence for each
impact level and a delivery protocol that can change severity on the **same**
active incident. Classification must preserve unknown observations, confirmation
windows, durable incident identity and recovery ownership. It must not resolve an
incident merely to reopen it with a different severity, or treat loss of metrics
as recovery. Runtime management API credentials are not introduced by this change.

The provider documents a status parameter for its separate
[Webhook to Incident integration](https://instatus.com/help/integrations/custom-service-webhook).
That is not the current Grafana protocol. Its update/deduplication/recovery behavior
must be verified before migrating; no unverified extra field is sent to the
existing Grafana webhooks.

## Devnet correction

Bridge Portal's current failure affects its history API while its page responds:
`PARTIALOUTAGE`. Block Explorer's page and API both fail HTTPS certificate
validation: `MAJOROUTAGE`. These classifications describe the observed failures,
not permanent severity assumptions for every future failure of those components.
Other existing component policies are preserved explicitly during this migration;
they have not thereby acquired dynamic severity classification.
