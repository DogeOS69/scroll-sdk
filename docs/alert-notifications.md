# 内部告警通知格式与文案规范

适用于 scroll-monitor 发送到内部 Slack 的全部 Grafana 告警，不涉及公开状态页
（见 [公开组件健康规则](status-page-health-rules.md)）。

## Slack 消息模板

chart 通过告警 seed Job 把通知模板 `scroll-monitor` 写入 Grafana，
内容来自 `charts/scroll-monitor/notifications/slack.tmpl`。模板在 UI 中可编辑：
未改动的模板随 chart 升级；UI 修改过或同名的非托管模板会保留，并在 Job 日志里报告 `DRIFT`。

Slack contact point 需要引用它（只需配置一次）：

| 字段 | 值 |
| --- | --- |
| Title | `{{ template "scroll-monitor.slack.title" . }}` |
| Text Body | `{{ template "scroll-monitor.slack.text" . }}` |

在 Grafana UI 中直接填写上表的值。若通过 `grafana.alerting` values 文件化配置，
必须使用 `values/production.yaml` 示例中的转义写法，否则 Grafana 子 chart 的 `tpl`
会在安装时执行这段模板并报错。

消息结构：

```text
[FIRING:2] CRITICAL · testnet · 2 alerts · l1-interface      ← 标题：状态、级别、网络、告警、服务
*Firing (2)*
*Protocol state has not recorded a new WF transaction for 60 minutes.*   ← summary
Job l1-interface in namespace default has not observed ...               ← description
`ProtocolStateWFTxNumberStalled job=l1-interface namespace=default`      ← 告警名与定位标签
Since 2026-10-02 06:58 UTC · Rule · Silence                              ← 时间与链接
```

- 网络名取 `grafanaAlerting.notificationTemplate.environment`，为空时使用 `statusPage.environment`。
- 不显示 Grafana 内部的 `A=… B=… C=…` 表达式值；需要展示的数值写进 description。
- 定位标签行以告警名开头，省略 `severity`、`managed_by`、`grafana_folder`。
- 每组最多列出 10 条，其余在 Grafana 中查看。规则关联了 dashboard 时附带 Dashboard/Panel 链接。

## 告警文案规范

所有规则（`charts/scroll-monitor/alerts/**/*.yaml`）遵守以下约定，
由 `tests/test_alert_notifications.py` 检查。英文书写。

**summary** 是 Slack 中的标题行：

- 一句话、以句号结尾、不超过 100 字符。
- 以组件开头，写现象和阈值/时长：`Fee oracle value has not been updated for 15 minutes.`
- 使用组件名（TSO、L1 Interface、Ethereum DA submitter 等），不写指标名或 `readiness is below 1` 这类表达式。
- 每条规则的 summary 唯一，不能复用其他规则的标题。

**description** 依次写：

1. 证据：哪个对象（`{{ $labels.job }}` 等）出现了什么，必要时带数值。
2. 影响：仅在确定时写，例如 “so no bridge transaction can be signed”。不确定就写条件句。
3. 下一步：`Check …` / `Inspect …`，按最可能的原因排序。相关告警同时触发时说明先查哪个。
4. 已有的边界说明（如 “Missing telemetry does not establish …”）放在最后。

**数值与标签**：

- 只在表达式返回有意义的量时使用 `$value`，且必须格式化：计数 `{{ $value | printf "%.0f" }}`，
  ETH `printf "%.4f"`，DOGE `printf "%.2f"`，秒数 `{{ $value | humanizeDuration }}`。
  比较型或停滞型表达式（返回 0/1）不要显示 `$value`。
- 只引用表达式保留下来的标签。`max(...)`、`sum(...)` 等未 `by` 的聚合会丢掉 job/instance。
- 计数可能为 1 时用 `item(s)` 这类写法。

修改已有规则的文案不需要迁移字段：seed Job 会更新已记录基线且未被 UI 修改过的 annotation。
labels 属于运维方，已部署规则的 labels 不会被 chart 升级改写。
