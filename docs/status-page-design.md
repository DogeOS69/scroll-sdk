# DogeOS public status page design

当前实现状态及启用条件以 [组件发布配置](status-page-publication.md) 为准；本文中的页面预览和早期只读采样是设计记录，不代表当前线上健康。

日期：2026-09-26。状态：设计草案，未创建或修改 Instatus 资源，未启用公开告警路由。

配套 [可交互页面预览](status-page-preview.html) 可直接用浏览器打开，切换正常、提现延迟、RPC 中断、监控失联、维护和事故恢复场景。所有状态均为演示；没有真实历史、百分比或订阅投递。预览展示信息结构和视觉方向，生产使用 Instatus 原生页面，不部署这个 HTML 为另一套状态页服务。

## 设计结论

采用面向用户能力的组件命名，复用 workspace **DogeOS (`6wxpx`)** 中的 **dogeos.instatus.com**，按 **Mainnet / Testnet / Devnet** 分组。每组包含 6 个网络组件、Bridge Portal 和当前部署的 Blockscout，共 8 个组件，三网完整接入后共 24 个。L2Scan 由用户明确排除在本次范围之外，后续单独设计。公开页面使用英文。

用户最新决定为三网共页，替代此前 Testnet 独立页面方案。每个工作目录仍只对应一个网络，分别生成该组的组件、地址和 webhook。上线时核实各网络实际部署与公开地址；预览中的状态均不证明真实健康。

页面回答四个问题：现在能否使用、哪项能力受影响、用户需要做什么、何时再次更新。默认不展示 TPS、区块高度、资金余额、内部拓扑或原始监控曲线。

## 环境与地址来源

状态页组件描述的是能力，URL 属于部署环境。**Bridge Portal 的地址以用户选定工作目录中的 `frontends-production.yaml` 为准**；当前工具生成的目录布局通常为 `<工作目录>/values/frontends-production.yaml`。读取 `ingress.main.hosts[].host`，结合部署使用的协议与前端路由形成 Bridge URL，当前前端路由为 `/bridge`。不能把 `portal.testnet.dogeos.com` 写成生成器或通用模板常量。

同样的能力可部署在 Testnet、Mainnet、Devnet，但各环境有自己的 Portal、RPC、Explorer、链身份和 Instatus 组件组、独立 webhook；共享同一个页面 ID。环境名称由部署选择明确提供，不能通过域名字符串推断，更不能通过替换 `testnet` 为 `mainnet` 来猜测 URL。

本次读取到的 Testnet values 与用户确认的 `https://portal.testnet.dogeos.com/bridge` 一致。这个 URL 是本页预览的 Testnet 示例数据，不是跨环境配置契约。生成器已有从 `spec.frontend.hosts.frontend` 写入 frontend ingress，以及从 `config.toml` 的 `ingress.FRONTEND_HOST` 更新它的路径，无需增加一套独立的 Portal 域名字段。

RPC 应取同一部署的有效公共入口；存在旧文件、多个 hosts 或禁用 ingress 时不能默认选第一个。本次 Explorer 明确为当前部署的 Blockscout，地址取 `blockscout-production.yaml` 的 `blockscout-stack.frontend.ingress.hostname`，不从文档推荐链接替代部署配置。

具体字段、只读核实结果和接入顺序见 [部署接入说明](status-page-rollout.md)。

## 参考依据

