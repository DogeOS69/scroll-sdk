# Independent Alertmanager backend

Select `alerting.backend: prometheus` using
`examples/values/scroll-monitor-alertmanager.yaml` after the environment's
production values. The chart retains `grafana` as its compatibility default;
backend changes on an existing installation require the migration below.

Prometheus evaluates metric alert rules. Grafana evaluates the LogQL rules and
forwards firing and resolved events through the `scroll-external-alertmanager`
contact point. This forwarding hop uses no initial wait, a 10-second group
interval and one-minute refreshes; Slack repeats remain controlled by the
independent Alertmanager. The independent Alertmanager owns Slack routing, grouping,
inhibition and silences. Grafana provisions an `Alertmanager` data source for
viewing alerts and managing silences. Select this data source, rather than the
built-in Grafana Alertmanager, on the Silences page.

The provisioned Loki data source sets `jsonData.manageAlerts: false`. LogQL
alerts remain Grafana-managed and continue forwarding to the external
Alertmanager. This disables discovery and management of Loki ruler rules in the
Grafana UI, avoiding unsupported Ruler API probes against local rule storage;
Explore queries and Grafana-managed log alert evaluation remain available.
Prometheus keeps `manageAlerts: true` for viewing its native rules. If migrating
log rule evaluation to Loki ruler later, configure that rule owner and its
storage before enabling Loki rule management.

Python balance and node collectors, bridge observations, and the status-page
health evaluator and durable publisher remain independent services. Silencing
an internal Slack notification does not suppress public status-page events.
Use the status-page maintenance configuration for public publication controls.

## Configuration and credentials

Set `alerting.alertmanager.grafanaURL` to the public Grafana base URL. Slack
message titles and the Alerts link open Grafana's alert list, filtered by alert
name when available. Firing notifications also link to the external Alertmanager's
silence form in Grafana. An unset Grafana URL omits these links instead of
falling back to cluster-internal Prometheus or Alertmanager URLs. Dashboard and
runbook links remain supplied by rule annotations. Prometheus and Alertmanager
do not need an Ingress for these Grafana links to work. Previously delivered
Slack messages retain their original links; the template applies to subsequent
notifications.

Configure
`alerting.alertmanager.slack.existingSecret` and include the same Secret name in
`kube-prometheus-stack.alertmanager.alertmanagerSpec.secrets`. The Secret must
contain the key named by `slack.secretKey` (default `url`). Provision its actual
value outside Git and Helm values. The chart references `api_url_file`; it does
not copy the webhook into the Alertmanager configuration or Helm release.

Without a Slack Secret, the chart creates a valid `slack-alerts` receiver without
an integration. Rules and silences still work, but Slack notifications are not
sent. Do not use an empty `slack_api_url` with an enabled Slack integration.

The chart owns the Alertmanager configuration and portable Slack templates in
`alerting.alertmanager.configSecretName`. Configure the bundled Alertmanager
with `useExistingSecret: true` and matching `configSecret`. Contact points,
routes, and templates for this independent Alertmanager are managed through
configuration, while silences are runtime state on its persistent volume.
Grafana's legacy Slack receiver is not used by forwarded LogQL rules.

## Resolved log notifications

Grafana can forward unresolved annotation templates when retiring a stale log
alert instance. Alertmanager treats annotation strings as data; it does not
expand Grafana's `$labels` or `$values` expressions a second time. The Slack
template builds log alert summaries and resolved descriptions from the alert's
labels and status. Resolved messages do not report a current log count from a
missing or historical sample. `grafana_state_reason: MissingSeries` is shown as
series disappearance, which is not sufficient evidence of service recovery.
Firing messages retain valid rendered descriptions and counts. Unexpanded
annotations fall back to plain text instead of exposing template expressions.
The same annotation helpers are used by both the independent Alertmanager and
the Grafana Slack templates. Link fields containing unresolved expressions or
missing-value markers are omitted; valid HTTP(S) dashboard and runbook links
remain available. Rule annotation expressions are retained for normal Grafana
evaluation; notification templates never evaluate annotation text as code.

## Migrate an existing installation

1. Privately back up Helm values, Grafana rules, contact points, routing and
   templates. Export existing rules' pause states and operator changes.
2. Translate pause states into `grafanaAlerting.pauseRules`. In Prometheus mode,
   paused metric rules are omitted. Preserve edited expressions, labels,
   annotations, pending periods and evaluation intervals in source before
   switching; do not assume a chart render includes UI changes.
3. Render the new rules and compare them with every active Grafana metric rule.
   Validate with `promtool check rules` and the chart tests. Validate the
   Alertmanager configuration and templates with `amtool`.
4. Stage the new backend with Slack disabled and skip the Grafana seeding hook
   (`--no-hooks`). Wait for Alertmanager readiness and Prometheus rule loading.
   Existing Grafana notifications remain active during this stage.
5. Pause the old metric rules, enable the new Slack receiver, and run the normal
   upgrade hook to switch LogQL notifications to the forwarding contact point.
   Verify firing, recovery, external silence access and notification failures.
6. Remove the backed-up, migrated Grafana metric rules after verifying the new
   owner. Preserve the remaining LogQL rules and unrelated contacts. Verify
   that each rule has one active evaluator and repeat upgrades are idempotent.

Switching alert evaluators does not preserve pending timers or notification
fingerprints. Stage long enough to establish pending/firing state where needed;
record the cutover and expect a new notification group for existing incidents.
Pausing or restoring rules can emit state transitions in Grafana.

For rollback, disable the new Slack receiver first, restore the previous chart
values and backed-up Grafana rules (including pause states), then restore their
original notification routing. Do not delete the status-page or Alertmanager
persistent volumes.
