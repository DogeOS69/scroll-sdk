# DogeOS 公开状态页健康规则 v1

状态：设计与采集模板修复，尚未启用公开告警。本文定义规则语义、第一版建议阈值、证据要求和验收条件；不是已部署的 SLO，也不是可直接导入 Grafana 的规则文件。

范围：每条链一套 DogeOS 集群、Prometheus 和 Grafana；Mainnet / Testnet / Devnet 共用 workspace `6wxpx` 下的 `dogeos` 页面，各自管理自己的组件组。工作目录只属于一条链，阈值和入口由该部署提供。L2Scan 不在本次范围。

## 1. 公开状态的判定原则

1. 判断用户能力是否受影响，内部服务故障用于解释原因。Pod 重启、一个 signer 离线、出现 ERROR 日志，不直接等于充值或提现中断。
2. 将“异常”“正常”“无法观测”分开。缺指标、错误查询、探针失联不能恢复为 Operational；保留最后确认状态，并触发内部监控告警，必要时发布监控异常公告。
3. 没有新请求、正常确认等待、空队列属于正常空闲。业务进度规则必须有符合处理条件的工作；历史完成/失败记录不参与当前积压计算。
4. 一个组件只有一个最终自动发布来源。多个内部原因先合并为组件级异常，再发送，防止原因 A 恢复时覆盖仍存在的原因 B。
5. 初始 `OPERATIONAL` 和页面 uptime 不构成健康证据。启用自动更新前，需完成真实触发与恢复验收；不补造历史。
6. 规则模板跨网络共用，入口、链 ID、工作负载名称、确认深度、正常处理期限和启用范围按部署输入。禁止通过替换域名中的 testnet/mainnet 来推导地址。

## 2. 观测与时间参数

以下为初始工程建议，先影子评估和校准，不自动改变现有内部规则。

| 参数 | 第一版建议 | 说明 |
| --- | --- | --- |
| 外部主动探测周期 / 单次超时 | 30 秒 / 5 秒 | 探测器必须在被测集群故障后仍可运行；超时按接口类型调整 |
| 公共端点观测位置 | 至少 2 个独立位置 | 明确区分“已收到失败结果”和“探针本身没有报告”；一个位置失联不算多数失败 |
| Grafana 评估周期 | 1 分钟 | `for` 是条件连续满足的时间，另有采样、评估和通知投递延迟 |
| 外部报告最大年龄 | 90 秒 | 超过即观测不足；不把长期未更新的成功记录继续当作健康 |
| 内部业务快照最大年龄 | `max(3 × 业务刷新周期, 120 秒)` | 必须使用采集成功时间或业务快照时间，不能只用 Prometheus 样本时间 |
| 普通公开故障持续时间 | 3–5 分钟 | 具体见组件表；安全性异常立即通知值班人员，由人工判断公开影响 |
| 普通恢复确认期 | 连续健康 5 分钟 | 同时要求所有必要观测有效、所有活动原因消失 |
| 业务恢复确认期 | 连续健康 10 分钟 | 除处理恢复，还要求超期积压清空或已回到约定界限 |
| 投递建议 | group_wait 30 秒；group_interval 1 分钟；repeat_interval 4 小时 | 初始值，需用原生集成验证；按网络和组件隔离通知 |

端点维度包含所有承诺对外提供的接口。HTTP RPC 和已启用的 WebSocket 单独观测：HTTP 正常不能掩盖 WS 故障。复制品内部失效但公共负载均衡入口正常，先发内部告警。

## 3. 八个组件的规则

`D_*` 表示从实际配置和健康运行基线确认的最长正常处理期限，必须显式配置；缺少该参数时不启用对应业务自动规则。表中的比例/时间是建议起点，不是已验证 SLA。

