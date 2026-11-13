# 外部智能体接入本体语义层设计

日期：2026-11-11，2026-11-12 修订。状态：首版已确认（SL-01～SL-03、SL-09），第 10 节为未确认的后续方向。来源：外部编程与分析智能体（Claude Code、zcode 等）读取 OntoFoundry 本体语义的需求。

实施步骤和验收见[实施计划](../plans/2026-11-11-runtime-agnostic-semantic-layer-plan.md)。

## 1. 背景

DataAgent 通过每个工作空间各自的 MCP 地址读取本体，使用部署时配置的固定令牌（[固定 MCP 令牌](2026-10-22-fixed-mcp-token.md)）。外部智能体直接沿用这套方式有三个问题：

1. **配置随空间增加**：每个空间一个地址，用户跨采购、销售等多个空间提问时要为每个空间配置一个 MCP 服务。
2. **调用者身份不可追溯**：固定令牌以空间最早加入的管理员身份读取，所有调用方共用一个身份，也拿到管理员可见的映射。
3. **固定令牌不能给个人**：它是部署级凭据，持有者可读任一已知空间。

首版只解决读取：外部智能体用个人身份查到已发布的语义定义和授权可见的映射，业务取数仍由已有查询平台按调用者权限执行。

## 2. 已确认决定

| 编号 | 决定 | 状态 |
|---|---|---|
| SL-01 | **兼容单空间 MCP，新增用户网关**：现有按空间配置的 MCP 地址、凭据、工具和协议不变。新增 `/api/v1/ontology/mcp`，只提供 `list_spaces`、`search_ontology`、`get_ontology` 三个只读工具，支持跨空间检索。网关不执行业务数据查询，不提供实例与文档事实工具。两个入口共用现有本体读取服务。来源：现有 MCP；属于接入方式，不进入本体模型。 | 2026-11-12 用户确认 |
| SL-02 | **个人访问令牌（PAT）**：网关只接受绑定用户的个人令牌，每次调用按该用户当前的空间成员关系和令牌权限范围授权。范围必含 `ontology:read`，可选 `mappings:read`（返回物理映射和 SQL 参考）。令牌不过期，用户可随时撤销。用户用现有登录会话签发、查看和撤销，首版只提供接口；登录对接各类统一认证的方式见 [OAuth 登录用户信息钩子](2026-11-12-oauth-login-hook.md)。来源：常见个人访问令牌机制；属于接入鉴权。 | 2026-11-12 用户确认；不过期 2026-11-12 用户确认 |
| SL-03 | **网关调用记录**：每次工具调用在数据库存一条记录：调用者、令牌、工具、读取的空间及其版本、调用参数、完整返回内容、结果状态与错误、耗时，另有扩展字段；只原样记录请求和返回，服务端不另行加工统计。不存令牌。用于审计、改进工具，并为日后把外部提问转成建模输入（第 10 节 SL-15）保留素材。来源：固定令牌无法追溯调用者的缺口；属于平台运行记录，不进入本体模型。 | 2026-11-12 用户确认；入库、字段及保存完整返回 2026-11-12 用户确认 |
| SL-09 | **客户端插件**：仓库根目录新建 `plugins/ontofoundry/`，采用 Claude Code 插件格式（ZCode 兼容读取），包含网关 MCP 配置和外部 Skill；仓库根目录的 `.claude-plugin/marketplace.json` 列出该插件，用户按仓库名添加。opencode 没有插件包格式，直接使用同一个 Skill 目录并按说明配置 MCP。`integrations/dataagent` 保持不变。来源：Claude Code 与 ZCode 的插件规范、Agent Skills 格式；属于客户端分发，不进入本体模型。 | 2026-11-12 用户确认 |

