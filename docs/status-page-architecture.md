# Status page 接入架构

当前代码的职责划分（2026-10-01）：dogeos-core 提供只读健康事实及解释契约；
scroll-monitor 自带评估和发布脚本；scroll-sdk-cli 解析实际部署参数。
Mainnet、Testnet、Devnet 使用独立的配置、Prometheus、状态日志和组件绑定。
这份文档描述代码行为，不代表任何网络已经升级。

```text
core /metrics ────────────────┐
Alloy / 外部入口探针 ──────────┼──> Prometheus ──> scroll-monitor 评估器 ──> Instatus
官方 Node Sync 采集器 ─────────┘         │                 │
                                       └──> Grafana <── 结果 /metrics
                                              │          │
                                         内部告警/展示    └──> Instatus 独立心跳
```

## 唯一的运行时规则归属

- core 保留 [健康事实契约](https://github.com/DogeOS69/dogeos-core/blob/feat/core-health-observability/docs/engineering/core-health-observability.md)
  和 [外部评估指导](https://github.com/DogeOS69/dogeos-core/blob/feat/core-health-observability/docs/engineering/bridge-health-evaluator.md)，删除可执行原型和原型测试。
- `charts/scroll-monitor/scripts/status_page_health.py` 拥有规则、PromQL 和默认阈值。
  `status-page-delivery.py` 在同一个进程中定时取证、评估、执行确认窗口、持久化并发布。
  保留原 `*-status-delivery` Deployment、Service、PVC 名称，避免迁移丢失事件身份。
- CLI 生成部署相关的 URL、链 ID、网络、命名空间、节点成员/副本数、探针目标、组件绑定和 Secret 引用。
  显式运维策略原样校验和传递，不生成内置健康 PromQL，不拥有故障/恢复默认值。
- Grafana 用于展示和内部排障/告警。Grafana 停止、删除/暂停规则或发送 resolved 都不能改变公开状态。

这是一个评估/发布进程和一个规则模块，不另建通用规则服务。其他采集器负责取得事实，
不持有公开组件 webhook。运行时不需要 Instatus 管理 API key。

## 判定与证据

每 30 秒完成一轮查询后等待下一轮；慢查询不会叠加新一轮。内置规则最多十个不同查询，
共享 WF 查询只读取一次；最多八个并发 HTTP 请求，每次超时 10 秒、响应上限 1 MiB。
直接访问 Prometheus，不访问 core 数据库，也不按抓取频率触发业务查询。
`/metrics` 和 `/health` 只读取最近一次结果，不重新取证。

Grafana 的 **DogeOS / Status-page health** 面板展示新鲜结果、证据完整性及持久化事件。
内部告警覆盖评估器失联、必需证据不完整及投递失败，不向公开组件发送通知。

结果含 `operational/degraded/unavailable/unknown`、观测完整性、原因、覆盖范围及有效时间。
恢复要求所有必需证据完整、新鲜并持续健康；已经确认的故障可以在其他证据缺失时继续成立。
过期、未来时间戳、重复来源、查询失败、预算耗尽不能等价于业务故障，也不能等价于恢复。
默认故障确认 5 分钟、恢复确认 10 分钟；重启、采样断档、时钟倒退和未知都重置确认窗口。

当前规则覆盖公共队列 deadline、规范 WF 停滞和已配置的入口/节点探针，属于 `pipeline`
证据，不是端到端转账成功证明。core 指导中的全部规则不是当前已实现功能：新任务签名法定人数、
第三方 signer 完整在线成员集合等缺少可靠来源时，不能用注册人数或单个任务签名数替代。
不调用第三方 signer 的管理接口，也不主动签名或提交充值/提现。

`publication.sourceNamespace` 限定 core 的指标来源；空值使用 Helm namespace。
`health.withdrawalProcessorExpectedTargets` 和 `health.ethDaSubmitterExpectedTargets` 默认各为 1，
部署多个有效实例时必须显式填写。缺少 target 不能因 Prometheus 当前集合缩小而误恢复。
业务 deadline 默认 0，表示未配置；不是默认 SLA，也不是忽略该依赖。

## 发布、凭据和监控失联

每组件模式为 manual（不评估/发布）、observe（评估但不发布）、automatic（评估并发布）。
公开 webhook 及可选心跳 Secret 只交给评估进程。CLI 管理 API key 仅用于显式 plan/apply。
SQLite PVC 保留活动及待发送事件，重试使用原身份。未知不清除活动事件；维护窗口暂停发布且保留证据。
HTTP 结果不明且健康反转时保留待发送事件，内部告警并由值班人员对账，不能盲目发送相反事件。

Instatus 使用现有每组件 webhook 模板；其公开严重度仍由审核过的 `affectedStatus` 决定。
评估器的 degraded/unavailable 结果可观测，但本次没有引入动态修改 Instatus 模板的管理 API 调用。
自动公开恢复须完成健康确认窗口，手工接管前先部署 manual 模式。

可选独立心跳由评估器直接发送，要求已配置的非 manual 组件观测完整且没有投递错误。
已确认的业务故障不会阻止心跳；缺证据或监控失联会停止心跳。未配置的 observe 组件不参与心跳门控。
Instatus Cron Monitor 独立通知内部值班人员；监控失联不自动宣布全网故障。

## 升级

使用配套 CLI 重新生成 schema v3 配置并部署新版 chart。CLI 为旧的公开 Grafana 规则/contact point
生成按既有保留 UID 删除的 provisioning，只清理旧 managed 发布资源，保留内部通知策略。
保留同一 release、PVC、网络和组件绑定。升级过程中应先停止旧公开规则再启用新版评估器，避免两个发布者并存；
可先部署所有组件 observe，确认旧规则已清理、观测正确，再部署 automatic。事件日志在两步中持续保留。

详见 [发布配置](status-page-publication.md)、[健康规则](status-page-health-rules.md) 和
[production values](../examples/values/scroll-monitor-production.yaml)。
