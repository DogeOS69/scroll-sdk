# Internal alert notification format and wording guide

Applies to every Grafana alert that scroll-monitor sends to internal Slack. It does not cover the
public status page (see [public component health rules](status-page-health-rules.md)).

## Slack message template

The chart's alert seed Job writes the notification template `scroll-monitor` into Grafana, with content
from `charts/scroll-monitor/notifications/slack.tmpl`. The template can be edited in the UI: an
unmodified template is upgraded with the chart; a template modified in the UI, or an unmanaged template
with the same name, is kept and reported as `DRIFT` in the Job log.

The Slack contact point must reference it (configure once):

| Field | Value |
| --- | --- |
| Title | `{{ template "scroll-monitor.slack.title" . }}` |
| Text Body | `{{ template "scroll-monitor.slack.text" . }}` |

Enter the values above directly in the Grafana UI. When configuring them as code through
`grafana.alerting` values, use the escaped form shown in the `values/production.yaml` example;
otherwise the Grafana subchart's `tpl` executes this template during installation and fails.

Message structure:

```text
[FIRING:2] CRITICAL · testnet · 2 alerts · l1-interface      ← title: status, severity, network, alerts, service
*Firing (2)*
*Protocol state has not recorded a new WF transaction for 60 minutes.*   ← summary
Job l1-interface in namespace default has not observed ...               ← description
`ProtocolStateWFTxNumberStalled job=l1-interface namespace=default`      ← alert name and locating labels
Since 2026-10-02 06:58 UTC · Rule · Silence                              ← time and links
```

- The network name comes from `grafanaAlerting.notificationTemplate.environment`, falling back to
  `statusPage.environment` when empty.
- Grafana's internal `A=… B=… C=…` expression values are not shown; put any values worth showing in
  the description.
- The locating-label line starts with the alert name and omits `severity`, `managed_by` and
  `grafana_folder`.
- Each group lists at most 10 alerts; view the rest in Grafana. When a rule is linked to a dashboard,
  Dashboard/Panel links are included.

## Alert wording guide

Every rule (`charts/scroll-monitor/alerts/**/*.yaml`) follows these conventions, checked by
`tests/test_alert_notifications.py`. Write in English.

**summary** is the title line in Slack:

- One sentence, ending with a period, at most 100 characters.
- Start with the component, then state the symptom and threshold/duration:
  `Fee oracle value has not been updated for 15 minutes.`
- Use component names (TSO, L1 Interface, Ethereum DA submitter, etc.), not metric names or
  expressions such as `readiness is below 1`.
- Each rule's summary is unique and cannot reuse another rule's title.

**description**, in order:

1. Evidence: which object (`{{ $labels.job }}` etc.) shows what, with values when needed.
2. Impact: only when certain, for example "so no bridge transaction can be signed". Use a conditional
   sentence when uncertain.
3. Next step: `Check …` / `Inspect …`, ordered by most likely cause. When related alerts fire together,
   say which to check first.
4. Existing boundary notes (such as "Missing telemetry does not establish …") go last.

**Values and labels**:

- Use `$value` only when the expression returns a meaningful quantity, and always format it: counts
  `{{ $value | printf "%.0f" }}`, ETH `printf "%.4f"`, DOGE `printf "%.2f"`, seconds
  `{{ $value | humanizeDuration }}`. Do not show `$value` for comparison or stall expressions that
  return 0/1.
- Reference only labels that the expression keeps. Aggregations such as `max(...)` and `sum(...)`
  without `by` drop job/instance.
- Use forms such as `item(s)` when a count can be 1.

Changing the wording of an existing rule needs no field migration: the seed Job updates annotations
whose recorded baseline has not been modified in the UI. Labels belong to operators, and chart upgrades
do not rewrite the labels of deployed rules.
