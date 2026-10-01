# 公开组件健康规则

当前实现：2026-10-01。规则和采集器已实现；实际启用需要部署对应应用镜像、
现有 Alloy 公网探测及生成的监控配置。默认全部 `automatic`，不将初始 OPERATIONAL 当作健康证据。
字段与生成命令见 [组件发布配置](status-page-publication.md)。

## 三态契约

每组件自定义表达式必须返回一个无标签的 0（健康）、1（异常），或无序列（无法观测）。
非二值、多序列、NaN、缺少必要来源、时间戳过旧/来自未来都不能代表健康。
内置规则在内部另带部分观测标记：已确认的故障仍然成立，但观测完整性和监控心跳必须保留缺口。
scroll-monitor 脚本拥有规则及确认窗口，通过 Prometheus 取证；未知期间重置确认窗口，
保留已有故障，不发送恢复。Grafana 只展示结果和处理内部告警，不控制公开状态。`up=1` 仅说明 scrape 成功，必须同时检查业务快照时间。

## 探测模式

首版选择 `probes.mode: alloy`，复用已有 Alloy，不新增公网探针 Pod。
Public RPC 检查 HTTP JSON-RPC 响应模式和延迟；Bridge/Blockscout 检查页面与 API
入口的 HTTP/TLS 可用性。CLI readiness 标注 `public-entrypoint`，公开说明不再宣称
这些检查证明浏览器功能或索引新鲜度。WebSocket 通过已有 Alloy Pod 内的辅助容器执行实际 JSON-RPC 检查。
官方 Node Sync 模式且连续出块时，Sequencing 复用参考 sequencer 的区块时间；其他模式需要自定义规则。
完整参数和边界见 [Alloy 公网探测](status-page-alloy.md)。

## 八个组件（external 深度探测模式及通用业务规则）

| 组件 | 已实现的判断 | 需要部署方提供 |
| --- | --- | --- |
| Public RPC | 所有公开 HTTP/WS 入口执行 chainId、blockNumber、block 查询；检查返回内容和 p95 请求序列耗时 | 独立探针位置；按链调整耗时阈值 |
| Transaction Sequencing | RPC 观测有效时检查最新区块时间；RPC 故障不能直接归因为排序器故障 | 明确 continuous 出块模式和最大块龄；按需出块需自定义可执行积压表达式 |
| Deposits | 已满足确认的规范链未扫描充值 + 已提交但未被 L2 消费的充值；索引、replay 和 RPC 规范链一致 | 新 WP 镜像、明确处理 deadline |
| Withdrawals | 协议 eligible 的未完成提现索引范围，完整唯一队列与规范 replay；最早 eligibility 时间 | 新 WP 镜像、明确处理 deadline；不是从用户最初交易起算 |
| Batch Publication | pending_publish / submitted / failed 的尚未确认批次，排除已确认、finalized 和归档项 | 新 DA 镜像、包含正常确认时间的 deadline |
| Node Sync | official 模式逐 Pod 比较 bootnode、内部 RPC、公开 RPC 与活跃 sequencer 的同高度 hash 和时间差；参考源失效或成员不完整为未知 | 选择有效 values/release；独立 canary 是可选的 external 模式，见 [Node Sync](status-page-node-sync.md) |
| Bridge Portal | Chromium 渲染充值/提现 UI、检查链身份及充值 payload；在浏览器中验证必要 API 响应 | 默认从 frontend 配置生成 API 类型检查，可覆盖 JSON path/语义；不签名或发起转账 |
| Block Explorer | Chromium 数据选择器 + Blockscout 最新索引块 API；与规范链同高度哈希及块时间比较 | 后端入口（可自动派生）、真实数据 CSS selector、容忍索引延迟 |

external 模式的公开 RPC/网页探测需至少两个独立位置、每个位置数据新鲜有效且结果一致；部分缺失、重复
reporter 或观测分歧进入未知，不能由一台成功探针覆盖另一台失败探针。
位置独立性由实际部署保证，两个同集群副本改名不构成独立位置。
官方 Node Sync 采集器在链内运行，不计入外部探针位置数。

业务规则必须选择完整的实际服务 target 集合及 namespace；配置期望 WP/DA target 数量，
缺失 target 不得降低恢复要求。WP 的 proof-only role 不应混入。
充值完整性检查覆盖中途扫描游标、缺记录、未分类数据、replay 落后和同高度重组。
DA 规则把已提交但未确认的工作保留在积压内，防止离开待发送队列就被误认为完成。
业务队列完全观测且为空时明确输出 0 个、0 秒，不把正常无业务视作故障。

## 当前默认值与可配置项