**与固定令牌设计的关系**：[MT-03](2026-10-22-fixed-mcp-token.md) 规定外部访问只用固定令牌，并删除了按空间签发的服务令牌。SL-02 修订这一点：用户网关使用个人令牌。两者用途不同：固定令牌和建模运行凭据供 DataAgent 在单空间入口使用；个人令牌绑定一个用户，只用于网关，权限不超过该用户的成员身份。单空间入口仍只接受固定令牌、建模运行凭据和登录会话。

## 3. 首版范围

| 包含 | 不包含（见第 10 节） |
|---|---|
| 个人令牌的签发、列表、撤销接口 | 个人设置页面、MCP 客户端浏览器授权（SL-16，首版之后实施） |
| 网关的三个只读工具，跨空间检索 | 实例、文档事实、实体解析工具；业务数据查询 |
| 调用记录表 | 调用记录的查询界面、清理策略、转为建模会话 |
| 客户端插件（Claude Code、ZCode）及外部 Skill（opencode 直接使用） | 斜杠命令、命令与子智能体 |
| 沿用已发布版本的 `version_id` | 条件读取、废弃标记、反馈与变更提案 |

## 4. 接入与鉴权

### 4.1 两个入口

| 入口 | 地址 | 接受的凭据 | 用途 |
|---|---|---|---|
| 单空间 MCP（已有） | `/api/v1/ontology/workspaces/{workspace_id}/mcp` | 固定令牌、建模运行凭据（`ofrun.`）、登录会话 | DataAgent、建模运行、已有客户端 |
| 用户网关（新增） | `/api/v1/ontology/mcp` | 个人令牌（`ofpat.`） | Claude Code、zcode 等个人客户端 |

凭据按入口隔离：单空间入口遇到个人令牌返回“本体令牌无效”（现有逻辑对未知令牌即如此）；网关拒绝固定令牌、建模运行凭据和登录会话；管理接口沿用现有规则，拒绝任何 `Authorization` 头，因此个人令牌不能用来签发令牌。

协议处理与单空间入口相同（MCP 2026-07-28 请求级 HTTP JSON，兼容旧版 `initialize`），两者共用一个 JSON-RPC 处理层，各自注册工具和鉴权依赖。

令牌只写在客户端的 MCP 配置里，由客户端作为 `Authorization` 请求头发送，不在对话中输入，模型看不到令牌。配置中通过环境变量或插件的敏感设置引用令牌，不直接写入明文。

客户端配置示例（Claude Code，令牌放在环境变量 `ONTOFOUNDRY_TOKEN`）：

```json
{
  "mcpServers": {
    "ontofoundry": {
      "type": "http",
      "url": "https://ontofoundry.example.com/api/v1/ontology/mcp",
      "headers": { "Authorization": "Bearer ${ONTOFOUNDRY_TOKEN}" }
    }
  }
}
```

### 4.2 个人令牌

| 项 | 规定 |
|---|---|
| 格式 | `ofpat.` 加 32 字节随机数的 base64url 编码，签发响应中只出现一次 |
| 存储 | 新表保存令牌 ID、所属用户、名称、范围、令牌的 SHA-256 摘要、创建时间、最近使用时间、撤销时间；不保存明文 |
| 范围 | `ontology:read` 必选，`mappings:read` 可选；`instances:read` 不提供，网关没有实例工具 |
| 有效期 | 不过期；撤销后立即失效 |
| 接口 | `POST /api/v1/auth/tokens`（名称、范围）签发；`GET /api/v1/auth/tokens` 列出本人令牌的元数据；`DELETE /api/v1/auth/tokens/{token_id}` 撤销。均要求登录会话，只能管理本人令牌 |
| 校验 | 按摘要查找未撤销的令牌，更新最近使用时间，生成该用户的身份 |

网关身份沿用现有 `Principal`：用户为令牌所属用户，`service_token_id` 为 `pat:<令牌 ID>`，`scopes` 为令牌范围，不绑定空间。现有读取服务据此裁剪物理投影（`can_read_mappings` 对带 `service_token_id` 的身份检查 `mappings:read`），游标的授权指纹也包含令牌 ID 和范围，所以不同令牌的游标不能混用。

