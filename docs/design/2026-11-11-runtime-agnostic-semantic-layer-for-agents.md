# 面向外部智能体（zcode 等）的运行时无关本体语义层设计

日期：2026-11-11。状态：草案待审。来源：针对外部编程与分析智能体（zcode、Cursor、Claude Code 等）消费本体语义、反馈纠偏、多空间路由与语义/接口版本演进的需求整理。

## 1. 背景与核心问题

OntoFoundry 核心模型表达业务语义，通过统一的语义基座消除数据孤岛与理解分歧。目前平台已具备内部建模与问数能力（通过 DataAgent 与单空间固定令牌 MCP）。随着业务发展，用户提出在外部通用编码与分析智能体（如 zcode、Cursor 等）中直接消费 OntoFoundry 本体语义的需求。

在将平台打造为**运行时无关（Runtime-Agnostic）的通用本体语义层**时，面临以下 5 个核心问题：

1. **多空间与跨领域接入**：平台按工作空间（Workspace）进行业务隔离。若用户需要跨财务、采购、销售多个领域知识，如果采用“每空间配一个 MCP 服务”，会导致外部智能体配置爆炸、工具列表污染，且无法进行跨领域概念关联。
2. **使用指引与插件化封装（MCP + Skill）**：外部智能体仅有 MCP 裸工具容易产生幻觉或凭直觉构造非法查询；需要通过 Skill/Plugin 提供标准化语义对齐（Semantic Grounding）工作流与调用规约。
3. **知识闭环与纠偏回流**：用户在智能体对话中纠正的指标口径与实体定义，不能直接原地修改生产本体（避免企业全局 Single Source of Truth 遭到污染），但又必须有自动化回流机制，形成“使用-发现问题-反馈-审阅-合并”的闭环。
4. **身份认证、权限归因与认知负荷**：平台支持 OAuth 登录。现有外部固定 MCP 令牌（`fixed-mcp-token.md`）是以空间最早管理员身份代读，无法归因调用者；若要求用户为每个空间分别申请并配置独立的 Bearer Token，用户认知负担过重。
5. **接口演进与语义版本防漂移（重点）**：平台的 MCP 契约与各空间的本体语义、指标口径会持续迭代更新。代码接口报错尚可 Fast-fail，但**语义口径更新若未及时同步，会导致智能体“一本正经地算出错误口径的业务数据”**。必须具备完备的版本标识、废弃提示、缓存失效与错误自愈协议。

---

---

## 2. 行业调研与同类产品对标分析

随着现代数据栈与大模型智能体生态的演进，独立语义层（Headless Semantic Layer）与业务本体（Operational Ontology）正在经历代际变革。通过对全球开源与商业产品的系统性调研，当前业界主要分为四大派系：

### 2.1 业界四大派系盘点

#### 1. 工业级本体与操作中枢派（最接近 OntoFoundry 愿景的标杆）
* **Palantir Foundry (AIP Logic & Foundry Actions & Ontology MCP)**：全球工业级企业本体的绝对标杆。
  * **现实路线**：Palantir 在大型企业中极少能直连生产数据库，主要依靠 **Data Connectors + External Webhooks + TypeScript Functions**。
  * **状态与动作**：实体属性支持由外部 REST API 实时填充（Hydration），实体上绑定的业务动作（Actions，如退款、封控）直接映射为业务系统的 API/Webhook。近期推出 **Ontology MCP Hub**，外部服务可通过 MCP 直接挂接为本体能力。
* **C3.ai (C3 Type System - 模型驱动架构)**：企业级 AI 软件独角兽。
  * **核心技术**：C3 Type System 将业务类型（如 `Customer`、`SmartMeter`）彻底与底层存储解耦。属性可以声明来自关系数据库、时序库、或者业务系统的 REST API。由平台联邦执行引擎自动分发调度。
* **Celonis (Process Intelligence Graph - 业务流程本体)**：全球流程挖掘与业务治理龙头。
  * 业务系统（SAP、Salesforce）不提供数据库直连。Celonis 纯靠 API 抽取业务事件与对象，构建统一业务流程本体，并在其上触发跨系统业务操作（Action Engine）。

