# 外部智能体接入本体语义层实施计划

日期：2026-11-12。设计见[外部智能体接入本体语义层设计](../design/2026-11-11-runtime-agnostic-semantic-layer-for-agents.md)，首版范围按其第 2、3 节（SL-01～SL-03、SL-09）。工期按一人估算。

## 1. 职责划分

| 参与方 | 职责 | 首版输出 |
|---|---|---|
| OntoFoundry 网关 | 按个人令牌和成员关系提供已发布定义、指标公式与固定过滤、关系、授权可见的数据集和表列映射 | `workspace_id`、`version_id`、元素 ID、定义、可用的物理投影 |
| 外部 Agent 与 Skill | 检索口径、发现歧义、选择来源，按目标引擎方言构造查询，调用查询工具并解释结果 | 口径、条件、来源、SQL 或查询请求及结果证据 |
| 查询平台 | 按调用者实际授权校验连接和库表，执行只读查询、限流和审计 | 查询结果或权限／执行错误 |

例如在虚构星港销售空间，已付款金额 100 元、已退款 20 元、未付款 30 元。网关返回“净销售额等于已付款金额减退款金额”的定义和来源映射；查询平台按该口径返回 80 元。查询平台拒绝访问退款表时，Agent 说明缺少数据访问权限，引用口径并标明查询未完成。

## 2. 现状核对（2026-11-12）

| 项目 | 当前实现 | 首版落点 |
|---|---|---|
| MCP 协议 | `api/mcp.py`：MCP 2026-07-28 请求级 HTTP JSON、旧版 `initialize`、工具发现；工具错误把 `ServiceError.code` 转小写，只透传 `filtered_count`、`warnings`、`instance_change_sequence` | 抽出共用 JSON-RPC 处理层；透传字段加入 `reason`、`limit` |
| 鉴权 | `api/auth.py`：`_ontology_principal` 只认固定令牌和 `ofrun.`，其余令牌 401；`current_principal` 拒绝任何 `Authorization` 头 | 新增 `ofpat.` 校验依赖，仅挂在网关路由 |
| 读取服务 | `services/mcp_ontology.py` 的 `invoke` 和 `services/ontology_search.py` 的 `search_ontology`；不要求成员身份；游标绑定空间、版本、工具、参数和授权指纹 | 网关先做成员检查再调用；跨空间检索逐个调用 `search_ontology`，传入不含 `workspace_ids` 的单空间参数 |
| 授权 | `services/access.py`：带 `service_token_id` 的身份按 `scopes` 判断映射与实例读取；授权指纹含令牌 ID 与范围 | 个人令牌身份设 `service_token_id="pat:<id>"`，无需改动 |
| 空间目录 | `services/workspaces.py` 的 `list_accessible_workspaces` 返回成员空间、角色、`version_id`、`current_version` | `list_spaces` 直接取用 |
| 令牌与调用记录存储 | 无（MT-03 已删除服务令牌表；没有审计表） | 新增个人令牌表和网关调用记录表 |
| Skill 与插件 | `integrations/dataagent/skills/semantic-grounding/`：先检索再精读、歧义追问、保留指标固定过滤；仓库没有面向外部客户端的插件 | 新建 `plugins/ontofoundry/`（设计第 7 节），原 DataAgent 套件不变 |

## 3. 交付顺序

### 步骤一　验证语义交接，预计半天

1. 在隔离环境准备一个带指标、维度和数据集绑定的虚构空间，用自定义固定令牌把单空间 MCP 配到 Claude Code，确认 `initialize`、`tools/list`、`search_ontology`、`get_ontology` 可用；zcode 用同一地址和 Bearer 头，记录配置方式和协议协商结果。
2. 把 `semantic-grounding` 的检索、精读、过滤和缺项处理改写成外部 Skill，放在 `plugins/ontofoundry/skills/ontology-grounding/`，写明版本规则（设计第 8 节）和“由客户端自己的查询工具取数”的约定；同时建好插件清单、`.mcp.json` 和仓库根目录的 `.claude-plugin/marketplace.json`（设计第 7 节）。本步骤的 `.mcp.json` 临时指向单空间入口和固定令牌，步骤二改为网关和个人令牌。
3. 用同一个指标跑两条路径：只配 MCP 时返回定义、版本和映射；再挂已有查询工具，由查询平台执行并返回结果与证据。现有投影不含查询平台的连接 ID，试点用查询平台已有的授权连接配置对齐。
4. 验证三种客户端的安装：Claude Code 和 ZCode 按仓库名添加插件目录并安装，opencode 按 README 配置 Skill 路径和 `opencode.json`。重点确认设计第 7 节列出的两个未写明事项：ZCode 是否读取 `.claude-plugin/marketplace.json`，以及 ZCode 中令牌的提供方式。

固定令牌持有者可读任一已知空间并取得管理员投影，本步骤只在隔离环境进行。结果写入试点记录；协议或客户端有缺口时先更新设计再进入步骤二。