### 4.3 成员检查

现有单空间读取对非成员也返回已发布的语义定义（`get_ontology`、`search_ontology` 本身不要求成员身份）。网关不沿用这一点：每次调用、每次翻页前，网关先确认用户当前是目标空间成员，再调用读取服务。用户被移出空间后，该空间立即从目录和默认检索中消失，显式请求返回统一的空间不可访问错误，不区分空间不存在和无权访问。

## 5. 网关工具契约

| 工具 | 入参 | 行为 |
|---|---|---|
| `list_spaces` | 无 | 列出用户当前加入的空间：`workspace_id`、名称、角色、`version_id`、`version_number`。未发布的空间两个版本字段为 `null`。 |
| `search_ontology` | `query`；可选 `workspace_ids`、`kinds`、`expand`、`limit`、`cursor`。除 `workspace_ids` 外与单空间入口相同 | 省略 `workspace_ids` 时检索全部成员空间。结果按空间分组，每组即单空间检索的结果（`workspace_id`、`version_id`、`items`、`total`、`next_cursor`、`retrieval`、`unmatched_terms`），组内排序不变，`limit` 按组生效；组按空间名称排序，不做跨空间统一排序。续页时传入该组的 `next_cursor`，`workspace_ids` 只含该组空间，其余参数不变。 |
| `get_ontology` | `workspace_id`；其余参数与单空间入口相同（`ids`、`kinds`、`include`、`limit`、`cursor`） | 读取一个空间的已发布定义和有权限的投影，响应带 `workspace_id`、`version_id`，分页和字段分段沿用现有规则。 |

错误：

| 情况 | 工具错误 `code` |
|---|---|
| 显式请求的空间不存在或用户不是成员（含 `workspace_ids` 中任一个） | `workspace_unavailable` |
| 检索涉及的空间超过 10 个 | `search_limit_exceeded`，`reason` 为 `workspace_count`，`limit` 为 10 |
| 各组结果合计超过 110,000 字节（与现有工具的单次响应预算相同） | `search_limit_exceeded`，`reason` 为 `response_size` |
| 游标无效或已失效（版本更新、成员或令牌变化） | `cursor_invalid`（沿用现有） |
| 某个空间的单空间检索出错（如单页超过预算的 `response_too_large`） | 该错误的 `code`，整次失败 |

超限或出错时整次返回错误，不返回部分结果。用户没有任何成员空间时，`list_spaces` 和默认检索返回空列表。Agent 可用 `list_spaces` 选出相关空间后显式传入 `workspace_ids`，或降低 `limit` 后重试。

例如用户是虚构星港采购空间和星港销售空间的成员，检索“订单金额”返回两组结果，各自带空间和版本；Agent 按空间分别展示两个定义，由用户确认采用哪一个。

## 6. 调用记录

每次 `tools/call` 分两步记录，失败的调用也留痕：

1. **开始**：通过鉴权、执行工具前插入一行，`outcome` 为 `started`，写入调用者、工具、参数和目标空间，并立即提交（独立于读取服务的数据库事务）。
2. **结束**：工具返回后更新同一行，写入完整返回、`ok` 或 `error`、错误码与消息、耗时。

进程崩溃、超时或连接中断导致没有返回时，该行停在 `started`，即为未完成的失败调用。记录写入失败不影响工具返回，只记应用错误日志。令牌无效、已撤销等鉴权失败没有可信的调用者，不写入本表，只记应用日志。