| 参数 | production 默认 | 含义 |
| --- | --- | --- |
| `health.failureFor` | `5m` | 持续异常确认；组件可通过 `rule.for` 覆盖 |
| `health.recoveryFor` | `10m` | 连续新鲜健康才恢复 |
| `health.freshnessSeconds` | `120` | 底层观测最大年龄 |
| `health.minimumProbeLocations` | `2` | 仅 external 模式使用；Alloy 不冒充两个位置 |
| `health.maxRpcLatencySeconds` | `2` | Alloy 每个 HTTP 探测 / external RPC 查询序列的 p95，需 5 分钟内至少 10 个样本 |
| 最大块龄 / 索引延迟 / 节点落后时间 | 各 `120` 秒 | 部署方按实际链行为确认 |
| 充值 / 提现 / 批次 deadline | `0` | 未配置；不编造业务 SLA，不生成对应内置规则 |
| `components.<key>.affectedStatus` | 无默认值 | CLI 管理的自动发布必须显式配置并审查规则语义；二值规则不能自动推导严重程度 |
| `incidents.notifySubscribers` | `false` | 明确启用后才在模板中请求订阅通知 |

以上是配置默认，不是公开承诺。旧设计讨论的 3/5/10 分钟分级及恢复迟滞不自动
成为现行参数；以生成配置为准。自定义表达式需 `rule.builtin: false` 并遵守同一三态契约。

## 发布和运维边界

每个组件只有一个最终规则及 webhook。多个内部原因必须先合并成组件表达式，
不能让某个原因的恢复覆盖另一项故障。原有内部诊断规则不直接映射公开状态。
校验器持久化当前事件，并在重启、未知、采样中断和时钟回退后重新等待完整窗口。
人工维护/事故接管先部署 manual 模式；已有事故和收据保留。
计划维护窗口与自动发布的联动已后置，放在首版探针部署及真实故障/恢复验收之后。

整个监控集群失联通过 Instatus Cron Monitor 的心跳超时通知内部值班人员。
有投递校验器时心跳同时依赖其新鲜运行和无投递错误。监控失联不自动改所有组件为故障。
真实 Instatus 的模板、重复投递、恢复关联和 subscriber 行为需在测试目标完成首版验收；
维护联动的专项验收随其后续实现进行；
本地测试使用本地 HTTP 接收器，不触发公开事故。

## 采集模板修复与验证

scroll-monitor 的 PodMonitor 发现与 ServiceMonitor 一致按 release namespace/instance
标签选择，覆盖 Blockscout frontend 现有 PodMonitor；eager-materializer example
启用应用自带 ServiceMonitor，不重复创建。没有应用指标端点的 proof coordinator
不能靠添加 ServiceMonitor 修复，保留相关诊断规则暂停。

回归包含真实 Prometheus 表达式求值、CLI 到 Helm 渲染、Grafana 11.1.5 通知格式、
浏览器渲染/接口故障、投递重启与未知期间禁止恢复、业务数据库完整性与重组。
完整部署验收步骤见 [rollout](status-page-rollout.md)。

## WF 停滞影响充值和提现

充值与提现的内置规则同时检查 WF。`health.wfStallSeconds` 默认 3600 秒，
使用 core 的只读 `withdrawal_processor_public_workflow_*` 快照，以及 jobs 来源的
有效性与时间戳，不再查询 Pod IP 的一小时 Prometheus `offset` 历史。
存在超过时限的 queued、building、built、failed_retryable、bug、proposed_to_tso 或
awaiting_replay 工作，且 core 连续观测同一 canonical WF 头超过时限，才确认停滞。
历史 completed / failed_terminal 行不参与；空闲或任务尚未超时可立即判断 WF 正常。
近期 canonical 头的首次观测时间由 replay 持久化，新进程也可使用这一正向进展证据。
这不是 scrape 时间，重复读取不会刷新它。

连续停滞时间由 core 的单调时钟计算。读取失败、超过 45 秒的采集空档、头身份改变
（包括同高度重组）、时钟倒退或进程重启都会重新开始计时。重启后，如果旧任务已经
超时且没有近期进展证据，仍需等待连续观测；不得把重启前未观测的时间算成停滞。
缺少新 workflow 指标的旧 core 为 unknown，部署时必须先升级 core，再重新生成 CLI 配置。

WF 快照自身有效且明确停滞时，两项组件均输出 affected，即使单独的充值或提现
队列快照无效。全局一致性检查失败会使 workflow 快照一并无效，不可借旧值发布故障。
业务积压超时本身也可独立判为 affected。只有 WF 与业务快照都证明正常，才允许恢复；
缺失指标不会以 0 替代。正常故障确认窗口 `failureFor`（默认 5m）及恢复窗口
`recoveryFor`（默认 10m）继续适用，因此默认 WF 停滞需持续约 65 分钟后发布。

新模板及省略 mode 的组件默认 automatic。顶层 statusPage.enabled 仍需显式启用；
自动模式缺少业务时限、健康表达式、heartbeat 或明确严重程度时，CLI 报错，
不会静默降级为 observe。既有配置中显式 observe 需要主动迁移。
充值和提现示例明确采用 MAJOROUTAGE；二元规则尚不能区分 WF 全停与部分请求超时，
需要更细严重程度时应提供经过评审的自定义规则和策略。