| 组件 / key | 异常判定 | 候选公开状态 / 持续时间 | 恢复条件 | 首版自动化准备情况 |
| --- | --- | --- | --- | --- |
| Public RPC / `public-rpc` | 每个公共入口由外部调用 `eth_chainId`、`eth_blockNumber` 和最新区块；校验 JSON-RPC 无 error、链 ID 正确、结果有效。两个健康探针位置均确认某入口失败；部分入口失败而其他入口健康；或两个位置 p95 延迟超过 2 秒且 5 分钟内每位置至少 10 个有效样本 | 所有必需公共入口失败：Major Outage，3 分钟；部分入口失败：Partial Outage，5 分钟；仅延迟高：Degraded Performance，10 分钟。第一阶段自动通道统一发 Degraded，其他等级人工升级 | 所有必需入口连续 5 分钟语义检查成功；p95 小于 1 秒；链 ID 正确。链不出块单独归 Sequencing，RPC 仍须与有效参照高度一致 | 缺独立外部语义探测；Reth 自身请求指标只覆盖请求到达之后的行为，不能替代入口探测 |
| Transaction Sequencing / `sequencing` | 在持续出块模式下，外部观测最新块时间距现在超过 `max(10 × blockPeriod, 120 秒)`；在按需出块模式下，有已接受且可执行的待处理交易，但纳入时间超过 `D_inclusion`。必须先确认 RPC 观测路径有效 | 停止出块：Major Outage 候选，3 分钟；仍在出块但交易纳入明显变慢：Degraded，5 分钟。仅一个观测 RPC 坏掉不判排序器故障 | 新区块连续推进 5 分钟且时间恢复正常；若由纳入延迟触发，还需新测试交易成功纳入并排空超期可执行队列 | 已有 Reth 高度指标；缺完整外部块时间与可执行交易年龄证据。出块模式、正常周期必须由链配置确认 |
| Deposits / `deposits` | 存在已满足确认、规范链及处理前置条件的充值，最老 eligible age 超过 `D_deposit`；只计算尚未到账的当前充值。索引器原始 tip 差不能代替充值延迟 | Degraded，超期连续 10 分钟；确认整个充值路径停止才由人工升级 Major | 超期充值全部完成或经人工确认排除，且业务观测连续有效、处理正常 10 分钟。孤立成功一笔不能恢复整个组件 | 现有充值状态计数及 relayed index 不能给出 eligible age；需要应用增加资格判定后的积压年龄和快照成功时间。先人工维护 |
| Withdrawals / `withdrawals` | 存在已到处理阶段、仍未完成的提现，最老 eligible age 超过 `D_withdrawal`；协议等待和 Dogecoin 最终确认窗口不算处理超期。结合 active job/proof/signing 的证据定位 | Degraded，超期连续 10 分钟；确认全路径停止才人工升级 Major | 超期提现清空，处理继续推进，业务观测正常 10 分钟；不能只看一个 WP Pod Ready | 已有 acknowledged backlog、oldest L2 block、WF job/proof age；仍缺完整的按处理资格计时的提现年龄，不能直接将 job age 等同用户提现年龄。先人工维护 |
| Batch Publication / `batch-publication` | 同一发布者存在 `ready_backlog > 0` 且 `oldest_ready_age_seconds > D_publish`；D_publish 需覆盖批次聚合间隔和正常发布/确认重试。没有待发布批次时允许长时间无发布 | Degraded，5 分钟；安全边界事件立即内部告警并人工评估影响，不由错误计数直接标全网中断 | 所有发布者不存在超期 ready 队列，业务观测正常 10 分钟；新工作能继续发布 | 原生 backlog/age 已存在，可作为第一批内部候选评估。自动发布还需业务快照新鲜度、正常期限和 recovery 测试 |
| Node Sync / `node-sync` | 独立的、使用受支持版本/配置的跟随节点，在有有效链参照且上游确实推进时，落后时间超过 `D_sync`；本地节点资源与网络故障先排除。建议至少两套独立观测节点交叉确认 | Degraded，10 分钟；确认所有受支持的同步路径不可用才人工升级 Major | 独立观测节点持续推进，落后回到恢复界限，连续 10 分钟 | 内部 reth peer/head/derivation 指标只能诊断当前节点；需要独立同步观测，不能用单个 bootnode 的 peers=0 代替。先人工维护 |
| Bridge Portal / `bridge-portal` | 外部浏览器能加载 `/bridge`、关键脚本和正确网络配置；必要 API 返回有效结构。两个位置均确认关键访问流程失败。只测首页 200 不够 | 页面整体无法使用：Major 候选，3 分钟；仅一个必要 API/功能受损：Partial 候选，5 分钟。第一阶段自动通道统一 Degraded | 页面、关键资源及必要 API 连续 5 分钟成功；充提处理仍由独立组件表示 | bridge-history-api/fetcher 已有原生采集；缺外部浏览器/API 合成探测。无需连接用户钱包或发起资金交易 |
| Block Explorer / `block-explorer` | 分别测 frontend 和必要 API；使用有效独立链参照比较最新**已索引**块的时间。索引延迟超过 `max(10 × blockPeriod, 120 秒)`，或两个位置确认网站/API 失败 | 索引滞后：Degraded，10 分钟；整体访问失败：Major 候选，3 分钟。第一阶段统一 Degraded | frontend/API 成功 5 分钟；索引延迟低于 `max(3 × blockPeriod, 30 秒)` 且连续推进 10 分钟。参照 RPC 失联时不能自动恢复 | 后端 ServiceMonitor 已有；本次补上 frontend PodMonitor 的发现。原生运行指标不等于完整索引新鲜度检查；缺外部语义探测 |

