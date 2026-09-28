# Status page 接入架构

当前实现：2026-09-28。Mainnet、Testnet、Devnet 共用 `dogeos.instatus.com`，
workspace 为 `6wxpx`，每组 8 个组件；L2Scan 不在范围内。每个网络仍拥有自己的
工作目录、scroll-monitor、Prometheus、Grafana、Secret 和组件绑定。

## 通信方向

```text
现有 Alloy 经公网入口探测 ─────────指标──┐
                                             v
该链 dogeos-core /metrics ───────────────> Prometheus
该链官方 Node Sync 逐 Pod 采集器 ────────────^
                                             │ 内网查询
                                             v
                                          Grafana
                                          │     │
                                    组件告警    每分钟心跳
                                          │     └──────> Instatus Cron Monitor → 内部值班通知
                                          v
                                状态投递校验器 + 持久化日志
                                          │ HTTPS webhook
                                          v
                              Instatus 当前网络的公开组件
```

Instatus 不访问内部 Grafana、Prometheus 或 Kubernetes。现有 Alloy 经公网 DNS/Ingress 检查已有用户入口，
在该链集群内运行，通过已有私网 remote-write 写入指标。Alertmanager 和现有内部告警继续各自的职责，
不自动转发到公开页面。整个集群失联时，独立 Cron Monitor 通知值班人员；页面保留
最后确认状态，监控失联不等价于整条链故障。

## 凭据归属

| 凭据 | 持有者 | 用途 |
| --- | --- | --- |
| Instatus 管理 API key | 执行 `--plan` / `--apply` 的 CLI 环境 | 读取或管理页面、组件、集成、心跳；不进入 chart 或运行时 |
| 每组件 Grafana webhook URL | Kubernetes Secret，默认由投递校验器读取 | 发送该组件的确认故障/恢复；旧的直接模式由 Grafana 读取 |
| Cron heartbeat URL | 独立 Secret，由 Grafana 读取 | 证明监控链路仍工作，不创建公开事故 |
| 内部监控凭据 | 我方 | 不交给 Instatus |

Webhook 是供应商生成的接收凭据，不是链上签名私钥。URL 不放入 Git、values 或日志。
轮换 Secret 后重启实际持有它的 workload。每个工作目录的私有文件统一在
`secrets/status-page/`；备份绑定收据，不能删除收据后用重跑来强制创建新集成。

## 为什么增加投递校验器

公开页面及 uptime 历史由 Instatus 原生提供，不需要上传连续数值图表。
早期方案采用 Grafana 直接推送并人工恢复，这条兼容路径仍可用。
本次完整自动化加入了明确需求：**只有连续有效的业务健康证据才可以公开恢复**。
Grafana 在规则暂停、删除等生命周期变化中也可能结束告警；仅有 firing 的 `for`
不能保证恢复窗口。因此 production 示例默认启用轻量校验器：

- 查询同一组件表达式，等待独立的故障/恢复确认窗口。
- 仅接收匹配网络和组件的 Grafana firing；忽略原始 resolved。
- 使用单副本和 SQLite PVC 保存活动/待发送事件，重试使用相同事件身份。
- 只发送固定公开字段，移除内部标签、注释和 URL。
- 不持有管理 API key，不读取 Instatus 的远端状态，不承诺 exactly-once。

这是恢复判定和可靠投递所需的工作负载，不是新的公开页面后端。
HTTP 结果不明确且健康已变化时暂停相反事件，内部报警并由值班人员对账。
人工接管前将该组件切到 `manual` 并部署，不能只在 Grafana UI 中静默告警。

## 配置与启用

组件可独立使用 `manual`、`observe`、`automatic`。示例默认全部 observe；
业务 deadline 默认 0（未配置）；首版复用已有 Alloy。只有选用 external 深度模式时才需要外部语义检查和独立位置。
CLI 自动生成目录、规则、组件 contact point、Secret 引用和探针配置，保留已有
Grafana 全局通知策略。`--plan` 只读；`--apply` 管理 Instatus 资源，不部署 K8s。
同一网络重跑复用绑定。共享页面元数据应用需按页面串行执行。用户已确认三个网络
分组创建完成；CLI 复用已有分组，不将分组初始化列为当前待办。全新页面的一次性
初始化说明仍保留在配置文档中，正常重部署不重复执行。

计划维护窗口与自动发布的联动最后处理；在实现前先部署组件 manual 模式，
再人工操作维护。首版公网入口探测复用现有 Alloy，见 [Alloy 方案](status-page-alloy.md)；外部独立位置是可选后续工作。

完整字段、健康规则、故障边界与命令见 [组件发布配置](status-page-publication.md)、
[健康规则](status-page-health-rules.md)、[上线验收](status-page-rollout.md) 和
[production example](../examples/values/scroll-monitor-production.yaml)。
本地自动化验证不代表任何具体网络已经部署或完成真实 Instatus 事故联调。

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

健康规则的三态判定、每组件发布来源、外部观测和模板采集审计见 [健康规则 v1](status-page-health-rules.md)。按组件发布生成能力见 [组件发布配置](status-page-publication.md)，旧单个初始化 webhook 保留兼容；线上路由需在部署生成配置后才生效。

首版入口采集链路为现有 Alloy → 公网 DNS/Ingress → 服务，再经私网 remote-write → Prometheus → Grafana → 已有投递校验器 → Instatus。Alloy 自动发布要求配置 Instatus 内部心跳目的地，监控失联不等于所有业务组件故障。
