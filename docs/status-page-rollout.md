# DogeOS Testnet status page rollout

日期：2026-09-26。状态：接入说明和只读核实记录；未启用监控、创建 Instatus 资源或更改公开状态。页面结构见 [设计稿](status-page-design.md)，运行架构见 [架构文档](status-page-architecture.md)。

## 1. 先固定部署，再读取地址

选择一个明确的部署工作目录，再从该目录的最终有效配置读取地址；不要从 SDK 仓库的通用 example、搜索引擎或另一套部署复制。当前 CLI 通常将 chart values 放在 `<工作目录>/values/`，若用户目录直接存放 `frontends-production.yaml`，使用该明确路径。

| 内容 | 部署来源 | 使用规则 |
| --- | --- | --- |
| Bridge Portal 域名 | `frontends-production.yaml` → `ingress.main.hosts[].host` | 选择实际服务该前端的 host；不能默认所有 hosts 都等价 |
| Bridge 路径 | 当前前端路由 `/bridge` | Ingress `/` 是路由匹配前缀，不是 Bridge 的业务路径；若部署了额外前缀或 rewrite，按实际外部 URL 验证 |
| 外部协议 | 实际 TLS 终止/代理配置与部署协议 | HTTPS 部署使用 `https://<host>/bridge`；不要仅因 values 未声明 TLS 就断定是 HTTP，也不要跳过证书校验 |
| 公共 RPC | 当前部署实际启用的公共 RPC release 的 ingress | 新 Reth 布局可见于 `l2-reth-rpc-public-production.yaml`；旧布局可见于 `l2-rpc-production.yaml`。文件存在不代表启用 |
| 公共 WebSocket | 同一公共 RPC release 的 `ingress.websocket`（若启用） | 读取实际 host 与 TLS，验证握手、订阅响应及事件；HTTP 健康不代表 WebSocket 健康 |
| Chain ID | 同一部署的 `config.toml` → `general.CHAIN_ID_L2`，并与 RPC `eth_chainId` 核对 | 两者一致后才将 RPC 观测用于该网络；若可能复用 chain ID，还需核对链配置/初始区块身份 |
| 部署的 Blockscout | `blockscout-production.yaml` → `blockscout-stack.frontend.ingress.hostname` | 浏览器入口；后端 `blockscout-stack.blockscout.ingress.hostname` 可以与它不同 |
| Instatus 页面及 webhook | 为该网络选定的 Instatus 页面/原生集成 | Webhook 进入 Secret；不从 chain ID 或网站域名推导 |

若多个 host/release 都有效，应列明 Public RPC 覆盖的全部官方入口并定义部分中断语义。若配置缺失、仍含占位符或 ingress 被禁用，保留未配置，不回退到 Testnet 常量。文件中的期望状态也不证明已经部署，需要核对实际 release 和入口。

CLI 现有来源链：`spec.frontend.hosts.frontend` → `frontends-production.yaml` 的 ingress；`prep-charts` 使用 `config.toml` 的 `ingress.FRONTEND_HOST` 更新前端 host。本次新增的 `setup status-page` 复用这些部署文件生成入口，`prep-charts` 在源 values 更新后生成状态页配置。具体命令与字段见 [自动化契约](status-page-automation.md)。

首版公开范围为 **Testnet**。Mainnet 和 Devnet 的路径规则可以复用，但 URL、链身份、Secret 与 Instatus 目标必须各自配置。Devnet 默认不出现在公共 Testnet 页面。

## 2. 本次 Testnet 只读核实

以下是本次观测记录，不是默认配置，也不是持续可用性的证明。