#### 2. 指标驱动型现代语义层（Metric-Centric / Headless BI）
* **Cube (Cube.js)**：开源界最成熟的通用独立语义层。以多维模型（Cubes/Dimensions/Measures）为核心，提供统一的 SQL API / REST API / GraphQL，近期也在发力向 LLM 提供上下文。
* **dbt Semantic Layer (MetricFlow)**：指标即代码（Metrics-as-Code），支持编译多表关联为目标 SQL 方言下推。
* **Kyligence Zen**：国内团队出品的指标平台，主打指标目录与 AI Copilot 问数。
* **核心局限**：**纯 SQL 与纯数仓思维**。假设所有数据都已存在于数据表中；一旦业务系统不开放数据库权限，便无法处理。缺乏实体关系图谱与定性文档事实。

#### 3. API 联邦与统一数据网格派（技术驱动的统一数据层）
* **Hasura DDN (Data Delivery Network / Native Data Connector)**：突破了早年只连 Postgres 的限制，通过 NDC 连接器允许把数据库与**业务微服务的 REST API / Python 服务**同时注册为数据源，在毫秒内跨库跨 API 拼装返回。
* **Apollo Federation (GraphQL Supergraph)**：硅谷大厂（Netflix、Expedia）解决微服务 API 割裂的标准架构。以 Entity 为核心将各子系统 API 拼成超级图谱。
* **核心局限**：偏向纯程序员视角的 API 编排网关，**没有业务指标（Metrics）定义、没有本体知识事实、缺乏面向大模型的 MCP 语义支持**。

#### 4. 面向 Agent 的工具路由派（Agent-Native Tool & Action Hub）
* **Composio (composio.dev)**：当前海外 Agent 生态中极火的平台，封装了 250+ SaaS 系统的 API 并转为 Agent Tool / MCP Server。
* **核心局限**：**空有四肢、缺乏大脑**。Composio 只有离散的工具（`create_jira_issue`、`get_salesforce_contact`），但缺乏“业务概念拓扑与实体关系（Ontology）”，智能体无法理解深层业务上下文和跨系统关联。

### 2.2 核心现实：长期来看 API / MCP 是更常态化的场景

企业架构的客观现实决定了：**不会有业务系统愿意直接向外部 Agent 开放数据库**。
1. **微服务封装原则（Database-per-Service）**：数据库属于系统私有实现细节，越权读库直接破坏微服务自治；
2. **安全与合规审计**：直连数据库直接绕过应用层的动态脱敏、行级权限控制与审计日志，且存在大查询锁表（Deadlock）打垮生产事务的致命风险；
3. **接口契约稳定性**：底层表结构随时重构，但官方对外暴露的 API / MCP 具备严格的语义版本控制（SemVer）。

因此，**OntoFoundry 必须确立“API 与 MCP 工具为一等公民、数仓表为大吞吐后备”的混合架构基调（SL-14）**。

### 2.3 横向对比矩阵

| 产品 / 阵营 | 核心数据源 | 是否支持业务 API / MCP | 核心抽象维度 | 是否具备闭环修改能力 | 目标受众 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Cube / dbt** | 仅限数仓/数据库 | ❌ 极弱（只能处理库表） | 纯指标、维度、SQL | Git PR 手写代码 | 数据分析师 / BI |
| **Composio** | 仅限 API / SaaS 接口 | ✅ 极强（主打 API 变 Tool） | 仅提供离散的函数工具 | ❌ 无模型，只有工具 | AI Agent 开发者 |
| **Hasura DDN** | 数据库 + 微服务 API | ✅ 支持自定义 API | 实体关系图（GraphQL Schema） | 代码配置 | 后端架构师 / 全栈 |
| **Palantir Foundry** | 数据库 + API + Webhook | ✅ 完善（Action + MCP） | **全域本体（实体/关系/指标/动作）** | 平台内分支审批流 | 顶级跨国企业 / 政府 |
| **OntoFoundry (我们)** | **数仓表 + 业务 API / 外部 MCP** | **✅ 核心常态（API/MCP First）** | **业务本体语义 + 知识事实 + 指标** | **查/修/馈/环：自愈闭环** | **业务智能体 / 平台开发者** |

### 2.4 OntoFoundry 的差异化破局点