RPC 的 2 秒/1 秒延迟门限应按地域和接口基线校准。表中高度/时间规则必须排除未来块时间、错误链 ID 和无效参照；至少两个独立有效来源才能区分单个 RPC 陈旧与整条链停止推进。需要发送测试交易时另行设计专用限额账户及交易策略，当前采集模板不包含私钥或交易行为。

## 4. 现有指标可以支持什么

源码核对基线：本地 dogeos-core `83eb01b38`、dogeos-rollup-node `d3260af`、当前 SDK 的 Helm 模板及缓存的 Blockscout chart `2.2.0`。这证明这些源码/模板的能力，不证明任何具体链已经部署这些版本。发布前应以实际镜像的指标契约为准。

| 已有信号 | 归属 | 使用限制 |
| --- | --- | --- |
| `reth_blockchain_tree_canonical_chain_height`，Reth RPC 延迟/错误、derivation 队列 | Sequencing / RPC / Node Sync 辅助 | 指标新鲜不等于块新鲜；要求按角色选 job，并以 namespace/job/instance 保留观测边界 |
| `withdrawal_processor_protocol_deposit_count{status=...}`、`withdrawal_processor_protocol_state_next_relayed_deposit_index` | Deposits 辅助 | 不随意假设 status 值和处理资格；计数/索引没有“正常等待之后的最老未完成时间” |
| `withdrawal_processor_protocol_state_unfulfilled_withdrawal_count`、`withdrawal_processor_withdrawal_oldest_unfulfilled_l2_block` | Withdrawals 辅助 | acknowledged backlog 不等于所有可处理用户提现；需要块时间及协议资格才能计算用户延迟 |
| `withdrawal_processor_protocol_job_oldest_age_seconds`、proof work age/count | 业务故障定位 | 区分 active/terminal、签名/证明/回放阶段，历史终态不作为当前积压 |
| `eth_da_publish_ready_backlog`、`eth_da_publish_oldest_ready_age_seconds` | Batch Publication | 按同一发布者关联，不将一个实例的队列与另一个实例的年龄配对；正常空队列不报警 |
| `withdrawal_processor_protocol_metrics_scrape_errors_total` | 观测质量 | 业务读库失败时可能留下旧 gauge；HTTP scrape 成功不足以允许公开恢复 |
| `withdrawal_processor_eth_da_inbox_worker_last_observed_timestamp_seconds` | WP 的 DA inbox ingestion 新鲜度 | 只证明这个子流程最近观测过成功 ingest tick，不能代表整个充值/提现业务快照 |
| TSO signer/quorum/signing cycle、CubeSigner readiness、L1 replay/indexer | 根因诊断 | 没有用户影响证据时保持内部；短时 quorum/确认等待不直接改公开组件 |
| `eager_materializer_ready`、`eager_materializer_chunks_failed_total`、`eager_materializer_chunks_abandoned_total` | 预计算优化诊断 | coordinator 可走 fallback，单独失败不代表公共能力失效；无新任务时 last_bundle 不变正常 |
| kube-state-metrics、容器资源、Loki | 所有服务的运行线索 | 用于缺失目标、未就绪、资源和日志排查，不作为组件恢复的唯一依据 |

例如，DA 的**内部候选表达式**如下，namespace/job selector 和期限需由部署填入，不能直接粘贴占位符运行：

```promql
(eth_da_publish_ready_backlog{namespace="<namespace>",job="<da-job>"} > 0)
and on (namespace, job, instance)
(eth_da_publish_oldest_ready_age_seconds{namespace="<namespace>",job="<da-job>"} > <D_publish_seconds>)
```

该表达式仅识别业务异常；还缺快照新鲜度/采集完整性条件，不能直接作为自动恢复规则。实例级异常应先根据 active/standby 角色筛选，再汇总为一个组件结果。不能用 `max(ready)` 让健康实例掩盖唯一活跃发布者的故障。

## 5. 观测状态、故障和恢复

组件评估输出逻辑采用三态：

```text
必要来源缺失、过期或查询失败 → UNKNOWN（内部观测故障，不发送 Operational）
必要来源有效，任一用户影响条件持续达到故障门限 → AFFECTED
必要来源有效，所有影响条件消失并满足恢复确认期 → HEALTHY
```