| 参考 | 当前可见信息 | DogeOS 采用方式 |
| --- | --- | --- |
| [Arbitrum](https://status.arbitrum.io/) | 按 ARB1、NOVA、SEPOLIA 分组；组件包括 Sequencer、Batch Poster、Validator、Feed，部分网络含 Arbiscan | 按网络分组，保留批次发布与网络同步能力；不照搬并不等价的 Validator / Feed 名称 |
| [Optimism](https://status.optimism.io/) | Mainnet、Sepolia 分组；Public API、Deposits、Withdrawals、Transaction Sequencing、Batch Submission、Node Sync | 主要采用其面向用户的能力粒度，明确区分交易、充值、提现及节点同步 |
| [Instatus components](https://instatus.com/help/status-page/components) | 组件、分组、排序和可用性历史可原生配置 | 使用供应商原生页面；自动恢复由内部投递校验器核实 |

两家当前均使用 Instatus，展示可用性历史及事故记录。公开页面无法证明它们内部采用了哪种采集或发布实现。以上页面在本次设计时读取，组件可能随运营调整。

## 页面结构与视觉

页面名称 **DogeOS**，使用已选定的 `https://dogeos.instatus.com/`；自定义域名按实际域名所有权和配置确定，不把候选域名当作已开通。

```text
DogeOS                                            Subscribe to updates
Service availability for Mainnet, Testnet and Devnet.

[Overall status]
[Active incident: impact, affected network/components, latest update]

[Mainnet]                                            Current status
  Public RPC                      Status + optional uptime history
  Transaction Sequencing          Status + optional uptime history
  Deposits                        Status + optional uptime history
  Withdrawals                     Status + optional uptime history
  Batch Publication               Status + optional uptime history
  Node Sync                       Status + optional uptime history
  Bridge Portal                   This network’s official bridge website
  Block Explorer                  Deployment-owned Blockscout

[Testnet] — same 8 components, independent status and URLs
[Devnet]  — same 8 components, independent status and URLs

[Scheduled maintenance]
[Recent incidents / incident history]
[Official website / Documentation / Support]
```

- 窄栏、白底、深色文字、细分隔线。使用 [DogeOS 官方品牌库](https://github.com/DogeOS69/web-images) 的完整 logo 和 favicon；白字 logo 可在控制台配置给深色模式。
- 绿色表示正常、黄色表示性能下降、橙色表示部分中断、红色表示严重中断，维护用蓝色。所有状态同时提供文字，避免只依赖颜色。
- 事故置于组件列表上方；按受影响网络和能力描述，不让用户先翻日志或内部组件列表。
- 按 Mainnet、Testnet、Devnet 顺序展示原生组件组。顶部总状态可能受任一组影响，因此事故标题必须明确网络；例如 “Testnet — Public RPC unavailable”，不能把测试网故障写成主网故障。三组在控制台初始化一次，CLI 后续只管理当前环境组内的组件。
- 顶部订阅入口使用 Instatus 原生订阅。页脚只填写已确认的正式链接；首次提供邮件订阅，其他通道按账户能力和运营需要开启。
- 时间使用明确时区的时间戳；事故应记录实际影响开始时间、每次更新和恢复时间。演示页面中的维护与历史占位不代表真实事件。

健康判断、故障/恢复窗口和采集缺口详见 [健康规则 v1](status-page-health-rules.md)。该设计尚未启用公开告警；组件初始正常状态不代表完成健康验证。

## 组件目录与公开英文说明

本表定义公开组件目录。CLI 将同一组 8 个 key 生成为 `statusPage.catalog`，`--apply` 用其创建或更新 Instatus 组件；真实 component ID 由 Instatus 分配并保存。自动化入口与模板字段见 [配置生成与应用](status-page-automation.md)。

| 顺序 | 公开组件名 / 本地 key | 可直接填写的英文说明 | 范围 |
| --- | --- | --- | --- |
| 1 | Public RPC / `public-rpc` | Availability of official DogeOS HTTP JSON-RPC and enabled WebSocket interfaces for network queries, transaction submission and subscriptions. | 同一部署的公共 RPC 入口；Testnet 当前核实为 `https://rpc.testnet.dogeos.com/`，同时覆盖该部署已启用的 WebSocket 入口，不包含其他第三方 RPC |
| 2 | Transaction Sequencing / `sequencing` | Inclusion of accepted transactions in new DogeOS blocks. | 排序与出块；不表示 Dogecoin 侧结算已完成 |
| 3 | Deposits / `deposits` | Processing of DOGE deposits from Dogecoin to DogeOS after the required confirmations. | 充值实际处理，不包括用户尚未满足的正常确认等待 |
| 4 | Withdrawals / `withdrawals` | Processing of DOGE withdrawals from DogeOS to Dogecoin, including protocol processing and confirmation. | 提现完成链路；正常协议等待不算事故 |
| 5 | Batch Publication / `batch-publication` | Publication of DogeOS batch data to the configured data availability layer. | 当前仓库为 Ethereum DA 路径；不等同于 Dogecoin 最终结算，也不作数据安全保证 |
| 6 | Node Sync / `node-sync` | Availability of the network data and services needed for supported DogeOS nodes to synchronize. | 支持的节点同步/派生路径；不包含单个用户自建节点的本地配置问题 |
| 7 | Bridge Portal / `bridge-portal` | Availability of the DogeOS bridge portal and its supporting API. | [portal.testnet.dogeos.com/bridge](https://portal.testnet.dogeos.com/bridge)；页面/API 访问与充值、提现处理分开 |
| 8 | Block Explorer / `block-explorer` | Availability and indexing freshness of the DogeOS Blockscout explorer. | 当前部署的 Blockscout；域名来自 `blockscout-production.yaml`，网页能打开但索引明显滞后仍可降级 |

Bridge Portal 的入口已由用户确认，并与 [DogeOS 官方部署教程中的 bridge 链接](https://docs.dogeos.com/en/developers/guides/contract-deployment-tutorial)一致。该确认仅明确组件对应的网站，不代表已完成充值、提现链路健康验证。

建议网络组件统一开启原生历史展示，但不导入虚构的上线前历史或手填 100%。从正式公开记录开始积累。Instatus 的默认 90 天 uptime 基于其事故时段计算，部分中断有权重，性能下降不扣减 uptime；这不是 Prometheus 采样成功率或独立 SLO。详见 [供应商计算说明](https://instatus.com/help/status-page/uptime-colors)。预览因此仅展示灰色历史占位，不编造百分比。

TSO、CubeSigner、proof-coordinator、withdrawal-processor、L1 Interface、数据库、Kubernetes 和各资金账户维持内部监控。它们可以影响多个公开能力，但不能仅因一个 Pod 或 signer 异常就把整个网络标红。第三方 Dogecoin/Ethereum 故障若实际影响 DogeOS，更新受影响的 DogeOS 组件，并在事故说明中引用已确认的依赖事件。

## 状态和事故语义

| 组件状态 | 对外含义 | 示例 |
| --- | --- | --- |
| Operational | 能力按已确认的正常范围提供，观测足以支持判断 | 公共 RPC 正常返回且链数据新鲜 |
| Degraded Performance | 仍能完成操作，但持续明显变慢 | 提现仍推进，已满足前置条件的请求超过正常处理预算 |
| Partial Outage | 确认部分用户、请求或入口不可用 | 部分 RPC 区域或支持的方法不可用 |
| Major Outage | 该组件覆盖的能力整体不可用 | 所有官方 RPC 入口不可用；不等于所有链上能力都中断 |
| Under Maintenance | 已公布维护窗口内该组件受到计划内影响 | 官方 Bridge Portal 升级；无影响维护不把整个网络降级 |

组件严重程度与事故进度分开：事故进度使用 Investigating → Identified → Monitoring → Resolved。确认恢复并观察稳定后才 Resolved。多个组件受同一根因影响时用一个事故说明影响范围，逐个更新受影响组件，不生成多条重复公告。

无数据、采集失联或发送端失联不能转换成 Operational。先告警给内部值班；必要时人工发布“状态验证受限”的调查公告，明确哪些能力无法确认，不臆造整网故障。Instatus 若没有独立 Unknown 组件状态，不新增一个假定存在的枚举；保留最后确认的状态并在公告中说明其时效。预览的监控失联场景用公告说明这个限制，不以绿色总横幅暗示刚刚验证正常。

## 从现有监控到公开状态

以下是设计映射，尚未启用路由或确认生产信号。现有服务规则中很多默认暂停，存在不代表已在生产运行。依据为 [业务告警评审](../charts/scroll-monitor/ALERTING_REVIEW.md) 与 [服务告警评审](../charts/scroll-monitor/SERVICE_ALERT_REVIEW.md)。

| 公开组件 | 已有内部候选信号 | 自动化前还需要什么 |
| --- | --- | --- |
| Public RPC | `L2RethRPCErrors`、`L2RethRPCSlow`、节点/入口健康 | 从集群外检查公开 HTTP/已启用 WebSocket 的 DNS/TLS、JSON-RPC 语义、订阅及数据新鲜度；区分无效客户端请求与服务错误 |
| Transaction Sequencing | `L2RethHeadStalled`、payload validation、交易队列 | 明确 sequencer 节点角色；按真实出块策略判断停滞，必要时结合待处理工作，不能拿任意 follower 停滞等同于停止排序 |
| Deposits | Dogecoin indexer、L1 Interface 和 WF 进度 | 充值生命周期/最老合格待处理项年龄，扣除正常确认等待；目前先人工确认公开影响 |
| Withdrawals | `WFJobStalled`、proof pipeline、TSO signing progress | 提现生命周期和可处理队列年龄，区分证明/签名/广播/正常确认阶段；目前先人工确认公开影响 |
| Batch Publication | `EthDAPublishBacklogStalled`、提交失败和 readiness | 待发布工作确实存在、最老待发布年龄、实际确认进度及环境发布预算；空闲时没有新批次不是故障 |
| Node Sync | `L2RethDerivationStalled`、peer/download、L1 Interface | 区分公共同步路径、健康参照节点与单节点问题；验证从公开接口同步的实际结果 |
| Bridge Portal | 前端、bridge history API 及基础设施信号 | 从外部打开页面并校验关键 API/网络配置；页面成功加载不证明充提成功 |
| Block Explorer | Blockscout/indexer 的部署健康 | 外部页面/API 语义检查，并将索引高度与同一网络已确认参照比较 |

`DogecoinIndexerLag` 的当前判断包含“已处理高度一段时间未变化”，可能由没有新 Dogecoin 区块或确认策略引起，不能直接用作充值、提现公开中断。`L2RethHeadStalled` 同样需要确认角色及出块模式。低余额、单次错误、单个副本失败、安全边界告警也不直接等价于公开 SLA 失败；实际安全事件的公开表述由事件负责人核实。

官方 [Testnet Bridge 指南](https://docs.dogeos.com/en/getting-started/user-guide/bridge)当前说明充值与提现处理可能需要最多约 4 小时，并标注为早期测试网实现。这是当前文档中的用户预期，不能直接作为新版本已承诺的 SLA；也不能把内部 15 分钟任务告警直接变成公开的充值或提现故障。先按实际部署版本核实正常流程和计时起点。

本稿不把现有内部数值阈值声明为对外 SLA。后续按网络分别确认 RPC 错误率/延迟、批次发布时间预算、充值/提现正常时间范围、触发持续时间和恢复观察窗口，应用已实现的公共规则；配置默认及实际覆盖见 [健康规则](status-page-health-rules.md)。

## 通知和发布方式

当前 [实现架构](status-page-architecture.md)：Prometheus → Grafana 公共状态规则 → 投递校验器 → Instatus 原生 webhook。校验器提供独立恢复窗口与持久化投递，不把内部 Prometheus 暴露给供应商。外部探测是观察已经公开的用户入口，不是让 Instatus 读取我们的私网监控。

- 内部诊断告警继续发给内部接收端；新增公开规则应只保留网络、公开组件和可公开文案，不携带 Pod/IP、钱包、RPC 凭据、内部 URL、日志或请求内容。仅更改通知模板不保证 webhook 中所有 labels/annotations 都被过滤，必须检查实际 payload。
- 建议在 Grafana 将一个网络/组件的多个原因聚合成一条公共状态规则，使用稳定标签如 `status_page=dogeos`、`network=<actual-network>`、`public_component=withdrawals`。评估聚合时考虑信号新鲜度；不得把缺失序列作为健康。
- 初期可用一条聚合规则对应一个公开严重程度；升级/降级和跨组件事件由人工协调。不要把每个内部告警分别绑定同一组件并让任意 resolved 消息自动恢复它。
- 先在测试页面验证供应商对同时 firing、部分 resolved、重复通知、分组及维护的行为。默认校验器已处理本地三态及恢复窗口；供应商行为仍需测试页面验收，未验收组件保留 observe。
- 若供应商不能从通知内容可靠选择目标组件，可给不同组件建立独立原生集成和 contact point。不要预设一个 webhook 必然支持任意动态映射。真实 ID/URL 只在接入时生成；具体方式以目标账户联调结果为准。
- 运行密钥仍只需生成的 webhook URL，放入 Kubernetes Secret；不使用通用管理 API key。暂不改 production 的告警路由，也不为未确定的组件预写凭据引用。

## 对外事故文案

以下仅为写作模板，不是已发生事故。填入已核实的网络、影响时间和下一次更新时间。

**Withdrawal processing delays — [Network]**

> Investigating — We are investigating delays affecting DOGE withdrawals from DogeOS to Dogecoin. [Describe the confirmed affected scope.] Our next update will be provided by [time and timezone].

> Identified — We have identified [confirmed cause at a user-appropriate level] and are working to restore normal withdrawal processing. [State any verified user action, or say that no action is required only if confirmed.] Next update: [time and timezone].

> Monitoring — Withdrawal processing has resumed. We are monitoring queued requests and recovery. [Include confirmed backlog progress if available.] Next update: [time and timezone].

> Resolved — Withdrawal processing has returned to normal. The incident affected [confirmed scope] between [start] and [end]. [State any remaining exceptions and follow-up.]

不默认写“资金安全”“所有交易都已完成”“充值和交易完全不受影响”或固定恢复 ETA；这些都需要事实确认。单条公告应包含用户影响和下一次更新时间，而不是直接复制内部告警名称。

## 完整性核对

以下区分设计覆盖与运行状态，不能把本地预览当作已经上线。

| 内容 | 设计/预览 | 真实接入状态 |
| --- | --- | --- |
| 三网分组、每组 8 个公开组件和说明 | 已覆盖 | 远端页面尚未配置 |
| HTTP RPC 与已启用的 WebSocket | 纳入同一个 Public RPC 组件；仅一种协议受影响可表达部分中断 | HTTP 已做只读采样；WebSocket 尚未验证 |
| 当前事故、受影响范围、进度与带时区的更新时间 | 已覆盖；预览提供演示内容 | 未创建真实事故 |
| 计划维护、影响范围与维护时间窗口 | 已覆盖；预览提供演示场景 | 未发布真实维护 |
| 历史事故及恢复时间线 | 已覆盖；预览提供明确标记的演示场景 | 未导入历史数据 |
| 90 天组件历史 | 使用 Instatus 原生能力；预览为灰色占位 | 未接入真实事故历史 |
| 订阅 | 使用 Instatus 原生订阅；预览按钮只说明行为 | 未连接真实订阅 |
| 官网、文档、支持入口 | 已加入链接；支持链接取官方文档的 Discord 入口 | 仅链接，不建立额外客服系统 |
| 手机布局、非颜色状态说明、监控失联提示 | 已覆盖 | 供应商生产主题还需核对 |
| 地址随部署变化 | 已明确从工作目录配置读取的契约 | CLI 已从工作目录生成；预览展示三组；已确认链接只用于 Testnet 示例 |
| 自动发布、恢复、去重和失联处理 | 已定义接入与验收边界 | Secret/webhook、路由和联调未完成 |

官方 [Faucet 指南](https://docs.dogeos.com/en/getting-started/user-guide/faucet)还列出测试币领取服务。这是额外的候选范围，已询问用户；在未确认前仍维持 8 个组件。若纳入，应区分正常限领/风控与领取服务异常，网页可访问不等于成功发币；不以频繁真实领币作为默认探测。当前仓库未找到其 chart，不能猜测它的部署配置来源。

三网统一展示；L2Scan、TPS/费用等数值曲线和内部服务逐项状态不属于本次范围。

## 上线准备与验收

1. 确认实际公开网络、官方 RPC/Bridge/Explorer URL、品牌素材、支持入口及订阅通道；只创建实际对外服务的组件。
2. 用 CLI 生成并应用页面名称、组件英文说明和排序。先在共享页面中初始化每个网络的原生组件组和 Public RPC 组件，再分别从各部署工作目录生成、应用；未积累的历史不补为 100%，确认公开观测及真实记录后再打开原生历史展示。
3. 先人工维护缺乏端到端证据的组件；给公共入口补外部观测。优先自动化公开 RPC/页面可用性、已验证的排序和批次进度。
4. 在独立测试页面验证触发、恢复、并发原因、观测缺失、发送端失联和维护流程，检查通知内容与原生聚合行为。
5. 将生成的 webhook URL 注入现有 Secret 管理流程，再启用选择性 Grafana 路由。生产发布状态来自真实观测或人工确认，不来自此 HTML 预览。

本次已在 scroll-sdk 模板和 scroll-sdk-cli 实现离线生成、只读计划及显式应用入口。尚未对真实 Instatus 执行应用，未修改生产告警路由。