| 字段 | 内容 |
|---|---|
| `id`、`created_at` | 记录标识和时间 |
| `user_id`、`token_id` | 调用者和令牌 |
| `request_id` | JSON-RPC 请求 ID |
| `tool` | 工具名 |
| `workspaces` | 本次读取的每个空间：`workspace_id`、`version_id`、`version_number` |
| `arguments` | 校验后的调用参数（如 `query`、`workspace_ids`、`ids`、`kinds`、`limit`），不含 `cursor` 原文，只记是否翻页 |
| `response` | 工具返回给客户端的完整结构化内容（成功时为结果，失败时为错误体），与客户端收到的一致 |
| `outcome` | `started`（已开始未结束）、`ok` 或 `error` |
| `error_code`、`error_message` | 失败时的工具错误码和中文消息 |
| `duration_ms` | 耗时 |
| `extra` | 扩展字段（JSON），首版为空，留给后续元数据 |

例如用户检索“净采购额 含税”，记录 `arguments` 为该检索词，`workspaces` 为采购空间第 13 版和销售空间第 7 版，`response` 为客户端收到的两组结果（其中 `unmatched_terms` 含“含税”）。命中数、未匹配用语等统计日后从 `arguments` 和 `response` 读取，不在写入时计算。管理员日后可据此发现本体缺少“含税”口径。

令牌只存其 ID。完整返回可能含物理映射和 SQL 参考（调用者有权看到的内容），每行最多约 110,000 字节，PostgreSQL 会压缩大字段，但表随调用量增长；首版没有查询界面和自动清理，只能由有数据库权限的运维查看，查看权限与清理策略随 SL-15 设计。查询平台的执行记录由查询平台自己保存。

## 7. 客户端插件（SL-09）

```text
.claude-plugin/marketplace.json        仓库插件目录，列出 ./plugins/ontofoundry
plugins/
  ontofoundry/
    .claude-plugin/plugin.json         插件清单（name、version、description、userConfig）
    .mcp.json                          网关地址与 Authorization 头
    skills/
      ontology-grounding/SKILL.md      外部 Skill：检索、精读、过滤、缺项处理与第 8 节版本规则
    README.md                          令牌签发和三种客户端的安装、配置说明
```