UNKNOWN 不能用 `or vector(0)` 转成健康，也不能只因为 Prometheus 正常抓到了 exporter 就忽略 exporter 内部的陈旧业务值。维护状态由运维控制，不让一条 resolved 通知覆盖 Under Maintenance 或人工事故。

当前 `seed-grafana-alerts.py` 面向内部“过滤式 PromQL”：有返回序列就视为异常，`noDataState=OK`，表达式 B 使用 `$A * 0 + 1`。**不能直接把这个生成器用于公开健康规则：正常、缺数据都可能是空向量，而返回数值 0 也会被转成告警。** 后续需独立的公开规则构造器：有效观测时稳定输出明确的 healthy/affected 值，真正缺数据进入 Keep Last State / 独立 No Data 通知，明确比较异常值，并单独验证缺失告警实例的处理。当前 Grafana 版本须验证这些策略，不能只改一个 noData 参数就声称已修复。

通过一条按组件汇总的最终规则发送 firing/resolved，恢复确认期在健康评估中实现；仅设置 Grafana 的 firing `for` 不会自动获得对称的恢复等待。原生集成能否准确保持该行为要通过验收；在验证完成前使用人工确认恢复。

## 6. Instatus 发布映射

每链独立 Grafana，仍然需要在同一网络组内区分组件。现有单个 `instatus-public` 和 `components: []` 集成只是初始化出口，不能把它关联全部 8 个组件后转发所有告警，也不能假设任意 `component` label 会被 Instatus 自动解析。

第一版映射设计：**每条链的每个自动组件一个独立 Grafana integration/contact point**，静态绑定该组件 ID；一个组件的多个内部原因先合并，再发送一个最终告警。示例命名 `instatus-public-rpc`、`instatus-batch-publication`。三条链可用同样的本地名称，URLs 和组件 IDs 各自独立。

这是下一阶段自动化的扩展目标，**当前 CLI 仍只生成单个初始化 contact point，不会因为本文自动创建 8 个 webhook**。Secret 文件仍放在本链工作目录的 `secrets/status-page/`，未来按组件分文件/key，不按网络再套目录。

建议最终规则标签：`audience=public-status`、`environment`、`component_key`、`chain_id`；值从部署生成。内部监控异常使用独立 audience，不进入组件状态更新。公开通知只包含网络、组件、影响摘要和更新时间，不携带 Pod 名、内部地址、账户余额、凭据或原始错误栈。

一期自动化只使用一个确认过的失败等级（建议 Degraded Performance），恢复到 Operational；严重中断、部分中断、维护和安全事件先人工处理。多等级自动切换需要验证 Instatus 模板/集成能力，不能并行发两条不同等级的自动恢复规则导致互相覆盖。人工接管期间须停用该组件的自动恢复/发送，结束后重新确认健康再恢复自动管理。

## 7. 整个集群或 Grafana 失联

集群内 Grafana 无法在自身宕机时可靠发布异常。独立外部观测必须能直接通知值班人员；若其与内部 Grafana 同时管理同一组件，必须明确唯一恢复权，不能让外部 RPC 成功覆盖内部确认的业务故障。

建议独立监控从每链接收周期心跳，预期 60 秒一跳，连续 3 分钟未到内部告警、5 分钟人工发布监控受限公告；这是待部署能力，不是当前已有 exporter。心跳只证明监控投递链路活着，不证明业务健康。外部 synthetic 可直接判断公开入口故障；充值、提现等内部状态在观测失联时保留最后确认状态并明确标注观测受限。

## 8. 通用采集模板审计与本次修复

