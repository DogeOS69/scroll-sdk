# Status page 接入架构

日期：2026-09-26。决策：第一阶段使用原生 webhook 推送，不实现自建 publisher，不展示连续数值指标图表。仓库提供可选配置示例，尚未部署或验证生产 webhook 链路。

初始化自动化已补齐：CLI 的 `setup status-page --apply --create-webhook` 调用 Instatus 创建 Grafana integration，并保存响应中的 `integration.uniqueUrl`。真实 API 已验证，临时验证集成已删除；没有发送告警或事故通知。integration ID 与 URL 一并按凭据保存到 Git 忽略的私有目录。普通 `--apply` 复用本地绑定；查询已有集成的公共 API 尚未验证，记录丢失或创建结果不明时停止并恢复/导入已有 URL，不能自动重建。完整命令、Secret 应用及备份要求见 [初始化说明](status-page-automation.md#automatically-obtain-the-grafana-webhook)。

## 架构与通信方向

scroll-monitor 已包含 Prometheus、Grafana 和 Alertmanager。Prometheus 采集指标，Grafana 查询指标并计算应用告警；经明确选择的告警由 Grafana 向 Instatus 推送。Instatus 承担公开页面、组件状态、事故及可用性历史。

```text
Our private monitoring network                         Instatus

Services --> Prometheus --> Grafana-managed alerts ---- HTTPS webhook ---> Public status page
                  |
                  +-------> Alertmanager ------------- HTTPS webhook ---> (optional source)
                            infrastructure alerts

scroll-monitor contains Prometheus, Grafana and Alertmanager.
Grafana and Alertmanager are independent notification senders.
Only explicitly selected alerts will be routed to Instatus.
```

箭头 `Prometheus --> Grafana` 表示指标供给；实际由 Grafana 在内网查询 Prometheus。跨越网络边界的是 Grafana（或可选的 Alertmanager）主动发出的 HTTPS 通知。Instatus 不回连内网，也不需要我们的监控访问凭据。原生集成方式见 [Grafana](https://instatus.com/help/integrations/grafana) 和 [Prometheus / Alertmanager](https://instatus.com/help/integrations/prometheus) 官方文档。

第一阶段只接入现有 Grafana 应用告警的通知能力。Alertmanager 继续负责已有基础设施告警；是否有对外公开的基础设施告警留待后续，不默认新增对外路由，同一事件也不应同时从两个引擎发布。

## 凭据与网络边界

| 内容 | 持有者 / 去向 |
| --- | --- |
| Instatus Grafana webhook URL | 我方 Secret 管理系统与 Grafana 发送端；URL 本身是敏感凭据 |
| 可选的 Instatus Prometheus webhook URL | 我方 Secret 管理系统与 Alertmanager 发送端；使用对应原生集成生成的 URL |
| Prometheus / Grafana 内部访问凭据 | 保留在我方；不交给 Instatus |
| Instatus 通用管理 API key | 当前运行时不需要；不注入 chart |
| 公网入口 | 不为这次接入新增；Prometheus 维持私网访问 |
| 出站请求 | 发送到供应商实际生成的 HTTPS webhook URL，不把 REST API host 当作 webhook host |

这里使用的是 webhook 凭据，不是区块链签名私钥。发送端持有 Instatus 生成的接收凭据，Instatus 验证请求。URL 不进入 Git、Helm values 或日志；production YAML 只记录 Secret 引用。不能因 URL 看起来随机就声称它具备已验证的页面级权限、有效期或轮换能力；实际授权范围及替换流程以供应商该集成为准。

可选 YAML 方案通过 `grafana.envValueFrom` 从 Kubernetes Secret 注入 URL，文件里的 `settings.url` 保留环境变量引用。轮换 Secret 后必须重启 Grafana，让其重新读取环境变量并执行 provisioning。URL 会进入 Grafana 运行时配置；Secret 注入不代表 Grafana 数据库、API 或备份里的 URL 自动保密。

如果集群限制出站访问，按实际 webhook host 配置已有防火墙、代理或支持域名规则的 CNI；原生 Kubernetes NetworkPolicy 不能直接用域名做白名单。无需为此新增内部接入 token、publisher Service、PVC 或队列。

## 页面展示范围与 publisher 的必要性

组件状态、事故记录和可用性历史由状态页服务原生提供，不要求我们上传连续指标。公开页面可参考 [Arbitrum](https://status.arbitrum.io/) 和 [Optimism](https://status.optimism.io/) 的组件与历史展示；页面外观不能证明其内部告警或发布实现。

Instatus 的 uptime 展示来自其事故/中断历史，不等同于把 Prometheus 的原始时间序列搬到页面上。具体规则见 [Instatus uptime colors](https://instatus.com/help/status-page/uptime-colors)。所以采用这类展示本身不构成自建 publisher 的理由。

只有后续出现原生集成无法满足的明确需求，例如连续数值图表、跨来源聚合或定制对账，再评估适配程序。Instatus 虽提供 [Prometheus metrics 拉取集成](https://instatus.com/help/integrations/metrics/prometheus)，那是另一条需要供应商可达查询端点的链路，本次不启用。

## 配置边界

- 删除旧设计中的 publisher 保留配置、启用拦截、API key 引用及存储/事件接入约定。
- 使用现有 Grafana chart 的 `envValueFrom` 与 `alerting` 字段。两个 production 示例均提供相同的注释配置，默认不创建 Instatus contact point 或路由。
- webhook URL 由 Instatus 动态生成并进入 Secret；Secret 名称/key、Grafana org ID 按部署填写；contact point 名称和 UID 使用稳定约定。协议类型、POST、恢复通知和环境变量引用按示例固定。
- 文件配置只创建 contact point，通知路由仍在后续人工选择公开告警时设置，避免覆盖整棵现有 notification policy tree。
- 可选择完全在 Grafana UI 管理 contact point；不要同时用 YAML 接管同一个对象。文件配置的 contact point 在 UI 中只读，现有 UI 管理的其他 contact points 和通知策略保持原有方式。
- CLI 默认离线生成原生 Grafana 配置、Secret 引用和公开组件目录；`--plan` 只读比较，显式 `--apply` 才创建或更新 Instatus 页面/组件。管理 API key 仅通过命令环境读取，不保存或注入运行时；不自动选择公开告警。详见 [自动化配置契约](status-page-automation.md)。

字段来源、配置示例和启用步骤见 [配置生成说明](../examples/scroll-monitor-configuration.md#instatus-native-webhook-configuration) 及 [production example](../examples/values/scroll-monitor-production.yaml)。Grafana 文件管理规则见 [官方 provisioning 文档](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/)。

## 运行边界和后续验收

原生通知机制承担投递，不为当前需求自建重试队列或持久化进程，也不承诺跨系统 exactly-once。监控系统或整个集群失联时，Instatus 可能保留最后状态；没有通知不能被解释为服务健康。页面仍可通过 Instatus 人工维护，后续可按需求增加独立外部探测。

启用真实公开路由前，针对测试页面验证告警触发、恢复、重复通知、分组、多告警重叠及网络失败后的行为。Grafana 的 Test 按钮是真实外发操作。必须检查 outbound labels/annotations 和生成的公开内容，不能直接把所有内部告警挂到公共接收端。具体公开异常、阈值、事故文案和组件映射仍是下一阶段的决策。

本次本地验收覆盖 Helm 配置渲染、Secret 引用、默认不启用、CLI 配置保留；不代表 webhook 已完成远端联调。

## 2026-09-26 API 实测

使用用户临时提供的 API key，通过 `https://api.instatus.com` 验证。凭据通过关闭回显的终端输入，仅在验证进程内使用，未写入仓库或临时文件。本文不记录凭据、个人资料或成员名单。

| 验证 | 结果 |
| --- | --- |
| `GET /v1/user` | 200；返回用户资料，没有 token scope 信息 |
| `GET /v2/pages?page=1&per_page=100` | 200；返回一个页面 |
| `GET /v1/workspaces?page=1&per_page=100` | 200；返回一个工作区，关联该页面 |
| `GET /v2/:page_id/components` | 200；返回两个组件 |
| `GET /v1/:page_id/metrics` | 200；返回一个指标 |
| `GET /v1/:page_id/team` | 200；成员条目没有返回角色 / 权限字段 |
| 不带 Authorization 请求 `GET /v2/pages` | 401 |
| `PUT /v1/:page_id/metrics/:metric_id`，仅将 suffix 回写为原值 | 200；随后读取确认 id、name、suffix、active、order、data 均未变化 |

没有修改组件状态、创建事故、发送订阅通知、创建资源或调用删除 / 吊销接口。原值回写属于真实写请求，可能产生供应商内部更新时间或审计记录。

可以确认此 key 有上述读取权限和指标配置写入权限；不能由此推断它具有全部写权限，也不能证明它被限制到单一页面。仅有一个可见页面时，无法区分“用户只有一个页面”与“key 被限制到一个页面”。页面级 scope、只写权限、跨 workspace 隔离、过期和吊销机制仍待供应商控制台或独立授权身份对照验证。这些是管理 API 的历史验证结果；当前原生 webhook 方案不需要运行时持有该 API key。

兼容性观察：指标列表返回的 name 实际为对象，而非文档示例中的字符串；验证因此只回写原有字符串 suffix。另一次使用默认 Python User-Agent 的读取返回 403，恢复明确的应用 User-Agent 后返回 200；原因尚未定位，不能把该 403 当作 token scope 的证据。后续客户端应设置明确 User-Agent，并区分 HTTP 网关拒绝与 API JSON 鉴权错误。

健康规则的三态判定、每组件发布来源、外部观测和模板采集审计见 [健康规则 v1](status-page-health-rules.md)。当前单个初始化 webhook 尚未实现该设计中的按组件路由。