比起传统纯指标工具或离散工具平台，OntoFoundry 具备三大代际级护城河：
1. **全域业务认知大脑（Ontology Brain）**：不同于 Composio 的离散工具堆砌，我们提供统一的实体概念网络、关系图谱与计算指标，赋予 Agent 结构化的业务认知；
2. **多模态混合源绑定（Hybrid Hydration）**：解耦底层物理细节，同一个实体，基础属性可走数仓表，实时状态可走业务 API/MCP；
3. **“查、修、馈、环”自愈闭环**：不仅对 Agent 开放只读查询，更通过结构化变更提案（修）与业务争议提报（馈），结合原子化校验与指纹刷新，实现本体资产的持续演进沉淀。

---

## 3. 已确认决定

| 编号 | 决定 | 状态 |
|---|---|---|
| SL-01 | **单网关 MCP（Gateway Pattern）**：提供平台级统一网关 MCP 端点 `/api/v1/ontology/mcp`，取代按空间拆分的多个 MCP 端点。智能体只需配置一次，通过参数指定空间或由后端自动在用户有权空间内检索。来源：MCP 最佳实践与微服务网关模式；执行优化，不改变底层空间隔离模型。 | 待评审 |
| SL-02 | **平台级个人访问令牌（PAT）**：用户在平台个人设置生成唯一的 PAT（`ont_pat_xxx`），绑定全局用户身份。MCP 自动识别调用者 `user_id` 并根据空间的 RBAC 权限做动态裁剪；彻底消除“为每个空间单独申请令牌”的认知负担。 | 待评审 |
| SL-03 | **全链路调用与反馈归因**：MCP 所有工具调用在服务端记录 `user_id`、`client: zcode`、`workspace_id` 与工具参数；智能体提交的反馈与变更提案自动绑定当前用户，无需客户端传递身份信息。 | 待评审 |
| SL-04 | **两阶段知识回流（反馈闭环）**：智能体通过 MCP 工具 `submit_ontology_feedback` 提交轻量业务反馈或争议，在平台生成“待审反馈/工单”，由空间管理员或建模人员在 Web 控制台确认合并；严禁外部 Agent 直接非受控覆盖生产本体。 | 待评审 |
| SL-05 | **空间语义指纹与版本化（Semantic Hash / SemVer）**：每个空间维护唯一的 `ontology_version` 与 `version_hash`。空间内任何实体、属性、度量或绑定的增删改均使 Hash 变化。MCP 响应统一附带元数据 `_meta: { space_id, ontology_version, version_hash }`。 | 待评审 |
| SL-06 | **条件查询与缓存失效（ETag 协议）**：MCP 核心探查工具支持 `if_version_matches`。未变化返回轻量 `NOT_MODIFIED` 节省上下文 Token；已变化返回最新子图与变更摘要，强制智能体刷新认知。 | 待评审 |
| SL-07 | **软废弃元数据与迁移警示（Deprecation Metadata）**：实体与指标支持 `deprecated`、`deprecation_reason`、`superseded_by`。对已废弃对象的调用正常响应但附带警告，Skill 强制 Agent 主动提示用户迁移至新口径。 | 待评审 |
| SL-08 | **接口增量演进与自愈错误契约**：MCP 工具采用向后兼容的增量变更；发生语义漂移或不兼容变更时，后端返回带 `ERR_SEMANTIC_VERSION_DRIFT` 的业务错误，内嵌 `suggested_action` 指引 Agent 自主重新拉取最新图谱自愈。 | 待评审 |
| SL-09 | **标准插件封装（OntoFoundry Plugin for Agents）**：将 MCP 服务声明、Semantic Grounding 核心 Skill 与 Rules 打包为通用 Plugin 规范（支持 zcode、Cursor、Claude Code 等），固化“先查本体 -> 消歧对齐 -> 构造查询 -> 异常反馈”的行为规约。 | 待评审 |
| SL-10 | **双模态语义输出与执行解耦**：第一期坚守“纯语义与元数据提供者”，物理 SQL 执行交由 opendataworks 插件；第二期演进支持 Agent-as-a-Tool 委派模式（A2A），保持运行时无关。 | 待评审 |
| SL-11 | **预置插件斜杠命令（Slash Commands）**：在 Plugin 中预置 `/onto-search`、`/onto-metric`、`/onto-sync`、`/onto-propose`、`/onto-feedback`、`/onto-spaces` 等快捷命令，降低用户认知成本，提供高频、确定性的交互通道。 | 待评审 |
| SL-12 | **结构化语义修改提案（Propose Semantic Mutations）**：面向有权限的开发与建模智能体，开放结构化变更工具 `propose_ontology_mutation`，支持直接提交实体、属性、度量或绑定的创建与修改，复用平台已有的提案原子化检查（`parse_agent` / `trial_apply`），实现“语义能修”。 | 待评审 |
| SL-13 | **多源语义绑定与业务应用 MCP 桥接（Data & API & Action）**：本体底层不局限于只读数仓表，预留支持业务应用通过 API / MCP 接入作为数据与动作来源。实体属性既可绑定数据表列，也可绑定实时 API/MCP 工具返回值；未来进一步映射业务动作（Action Types），成为全域业务语义中枢。 | 待评审 |
| SL-14 | **API 与 MCP 工具作为常态化语义源（API-First Operational Grounding）**：确立“企业应用通过 API / MCP 接入作为主要常态、数仓宽表作为离线大吞吐支撑”的架构基调。实体属性与状态支持直接绑定接口返回值，彻底摆脱传统语义层“必须直连底层数据库”的硬性约束。 | 待评审 |