| 项目 | 结果 / 依据 |
| --- | --- |
| 网络名称 | 官方文档为 DogeOS Chikyū Testnet |
| RPC | `https://rpc.testnet.dogeos.com/`；`eth_chainId` 返回 `6281971`（`0x5fdaf3`），与官方文档一致 |
| 出块观测 | 2026-09-26 02:49:48 UTC 观测到区块 `8045545`；02:50:40 UTC 观测到 `8045562`，两次区块时间分别为 02:49:46 和 02:50:37 UTC |
| Bridge Portal | 部署 values 的 host 与用户确认的 `https://portal.testnet.dogeos.com/bridge` 一致；HTTP 200，浏览器渲染出充提入口及 Transaction History |
| Blockscout | `https://blockscout.testnet.dogeos.com/`，工作目录的 Blockscout ingress 指向此；本次 HTTP 200，浏览器渲染出了最新区块 |
| Explorer 范围 | 本次 Explorer 按部署配置覆盖 Blockscout；用户明确排除 L2Scan |

公开来源：[网络配置](https://docs.dogeos.com/en/developers/developer-quickstart)、[用户指南](https://docs.dogeos.com/en/getting-started/user-guide)、[Bridge 指南](https://docs.dogeos.com/en/getting-started/user-guide/bridge)。两次 RPC 读请求能证明该观察窗口内返回的高度增长，不能证明所有用户请求成功、充提可用或所有节点同步正常。

本次未验证 WebSocket。浏览器检查未连接钱包、未签名、未发起充值/提现。单独 GET 返回 200 不足以验证 SPA 工作，因此额外读取了渲染后的页面；它仍不替代持续的浏览器合成检查。

## 3. 按组件建立判断依据

| 组件 | 最小有效判断 | 第一阶段发布方式 | 自动恢复前的要求 |
| --- | --- | --- | --- |
| Public RPC | 从外部验证 HTTP JSON-RPC 和已启用的 WebSocket；检查链身份、数据新鲜度及订阅，单协议失效可为部分中断 | 先内部通知，完成外部探测验证后再启用原生自动发布 | 原失败条件恢复且观测持续新鲜；一个成功 HTTP 请求不能清除其他仍在持续的故障 |
| Transaction Sequencing | 确认 sequencer 角色、预期出块模式及待处理交易，结合多个观测点确认停滞 | 先人工确认；候选信号来自现有 Grafana 规则 | 确认实际新区块推进；必要时确认已接受交易重新被包含 |
| Deposits | 已满足确认/有效性条件的充值仍未处理，且超出该部署确认的正常处理预算 | 人工确认，不直接转发 indexer 或 WF 告警 | 合格请求重新推进，异常积压得到处理或剩余影响已明确公告 |
| Withdrawals | 已满足协议条件的提现在具体阶段持续受阻，区分正常等待与故障 | 人工确认，不直接转发 TSO/proof 子任务告警 | 实际提现链路恢复，不能仅因一个内部服务恢复 ready 就宣布恢复 |
| Batch Publication | 有待发布批次且最老年龄超出确认的预算，并检查真实发布/确认进度 | 候选 Grafana 规则；先按部署版本校准 | 发布恢复且积压回到可接受范围；无新业务不能自动算恢复或故障 |
| Node Sync | 健康参照和待同步工作存在，但支持的公共数据路径持续无法同步 | 先人工确认；避免把单个 follower 问题放大 | 至少通过预定的参照/探针确认同步恢复 |
| Bridge Portal | 外部页面可达、关键脚本能加载、网络配置正确、支持 API 可用 | 基础 HTTP 探测先内部告警；浏览器/API 验证后确定自动化范围 | 页面与受影响功能都已恢复，不只检查 HTML 200 |
| Block Explorer | 部署内 Blockscout 的网页/API 可达，索引对比同一网络参照没有异常滞后 | 从工作目录确定入口后接入；索引滞后需先验证指标语义 | 对比最新已索引区块，不能用缓存首页的统计总数判断恢复 |

初始观察建议（用于调试，不是公开 SLA）：公共入口每 60 秒检查一次，单次超时预算 10 秒；连续失败约 3 分钟产生内部调查告警，恢复连续稳定约 5 分钟后再允许恢复判断。跨位置结果用于区分局部与整体故障，不能把轮询不同区域当作同时多区域确认。平台不支持这些窗口时先保留人工发布，不声称单次失败等价于持续故障。

充提预算单独确认。官方 Bridge 指南目前写明充提可能需要最多约 4 小时，并标注早期实现；这是用户预期的依据，不是可照搬到新版本的固定 SLA。不能将现有内部任务 15 分钟或队列 1 小时阈值直接对外承诺。

## 4. 公共入口的只读检查示例

以下 JSON 是请求体示例，不是额外的配置生成器输入。URL 与期望 chain ID 来自选定部署；公共入口不需要把内部 Grafana/Prometheus 的认证交给供应商。

确认网络身份：

```json
{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}
```

当前 Testnet 期望 `result` 为 `0x5fdaf3`。同时检查 `jsonrpc`、请求 ID、`error` 不存在和结果类型，不只检查 HTTP 200。确认最新区块：

```json
{"jsonrpc":"2.0","id":2,"method":"eth_getBlockByNumber","params":["latest",false]}
```

检查非空对象、有效的 `number` / `timestamp`，再结合部署的出块策略判断新鲜度和进度。`eth_chainId` 成功本身不证明节点没有卡住。生产告警需要持续采样和合适的基线，不能从本次两次读请求推导可靠 SLA。

默认保留 Grafana 统一发布路径。若要减少公共入口探针的自建工作，Instatus 另有原生 [API monitors](https://instatus.com/help/monitoring/api)，支持 POST、JSON 请求和响应断言，可作为候选外部观测方式；它访问的是已经公开的 RPC/网站，不读取私网监控。静态 JSON 断言适合验证 chain ID，但不足以自动推断区块持续推进、跨来源一致性或完整充提健康。

这是可选补充，当前未启用，也未改变已定的内部业务信号推送架构。若使用其原生公开状态更新，应明确该组件的唯一发布来源；不让原生 monitor 和 Grafana 同时独立恢复同一组件。原生探测地点按官方说明轮询，不当作同时多位置多数表决。页面不因此增加公开数值指标曲线。

## 5. 自动化应用与控制台落地清单

- 页面：`DogeOS Testnet Status`；描述：`Service availability and incident updates for the DogeOS testnet.`
- 先运行 `scrollsdk setup status-page` 生成配置，再用 `--plan` 检查和 `--apply` 应用。首版创建独立 Testnet 页面上的 8 个平铺组件，由页面标题标明网络；分组不在当前自动化范围内。
- Explorer 固定指本次部署的 Blockscout，具体域名与其他入口一样按工作目录读取并核对。
- 新建组件的初始状态默认 `OPERATIONAL`，可以覆盖；它只是初始化值，不代表已完成健康验证。已有组件的实时状态不会在重新部署时被覆盖。历史显示按真实记录启用，不填充虚构 uptime。
- 每条准备公开的规则只含可公开标签和文案，明确环境与组件。目标组件关联方式在 Instatus 测试页面联调，不假定任意标签都能自动匹配组件。
- Webhook 可通过 `setup status-page --apply --create-webhook` 首次自动取得；普通 `--apply` 复用保存在 `secrets/status-page/` 的私有记录。将生成的 `grafana.secret.yaml` 应用到现有 Grafana namespace。使用 production example 的 `statusPage.grafana.webhookSecretRef` 生成 Secret 引用与 contact point 配置；当前实例 URL 和 integration ID 不写入通用 values。备份私有记录，丢失或请求结果不明时恢复/导入已有 URL，不重复初始化；详见 [自动化说明](status-page-automation.md#automatically-obtain-the-grafana-webhook)。
- 最小联调：一次触发、重复通知、两个原因并存、只恢复一个原因、最终恢复、无数据、发送端失联、维护窗口。多原因未全部消除时不得提前恢复。
- 完成上述验证再给选定组件启用公开路由；其他组件由值班人员维护，后续逐项补齐信号。此文不代表测试页面或生产页面已经配置完成。