| 客户端 | 读取方式 | 依据 |
|---|---|---|
| Claude Code | 添加 `opendata-lab/ontofoundry` 插件目录后安装；令牌通过插件 `userConfig` 的敏感项填入，`.mcp.json` 中引用为 `Bearer ${user_config.ontofoundry_token}` | [插件](https://code.claude.com/docs/en/plugins)、[插件参考](https://code.claude.com/docs/en/plugins-reference) |
| ZCode | 清单查找顺序为 `.zcode-plugin/plugin.json`、`.claude-plugin/plugin.json`，因此只维护一份清单；从 GitHub 仓库添加插件目录后安装 | [ZCode 插件](https://zcode.z.ai/en/docs/plugin) |
| opencode | 插件是 JS/TS 模块，不读插件包；Skill 放入或指向 `.opencode/skills`、`.claude/skills`、`.agents/skills` 之一，MCP 写入 `opencode.json` 的 `mcp.servers`（`"type": "remote"`、`"oauth": false`、`"Authorization": "Bearer {env:ONTOFOUNDRY_TOKEN}"`） | [Skills](https://opencode.ai/docs/skills)、[MCP](https://opencode.ai/docs/mcp-servers) |

插件不带本地工具代码，工具全部来自网关。SKILL.md 只用 `name`、`description` 两个通用字段，描述不超过 1024 字符（ZCode 超长会忽略该 Skill）。

以下两点官方文档未写明，在实施步骤一中联验：ZCode 是否读取 `.claude-plugin/marketplace.json`（其文档只写“仓库根目录的 `marketplace.json`”）；ZCode 敏感 `userConfig` 暂不能在界面填写时，令牌如何提供。联验不通过时按结果调整本节，再进入步骤二。

## 8. 版本一致性

首版不新增版本协议。每个检索结果组和 `get_ontology` 响应都带 `version_id`，`list_spaces` 带当前 `version_id`。外部 Skill 规定：

- 同一轮回答使用的定义来自同一空间的同一 `version_id`；发现版本变化时重新检索和读取。
- 回答中注明采用的空间和版本；跨空间的命中分别说明口径，不合并。
- 生成查询前可用 `list_spaces` 复核相关空间的当前版本。

## 9. 与现有架构的关系

| 层次 | 首版影响 |
|---|---|
| MCP 与鉴权 | 新增网关路由、个人令牌鉴权依赖和令牌管理接口；单空间入口的路由、鉴权和工具不变。 |
| 读取服务 | 复用 `mcp_ontology` 与 `ontology_search`，不改其授权规则；跨空间检索由网关逐个空间调用单空间检索后分组。 |
| 数据库 | Alembic 新增个人令牌表和网关调用记录表，引用用户表；其他表不变，无需迁移数据。 |
| DataAgent | 继续使用单空间入口、固定令牌和建模运行凭据，配置不变。 |
| 部署 | 同一应用升级。随附的 nginx 已整体转发 `/api/`；自建反向代理若按路径放行，需加入 `/api/v1/ontology/mcp`。 |

## 10. 后续方向（未确认）

以下方向未确认，不在首版范围；开工前各自按 AGENTS.md 说明来源、语义还是执行、删掉会失去什么，并写设计和计划。详细记录见 [TODO](../TODO.md)“本体 MCP”。

| 编号 | 方向 | 说明 |
|---|---|---|
| SL-04 | 反馈回流 | Agent 提交口径争议，平台生成待审反馈，管理员转为提案；不直接改已发布本体 |
| SL-05 | 响应统一附带版本元数据 | 首版已在响应中带 `version_id`，是否统一为 `_meta` 待定 |
| SL-06 | 条件读取 | 按 `version_id` 判断未变化时返回轻量结果，节省重复读取；不做版本差异摘要，版本变化时 Agent 重新检索和读取 |
| SL-07 | 废弃标记 | 元素增加废弃状态和替代项；需说明来源，Ossie 与现有模型能否表达 |
| SL-08 | 语义漂移错误 | 引用的元素已不存在或改名时返回可指导重读的错误 |
| SL-10 | 查询委派 | 网关把确认后的口径交给查询平台执行；首版由 Agent 自行调用查询工具 |
| SL-11 | 斜杠命令 | 在 SL-09 的插件内预置检索、指标、空间等命令 |
| SL-12 | 结构化变更提案 | 外部提交复用 `parse_agent`、`trial_apply`、`store_batch`，需合法的会话与基线上下文，一律经人工审阅 |
| SL-13 | 接口来源绑定 | 属性绑定业务 API 或 MCP 工具的返回值；与“执行细节不进入模型”的原则相关 |
| SL-14 | 业务动作 | 实体绑定业务系统的操作工具；与决定 #37（删除业务动作）冲突 |
| SL-15 | 调用记录转建模输入 | 从调用记录的参数和返回中筛选（检索词、未匹配用语、零命中）后生成建模会话或待处理事项，并设计记录的查看与清理 |
| SL-16 | MCP 客户端浏览器授权 | **已决定在首版之后实施**：平台按 MCP 授权规范作为授权方（发现元数据、客户端注册、PKCE、访问与刷新令牌），用户经平台登录（依赖 [OAuth 登录用户信息钩子](2026-11-12-oauth-login-hook.md)）后授权客户端；网关地址和工具不变，个人令牌继续可用。ZCode、opencode 文档均支持远程 MCP 的 OAuth，Claude Code 待核实 |

## 11. 参考

- [Palantir Ontology MCP 概览](https://palantir.com/docs/foundry/ontology-mcp/overview/)、[鉴权与授权](https://palantir.com/docs/foundry/ontology-mcp/authentication-and-authorization/)：一个 MCP 服务器对应一个本体，令牌权限取用户权限、应用限制和操作范围的交集。
- [Claude Code MCP 配置](https://code.claude.com/docs/en/mcp)、[Claude Code Skill 配置](https://code.claude.com/docs/en/skills)