---

## 4. 多空间接入与认证架构（SL-01、SL-02、SL-03）

### 3.1 接入对比

* **改前（单空间独立 MCP，见 `2026-10-22-fixed-mcp-token.md`）**：
  * 地址：`/api/v1/ontology/workspaces/{workspace_id}/mcp`
  * 鉴权：部署固定的静态环境变量令牌（代表最早加入的管理员身份，只读，无法识别真实调用人）。
  * 体验：用户在 zcode 中若要使用 `fiction_retail_space` 与 `fiction_crm_space`，必须在配置中维护两个不同的 MCP Server。

* **改后（统一 MCP 网关 + PAT，SL-01、SL-02）**：
  * 地址：`/api/v1/ontology/mcp`
  * 鉴权头：`Authorization: Bearer <ONTOLOGY_PAT>`
  * 交互体验：配置一次，终身受益；后端根据 PAT 解析用户身份，自动列出并操作该用户有权的所有空间。

### 3.2 zcode MCP 配置示例

```json
{
  "mcpServers": {
    "ontofoundry": {
      "type": "http",
      "url": "https://ontofoundry.example.com/api/v1/ontology/mcp",
      "headers": {
        "Authorization": "Bearer ont_pat_9a8b7c6d5e4f3a2b1c0d"
      }
    }
  }
}
```

### 3.3 认证与审计流转

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户 (Alice)
    participant Agent as zcode Agent
    participant Gateway as OntoFoundry MCP Gateway
    participant Auth as 认证与权限服务
    participant Audit as 审计日志服务
    participant Onto as 本体核心服务

    Note over User,Gateway: 一次性配置 PAT (ont_pat_xxx)
    User->>Agent: "分析虚构采购空间的近期异常订单"
    Agent->>Gateway: POST /mcp (tool: search_ontology, PAT)
    Gateway->>Auth: 校验 PAT 有效性与用户身份
    Auth-->>Gateway: Principal(user_id="u_alice", tenant_id="t_1")
    Gateway->>Auth: 获取 u_alice 有权空间及权限级别
    Auth-->>Gateway: ["fiction_procure_space": read, "fiction_retail_space": admin]
    Gateway->>Audit: 异步记录调用日志 (user_id, client="zcode", tool="search_ontology", args)
    Gateway->>Onto: 执行带空间与权限过滤的语义检索
    Onto-->>Gateway: 返回本体子图与版本指纹
    Gateway-->>Agent: JSON-RPC Result (_meta 携带 version_hash)