| 服务/来源 | 当前模板证据 | 本次处理 |
| --- | --- | --- |
| TSO | 应用 chart 默认不建 monitor；当前 scroll-monitor 已补充 `/metrics`、http port、30 秒抓取 | 保留已有修复。应用接管 monitor 时关闭补充项，保持唯一采集 owner |
| Reth RPC/Sequencer/Bootnode | production examples 具有 `/debug/metrics/prometheus`；渲染后的 RPC selector 与 Service 标签匹配，包括 Service fullname override | 添加回归测试；不将旧部署漂移误当作当前模板缺陷 |
| WP / L1 Interface / DA submitter / CubeSigner / Fee Oracle | 已有 application-owned monitor；WP、DA 的 production 配置分别给出实际路径/端口 | 保留唯一 owner；按实际部署版本检查指标可用性，未部署的可选服务不能按缺指标判公开故障 |
| Bridge history API/fetcher | 应用 chart 已有 metrics port 的 ServiceMonitor | 保留；补外部语义探测属于后续观测能力，不伪造 frontend `/metrics` |
| Blockscout backend | upstream `blockscout-stack 2.2.0` 已有 `/metrics` ServiceMonitor | 不重复创建 |
| **Blockscout frontend** | upstream 已有 `/node-api/metrics` PodMonitor，但原 Prometheus 默认 selector 要求 `release=scroll-monitor`，该 monitor 不带这个 label | **修复 scroll-monitor 默认及两份 production 示例：PodMonitor 按 Helm instance label 发现，并限定当前部署 namespace** |
| **Eager materializer** | 源码提供 `/metrics` 和真实 recorder，生产示例未启用 application-owned ServiceMonitor | **生产示例开启 http port、`/metrics`、30 秒采集；保留基础 chart 默认关闭以兼容没有 CRD 的独立安装** |
| Proof Coordinator | 当前核对源码的 prover API 只有 health/readiness 和业务路由；没有生产 metrics recorder 或 `/metrics` | **不是模板能修好的缺口**。不新增必然失败的 scrape；现有 Kubernetes readiness 和日志先用于诊断。待应用提供真实端点再加 monitor，旧诊断规则保持暂停 |
| 外部 Attestation Signers | 有原生指标，但地址/网络属于部署；README 已给出 additionalScrapeConfigs 入口 | 模板不得写固定 IP；生成实际 endpoints 后验证每实例 up/业务 readiness，未配置不能当作 healthy |
| 外部 RPC/Bridge/Explorer 观测 | 当前没有完整独立语义/浏览器探测链路 | 列为启用自动公开规则前的前置能力。Blockscout 自带 blackbox ServiceMonitor 也只选择另行部署的 exporter，本身不安装探测器 |

新 PodMonitor selector 的作用域与现有 ServiceMonitor 一致：只发现本 namespace 带 Helm instance label 的监控资源。一个 namespace 应只属于一条链；同 namespace 共用多条链不在本设计中。外部 Prometheus 用户需要在其自身配置中采用相应 selector。

## 9. 验收与实施顺序

先补齐采集，再运行候选规则的内部评估，最后开启公开通知。建议先覆盖 RPC、Bridge Portal、Explorer 和 DA publication；充值/提现及 Node Sync 在证据不足时保持人工维护。

| 场景 | 必须得到的结果 |
| --- | --- |
| 没有交易、没有充值提现、DA ready 队列为空 | 不以计数/高度长时间不变直接判业务失败；按实际出块模式判断 Sequencing |
| 一个 Pod/一个 signer 失败，但用户请求和整体 quorum 正常 | 内部告警；公开组件不因单实例告警自动降级 |
| 正常确认窗口造成 indexer tip 差 | 不作为充值超期或全网故障 |
| 有超过正常期限的真实待处理工作 | 对应组件出现一个告警；其他网络、其他能力不受误更新 |
| HTTP 200，但 RPC error、错误 chain ID、陈旧缓存、桥接 JS/API 失败 | 语义观测判失败，不能绿灯 |
| 一个探针报告失败、另一个成功 | 内部调查地域/路径问题；未满足对外判定条件时不报全局中断 |
| 探针停止报告、指标消失、exporter 返回旧 gauge、Prometheus 查询失败 | 进入观测异常，不发送健康恢复 |
| 异常持续时间不足 / 恢复不足确认期 | 不切换公开状态，避免抖动 |
| 同一组件原因 A、B 同时存在，仅 A 恢复 | 组件仍受影响；直到全部活动原因消失才允许恢复 |
| Grafana/整个集群退出 | 独立外部通道仍可发现并通知，公共页面不能无说明地长期保持“刚确认正常” |
| 维护、人工事故、重复 webhook、延迟/乱序 resolved | 不覆盖人工状态，不重复创建事故，不因旧 resolved 错误恢复；无法保证时保留人工恢复 |
| 三链同时告警、重复部署、组件配置重建 | 仅更新对应环境/组件；保留现有状态和事故，不新增重复页面 |

本次自动化测试覆盖采集资源的真实跨 chart selector/port/path 匹配与 namespace 隔离；不声称已验证线上应用或上述故障演练。本次不修改任何具体链的工作目录、不部署 Helm、不向 Instatus 发送告警。

参考：[Prometheus Operator 监控资源定义](https://prometheus-operator.dev/docs/api-reference/api/)、[Grafana No Data/Error 行为](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/nodata-and-error-states/)、[Instatus Grafana 接入](https://instatus.com/help/integrations/grafana)。原生接入文档仅说明 contact point 和路由连接，不应据此推断多原因聚合、自动分级或乱序恢复已有保证。
