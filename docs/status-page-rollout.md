# DogeOS shared status page rollout

更新：2026-09-27。通用功能的部署与验收说明，保留前期只读核实记录；本次实现未部署具体链或更改公开状态。页面结构见 [设计稿](status-page-design.md)，运行架构见 [架构文档](status-page-architecture.md)。

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
| Instatus 页面及 webhook | 共享 DogeOS 页面 / 该网络独立的原生集成 | Webhook 进入 Secret；不从 chain ID 或网站域名推导 |

若多个 host/release 都有效，应列明 Public RPC 覆盖的全部官方入口并定义部分中断语义。若配置缺失、仍含占位符或 ingress 被禁用，保留未配置，不回退到 Testnet 常量。文件中的期望状态也不证明已经部署，需要核对实际 release 和入口。

CLI 现有来源链：`spec.frontend.hosts.frontend` → `frontends-production.yaml` 的 ingress；`prep-charts` 使用 `config.toml` 的 `ingress.FRONTEND_HOST` 更新前端 host。本次新增的 `setup status-page` 复用这些部署文件生成入口，`prep-charts` 在源 values 更新后生成状态页配置。具体命令与字段见 [自动化契约](status-page-automation.md)。

当前公开设计为 **Mainnet / Testnet / Devnet 共用页面**：workspace `6wxpx`，页面 `dogeos.instatus.com`。每个工作目录只负责自己的组，URL、链身份与 webhook Secret 各自配置。下文 Testnet 核实记录不能作为其他网络的健康证据。控制台分组初始化、自动化入口与旧页面迁移见 [配置契约](status-page-automation.md)。

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

## 3. 部署前输入

当前实现见 [组件发布配置](status-page-publication.md)。上述 2026-09-26 采样只是历史记录。
通用模板不会代填具体链的业务 SLA 或把入口可访问等同于完整业务可用。

1. 部署包含新 public queue 指标的 dogeos-core 镜像。确认 WP 和 DA 实际 target
   与 `health.*JobRegex` 匹配；proof-only WP 不属于业务队列 target。
2. 确认充值、协议 eligible 提现、批次发布的 deadline，填写对应 `health` 参数。
   设置真实出块模式、块龄、延迟和采样新鲜度；未填写的业务 deadline 保持未配置。
3. 填写 Bridge 必要 API 的 JSON path/期望值、Explorer 实际数据 selector，
   配置独立 canary node 和同步依赖检查；内置 WebSocket 检查是 JSON-RPC 请求，
   不覆盖订阅推送完整性，有订阅 SLO 时另加语义探针/自定义规则。
4. 构建 `charts/status-page-probe/Dockerfile` 镜像；在至少两个独立位置部署探针，
   设置不同实际 location。配置私网 `metricsTargets` 或现有 Prometheus federation。
   不在该链集群内复制两个 Pod 来代替独立探测。
5. 配置真正可用的内部 Grafana contact point。需要集群失联通知时，填写 Instatus
   内部 monitor alert IDs 并启用 heartbeat；这些不是公开订阅者，也不是 Grafana UID。

## 4. 生成、观察、逐组件启用

```sh
scrollsdk setup status-page --deployment-dir /path/to/network \
  --probe-values values/status-page-probe-production.yaml
scrollsdk setup status-page --deployment-dir /path/to/network --plan --create-webhook
scrollsdk setup status-page --deployment-dir /path/to/network --apply --create-webhook
```

初期所有组件 observe，不需要组件 webhook。检查 CLI readiness 的缺项，应用生成的
Helm values 和独立探针，观察真实指标及 missing-data 告警。配置 ready 不等于实时健康。

选择已完成验收的组件改为 automatic，重新生成并 review/apply；创建组件独立集成与
Secret。将 `secrets/status-page/<key>.secret.yaml`（及可选 heartbeat Secret）通过已有
Secret 流程应用到 monitoring namespace，再部署监控。CLI apply 本身不部署 K8s。
新配置默认使用 PVC 投递校验器；确认 StorageClass、单副本和私网连通性。
同页元数据按页面串行 apply，保留父组及其他网络组件。

## 5. 验收场景

先在测试目标验证以下场景，不用真实公共页面来做故障演练：

| 场景 | 必须满足 |
| --- | --- |
| 明确故障持续超过窗口 | 只更新该网络、该组件；公开 payload 不含内部 URL/原始错误 |
| 短故障 / 短恢复 | 不产生错误切换 |
| 无数据、过旧样本、探针分歧、查询失败 | 内部报警；已有公开事故不恢复 |
| 多个失败原因，仅一项恢复 | 组件保持异常 |
| Grafana 暂停、删除、原始 resolved | 不能据此公开恢复 |
| 校验器重启 | 保留事件身份；重新等待完整确认窗口 |
| 发送失败或 HTTP 响应不明确 | 相同事件重试；状态已反转时停留 pending 并内部报警 |
| 持续新鲜健康超过恢复窗口 | 同一组件的确认恢复，供应商正确关联原事故 |
| 重跑 CLI / 模板升级 | 不新增重复页面、组件或集成；拒绝手改产生的陈旧配置 |
| 监控/集群断开 | 心跳停止；Cron Monitor 在 grace 后通知内部目的地 |
| 人工接管 | manual 部署后停止该组件自动投递；保留事件与私有收据 |

本地已覆盖 Prometheus 表达式、CLI→Helm、真实 Grafana→校验器→本地 HTTP 接收端、
浏览器及数据库异常用例。真实 Instatus 模板、重复通知、维护及订阅行为仍是供应商
验收项。首次心跳需确认已成功到达并启动 provider 计时。

## 6. 运维与回退

私有绑定目录、管理状态文件和校验器 PVC 都需备份。自动 apply 不发送事故，但创建
Cron Monitor 是真实 provider 配置；不要把含凭据的响应加入日志或工单。
停用单组件先改 manual/observe 并部署；停用 heartbeat 需 apply 暂停远端计时。
旧的 operator 自建路由要单独退役。发生不明确投递、PVC 丢失或人工接管，先暂停组件，
核对实际 Instatus 事故和持久化记录，恢复确认后再启用。不能删除收据强制重建。