```

---

## 5. 语义版本化与防漂移协议（SL-05、SL-06、SL-07、SL-08）

### 4.1 语义版本指纹（Semantic Version Fingerprint）

每个空间维护由核心定义内容计算得出的 SHA-256 摘要前缀（`version_hash`）及语义版本号：
* 变更触发源：实体（Object Type）、属性（Property）、关系（Link Type）、规则（Rule）、独立指标（Metric）、数据集绑定（Dataset Binding）的任何发布与修改。
* 元数据注入：所有 MCP 工具返回的数据均外覆 `_meta` 对象：
  ```json
  {
    "_meta": {
      "space_id": "fiction_procure_space",
      "ontology_version": "v1.3.0",
      "version_hash": "e3b0c44",
      "updated_at": "2026-11-11T10:30:00Z"
    },
    "result": { ... }
  }
  ```

### 4.2 条件查询与 ETag 协议（SL-06）

为解决 Agent 长时间运行上下文缓存陈旧、频繁拉取整图浪费 Token 的问题：

* **请求格式**：
  ```json
  {
    "tool": "get_entity_subgraph",
    "parameters": {
      "space_id": "fiction_procure_space",
      "entity_name": "PurchaseOrder",
      "if_version_matches": "e3b0c44"
    }
  }
  ```
* **响应情况 A：未发生变更（304 Not Modified）**：
  ```json
  {
    "_meta": { "space_id": "fiction_procure_space", "version_hash": "e3b0c44", "status": "NOT_MODIFIED" },
    "message": "本体语义无变化，可继续沿用本地上下文"
  }
  ```
* **响应情况 B：已发生变更（强制刷新）**：
  ```json
  {
    "_meta": { "space_id": "fiction_procure_space", "version_hash": "7f8a9b1", "status": "UPDATED" },
    "changelog_since_last": [
      "Property [tax_amount] added to [PurchaseOrder]",
      "Metric [net_procure_amount] formula updated"
    ],
    "subgraph": { ... }
  }
  ```

### 4.3 软废弃元数据（SL-07）

指标和属性支持软废弃，定义结构如下：

```json
{
  "id": "metric_procure_gmv_legacy",
  "name": "procure_gmv_legacy",
  "display_name": "采购总额（旧口径）",
  "deprecated": true,
  "deprecation_reason": "未剔除折让与退款，口径已废弃",
  "superseded_by": "net_procure_amount",
  "sunset_date": "2026-12-31"
}
```

当 Agent 请求涉及此度量时，MCP 返回并在响应中注入警告 `warnings: [{ code: "DEPRECATED_METRIC", ... }]`，Skill 指引 Agent 主动告知用户。

### 4.4 自愈错误契约（SL-08）

当 Agent 发起的操作引用的实体、属性或关系已不存在或口径发生冲突时，后端返回符合 `ServiceError` 约定的结构化自愈响应：

```json
{
  "error": {
    "code": "ERR_SEMANTIC_VERSION_DRIFT",
    "message": "属性 [PurchaseOrder.status_code] 已在 v1.3.0 中迁移至 [PurchaseOrder.order_status]",
    "space_id": "fiction_procure_space",
    "current_version": "v1.3.0",
    "suggested_action": "调用 get_entity_subgraph('PurchaseOrder') 重新同步最新定义并重新生成查询",
    "can_self_heal": true
  }
}
```

---

## 6. 语义管理闭环架构：查、修、馈、环（SL-04、SL-12）

要实现“持续沉淀、修正语义”，系统必须打通**“语义能查（知）”、“语义能修（改）”、“能提交反馈（馈）”、“持续自愈演进（环）”**四大支柱，形成完整的资产演进生命周期。

### 5.1 闭环全景流程

```mermaid
flowchart TD
    subgraph Client [外部智能体 / 开发者 IDE (zcode)]
        U[用户提出业务需求 / 写代码 / 做分析] --> Q[1. 查: 检索权威本体概念与口径]
        Q --> Dev[开发与查询执行]
        Dev -->|发现缺少定义或口径过时| Decide{用户角色与诉求}
        Decide -->|建模者/开发者: 明确结构变更| M[2. 修: 提交结构化语义修改提案]
        Decide -->|业务分析师: 提出口径争议/疑问| F[3. 馈: 提交非结构化问题反馈]
    end

    subgraph Platform [OntoFoundry 语义治理平台]
        M -->|原子化校验 pass| PB[生成空间待合并提案批次]
        F --> FB[生成语义反馈待核实工单]
        FB --> RevGov[建模师核实并转化为标准提案]
        RevGov --> PB
        PB --> WebRev[Web 控制台审阅看板: 变更 Diff 与冲突比对]
        WebRev -->|管理员核准合并| Merge[发布新版本 & 写入生产本体]
        Merge --> Bump[4. 环: 更新 version_hash & 发布事件]
    end

    Bump -.->|下一次请求带最新指纹 / ETag 失效| Q
    Bump -.->|/onto-sync 强制刷新| Q