### 步骤二　交付用户网关，预计 3 至 4 个工作日

前置：[OAuth 登录用户信息钩子](2026-11-12-oauth-login-hook-plan.md) 已实施，现场用户能登录并签发令牌。

1. **个人令牌与调用记录表**：`db_models.py` 新增令牌表和调用记录表，同一个 Alembic 迁移；`services/personal_tokens.py` 负责签发（生成 `ofpat.` 令牌、保存 SHA-256 摘要）、列表、撤销和校验；`api/auth.py` 新增 `/api/v1/auth/tokens` 三个接口（`current_principal`）和网关鉴权依赖 `gateway_principal`；`contracts/` 新增令牌请求与响应模型。
2. **网关**：从 `api/mcp.py` 抽出 JSON-RPC 处理（协议协商、请求头校验、工具结果与错误封装），单空间入口改为调用它且行为不变；新增 `api/ontology_gateway.py` 注册 `/api/v1/ontology/mcp` 与三个工具。工具入参模型放在 `services/ontology_gateway.py`，`tools/list` 由模型生成 JSON Schema。
3. **成员检查与跨空间检索**：每次调用和翻页前检查成员关系，失败返回 `workspace_unavailable`；`search_ontology` 先解析目标空间（显式列表或全部成员空间），超过 10 个返回 `search_limit_exceeded`／`workspace_count`；逐个调用单空间检索并按空间名称分组，合计超过 110,000 字节返回 `search_limit_exceeded`／`response_size`。
4. **调用记录**：按设计第 6 节在 `tools/call` 结束后写一行记录，写入失败只记错误日志，不影响工具返回。
5. **测试**：新增 `tests/test_personal_tokens.py`、`tests/test_ontology_gateway.py`，覆盖第 4 节验收中可自动化的场景；单空间入口现有测试保持通过。完成全部修改后统一运行后端测试和 `make lint`。
6. **插件与文档**：`plugins/ontofoundry/.mcp.json` 改为网关地址和个人令牌；`plugins/ontofoundry/README.md` 写明令牌签发、三种客户端的安装与配置；AGENTS.md 增加 `plugins/` 的说明（外部客户端插件的源码位置，改动后同步版本号）；`docs/concepts/` 只描述模型概念，本次不变。随附的 `apps/web/nginx.conf` 已整体转发 `/api/`，无需修改。

首版不改前端：令牌通过接口签发，个人设置页面按试点反馈排期。

## 4. 验收

| 场景 | 预期 | 自动化 |
|---|---|---|
| 签发、列表、撤销 | 明文只在签发响应出现一次；列表只有元数据；撤销后网关调用返回 401 | 是 |
| 凭据入口隔离 | 网关拒绝固定令牌、`ofrun.` 和登录会话；单空间入口拒绝个人令牌；管理接口拒绝个人令牌 | 是 |
| 范围 | 只有 `ontology:read` 的令牌取不到物理映射和 SQL 参考；加 `mappings:read` 可取得；两个令牌的游标不能互用 | 是 |
| 单空间成员 | 目录只有该空间；传入其他空间 ID 返回 `workspace_unavailable` | 是 |
| 加入第二个空间 | 同一令牌立即能检索两个空间，结果按空间分组并带各自版本 | 是 |
| 移出空间 | 该空间从目录和默认检索消失；旧游标返回 `cursor_invalid` | 是 |
| 检索超限 | 11 个空间返回 `workspace_count`；合计超过预算返回 `response_size`；均无部分结果 | 是 |
| 两次读取之间发布新版本 | 旧游标失效，响应 `version_id` 更新 | 是 |
| 调用记录 | 成功和失败的调用各一行，空间与版本、参数、完整返回、摘要、错误码和消息齐全；完整返回与客户端收到的一致；不含令牌和游标原文 | 是 |
| 单空间入口与 DataAgent | 现有测试通过；DataAgent 原配置联通，建模运行版本固定不变 | 测试 + 联验 |
| 插件安装 | Claude Code、ZCode 按仓库名安装插件后可调用网关；opencode 按 README 配置后可用同一 Skill | 联验 |
| 只装插件（MCP 和 Skill） | 能查到净销售额定义、固定条件、映射和版本，回答区分口径与数值 | 联验 |
| 挂已有查询工具 | 口径一致，虚构数据返回 80 元，查询平台有执行记录；无权表时拒绝执行 | 联验 |

## 5. 发布与回退

- 发布：同一应用和数据库升级，迁移只新增令牌表和调用记录表；DataAgent 和已有客户端无需改配置。
- 回退：停用网关路由即可，两张新表保留不影响单空间入口；需要彻底回退时执行迁移降级删除两张表。

## 6. 后续顺序

多人试点后，按使用情况排定个人设置页、浏览器授权、跨空间统一排序和插件内的斜杠命令。反馈回流、条件读取、废弃标记、结构化提案等见设计第 10 节，各自先写设计。