```

---

### 5.2 语义能查（知）：语义服务与按需探查

* **核心目标**：提供只读的语义基座服务，消除物理表与业务术语之间的鸿沟，防止外部 Agent 臆造库表字段。
* **工具支持**：
  * `list_spaces`：按当前 PAT 用户权限展示空间目录与各空间最新指纹。
  * `search_ontology`：基于 BM25 / 向量的多空间概念全文检索。
  * `get_entity_subgraph`：获取指定实体及其 1 度/2 度关系子图，带绑定物理表投影，支持 `if_version_matches` 条件 ETag。
  * `resolve_metric`：精确解析指标口径公式、默认过滤条件、聚合基数与物理列映射。

---

### 5.3 语义能修（改）：结构化语义变更提案（SL-12）

当开发者在 zcode 中编写业务逻辑，发现“采购订单实体缺少 `tax_rate` 属性”，或“净采购额指标公式需要更新”时，**具备空间编辑权限的 Agent 可以直接调用结构化修改工具**：

* **工具定义：`propose_ontology_mutation`**
  * **入参**：
    * `space_id`: 目标空间；
    * `action`: `create` | `update` | `deprecate` | `delete`；
    * `target_kind`: `object_type` | `property` | `link_type` | `metric` | `dataset_binding`；
    * `target_name`: 概念英文标识（如 `net_procure_amount`）；
    * `payload`: 结构化定义（如指标的聚合表达式、属性的物理列映射）；
    * `rationale`: 修改理由与业务依据。
  * **后端处理机制**：
    1. 后端直接复用平台现有的**提案检查与原子化校验引擎（`parse_agent` / `trial_apply`）**，当场检查语法、类型兼容性、来源物理列是否存在。
    2. 校验通过后，在空间内生成一个待合并的提案批次（Proposal Batch），附带提交人 `created_by=user_id` 与客户端来源 `source=zcode`。
    3. 若该用户本身是空间的 Space Admin，可支持配置 `auto_merge_if_admin=true` 直接生效，否则进入待审池。

---

### 5.4 能提交反馈（馈）：轻量业务反馈与争议上报（SL-04）

面向普通业务分析师或只读用户，当其不具备建模权限，或仅发现“计算出来的结果不对、退款没有扣除”但不知道底层表结构如何修改时：

* **工具定义：`submit_ontology_feedback`**
  * **入参**：
    * `space_id`: 涉及空间；
    * `target_concept`: 存疑的概念或指标（如 `GMV`）；
    * `issue_category`: `formula_dispute`（口径争议） | `missing_concept`（缺少概念） | `definition_unclear`（定义不清）；
    * `description`: 用户自然语言描述（“财务口径要求从本月起排除未付款订单”）；
    * `dialogue_context`: 产生争议时的上下文对话与数据证据。
  * **后端处理机制**：
    * 写入 `agent_feedbacks` 待办工单库。
    * 平台在 Web 审阅看板中展示，空间管理人员核对后，可**一键将反馈转为标准修改提案（Proposal）**，进入合并流程。

---

### 5.5 持续沉淀与自愈闭环（环）

1. **版本递增与指纹刷新**：无论是通过“修（提案）”还是“馈（反馈转提案）”，一旦管理员在平台审阅通过并合并，空间的 `ontology_version` 自动递增，规范化 `version_hash` 立即重新计算。
2. **外部感知与即时自愈**：
   * **隐式自愈**：外部智能体下次发起查询时，若传入了旧的 `if_version_matches`，平台返回 `UPDATED` 及最新变更摘要，Agent 静默刷新上下文；若调用了已删除/废弃的概念，平台返回 `ERR_SEMANTIC_VERSION_DRIFT` 指引 Agent 自愈重新拉图。
   * **显式刷新**：用户在 zcode 敲 `/onto-sync`，立即强制拉取空间最新语义指纹与变更记录。
3. **资产持续沉淀**：
   * 外部 Agent 不再是一个单纯的“消费者”，而是成为了语义建设的**“触角与输入源”**。每一次编码纠错、每一次问数争议，都在丰富和纠正平台的全局本体，越用越准。

---

## 7. MCP 工具契约（Gateway 统一接口）

网关 MCP 提供以下核心工具，覆盖查（探查与编译）、修（结构化提案）、馈（问题反馈）：

| 工具名称 | 职责分类 | 核心参数 | 返回关键内容 |
|---|---|---|---|
| `list_spaces` | **查（知）** | 无 | 空间列表、空间名称、用户角色（admin/member/viewer）、当前 `version_hash` |
| `check_space_version` | **查（知）** | `space_id`, `current_hash` | 是否变化、当前版本号、变更摘要 |
| `search_ontology` | **查（知）** | `query`, `space_ids?`, `kinds?`, `limit` | 召回的实体、属性、指标候选列表，按相关度排序，带消歧标记 |
| `get_entity_subgraph` | **查（知）** | `space_id`, `entity_name`, `depth` (默认 1), `if_version_matches?` | 实体定义、属性清单、业务标识、直连关系、引用的数据集投影 |
| `resolve_semantic_query` | **查（知）** | `space_id`, `metrics`, `dimensions`, `filters` | 编译后生成的安全 SQL、维度对齐路径、口径确认信息 |
| `propose_ontology_mutation` | **修（改）** | `space_id`, `action`, `target_kind`, `target_name`, `payload`, `rationale` | 提案批次 ID (`batch_id`)、原子校验状态、审阅链接、是否已直合（Admin 模式） |
| `submit_ontology_feedback` | **馈（馈）** | `space_id`, `target_concept`, `issue_category`, `description`, `dialogue_context` | 反馈工单 ID (`feedback_id`)、审阅链接、状态 (`PENDING_REVIEW`) |

---

## 8. 智能体 Skill、Plugin 与斜杠命令规约（SL-09、SL-11）

面向 zcode 等智能体的插件包包含：
1. `plugin.json`：注册 MCP 服务地址、认证引导与能力描述。
2. `skills/semantic-grounding/SKILL.md`：定义语义锚定与使用策略。
3. `commands/`：预置便捷斜杠命令模板。

### 8.1 Skill 核心指导原则（Prompt 注入规范）
1. **语义优先（Ontology First）**：
   * 禁止在未检索本体的情况下臆造物理库表名或字段名。
   * 查询前必须先调用 `search_ontology` 或 `get_entity_subgraph` 确认概念已发布。
2. **版本防漂移规则（Version Freshness）**：
   * 在涉及复杂指标计算的对话中，若本地上下文中的本体知识超过 30 分钟未更新，必须调用 `check_space_version` 校验指纹。
   * 遇到 `ERR_SEMANTIC_VERSION_DRIFT` 时，禁止机械重试，严格按照返回的 `suggested_action` 重新拉取新子图。
3. **闭环修改与纠偏策略（Mutate & Feedback Strategy）**：
   * **修（Propose）**：开发者明确要求新增或变更概念且具备权限时，调用 `propose_ontology_mutation` 提交结构化提案。
   * **馈（Feedback）**：业务用户提出口径分歧但未指定修改方案时，调用 `submit_ontology_feedback` 提交工单。

### 8.2 预置插件斜杠命令（SL-11）

| 命令 | 对应分类 | 作用与交互示例 |
|---|---|---|
| `/onto-search [词]` | **查** | 快速探查实体或指标的官方权威定义卡片（如 `/onto-search 采购订单`） |
| `/onto-metric [指标]` | **查** | 穿透查看指标的底层计算公式、过滤条件与物理表绑定（如 `/onto-metric 净采购额`） |
| `/onto-sync [空间]` | **环** | 强制刷新本地语义缓存，校验 `version_hash` 并展示最新变更日志 |
| `/onto-propose` | **修** | 引导式发起结构化变更提案（支持在 IDE 中交互补齐属性/公式并提交审核） |
| `/onto-feedback [描述]` | **馈** | 一键将当前会话中的口径争议与 SQL 片段打包上报平台工单库 |
| `/onto-spaces` | **查** | 列出当前用户有权访问的所有空间、所属角色与当前版本指纹 |

---

## 9. 与现有架构的关系与迁移

1. **与 `2026-10-22-fixed-mcp-token.md` 的关系**：
   * 现有固定令牌 `ONTOFOUNDRY_MCP_TOKEN` 保留，用于内网无用户界面的 DataAgent 容器间服务级通信；
   * 新增的 PAT 机制用于面向终端用户的通用智能体（zcode、IDE 插件），互不干扰。
2. **与 `2026-10-21-semantic-grounding-skills.md` 的关系**：
   * 沿用其关于“检索、候选召回、判级、校验在平台 Python 服务中完成，Skill 只写执行策略”的定式（SG-08）；
   * 将原先仅适配 DataAgent 的三个内部技能进一步抽象为开放的通用 Agent 规范。
3. **与平台提案校验体系（`single-proposal-check.md`）的关系**：
   * `propose_ontology_mutation` 完全复用平台统一的 `parse_agent` 检查逻辑，不另起炉灶。

---

## 10. 后续实施阶段划分

* **阶段 1：PAT 鉴权与 MCP 网关支持（P0）**
  * 后端增加用户 PAT 签发与解析机制；
  * 新增无 `workspace_id` 路径的统一 MCP 路由 `/api/v1/ontology/mcp`，支持基于用户权限的空间动态过滤。
* **阶段 2：版本指纹与 ETag 条件查询（P0）**
  * 空间实体与指标增加 `version_hash` 计算逻辑；
  * 核心 MCP 工具集成 `_meta` 指纹与 `if_version_matches` 条件判断；
  * 支持 `deprecated` 元数据与自愈错误码 `ERR_SEMANTIC_VERSION_DRIFT`。
* **阶段 3：语义闭环——修改提案与反馈工单（P0）**
  * 实现 `propose_ontology_mutation`（修）工具并对接提案检查入库引擎；
  * 实现 `submit_ontology_feedback`（馈）工具与待审看板；
  * OntoFoundry Web 端增加“外部智能体提案/反馈”审阅视图，支持一键采纳并合并。
* **阶段 4：zcode 插件规范打包与端到端验收（P1）**
  * 编写面向 zcode / Cursor 的 Plugin 安装包、Skill 模板与 5 个核心斜杠命令；
  * 在真实业务空间（如 `fiction_procure_space`）中验证“查、修、馈、环”完整闭环。

---

## 11. 远景演进：全域业务语义中枢（表 + API/MCP + 动作，SL-13、SL-14）

我们对本体语义层的定位不仅是“分析型数仓表上的 SQL 翻译器”，而是**全域业务语义中枢（Enterprise Semantic Hub）**。

### 10.1 数据源的双模态：从 Table 到 API / 外部 MCP
* **物理表来源（Table-backed）**：适合大规模、批处理与 OLAP 分析型数据（如历史订单表、账单表）。
* **接口/工具来源（API/MCP-backed）**：业务应用（如 CRM、ERP、工单系统）通过自身的 OpenAPI 或 MCP 接口接入平台。
  * 实体属性既可以绑定物理表列，也可以绑定实时 API 的输出字段（例如：`Customer.live_credit_score` 绑定调用风控系统的 MCP 接口实时获取最新分值）。
  * 平台将数据集绑定扩展支持 `source_kind: api` 或 `source_kind: mcp_tool`。

### 10.2 读写完整生命周期：状态（State）与动作（Action）
* **读语义（State）**：实体属性、关系图谱与聚合指标。
* **操作语义（Action）**：业务应用暴露的 MCP 操作工具（如 `approve_refund(order_id)`、`lock_account(user_id)`）。
  * 平台管理“什么实体支持什么动作、动作的参数约束与前置规则（Rules）”。
  * 智能体不仅能查询“这个客户有哪些逾期订单”，还能在本体规则校验通过后，调用绑定的业务应用 MCP 工具发起操作。
* **定位升维**：这一特性让平台与 Cube、dbt 等传统 SQL 语义层产生代差级跃迁，直接具备了对标 Palantir Foundry 核心操作中枢（Operational Ontology）的能力。
