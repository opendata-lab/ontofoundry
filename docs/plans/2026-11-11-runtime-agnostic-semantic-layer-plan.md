# 运行时无关本体语义层（面向外部 Agent）实施计划

设计：[2026-11-11 面向外部智能体（zcode 等）的运行时无关本体语义层设计](../design/2026-11-11-runtime-agnostic-semantic-layer-for-agents.md)。

## PR 1：平台级个人访问令牌（PAT）与认证改造（后端与前端）

- **数据层**：新增 Alembic 迁移 `user_access_tokens`（`id`, `user_id`, `name`, `token_hash`, `scopes`, `last_used_at`, `expires_at`, `created_at`）；
- **服务层（`services/tokens.py`）**：实现 PAT 随机生成（带 `ont_pat_` 前缀）、PBKDF2/HMAC 哈希存储、校验及作废；
- **认证中间件（`api/auth.py`）**：`_ontology_principal` 增加对 `ont_pat_` 令牌的识别，解析为对应用户的 `Principal`，不再受限于静态管理员映射；
- **前端设置（`pages/ProfileOrSettings.tsx`）**：新增“开发者令牌 / PAT”面板，支持生成令牌（仅生成时可见一次）、查看使用记录与撤销；
- **测试**：PAT 签发、多端并发校验、过期拦截、撤销后失效、空间权限动态跟随用户角色。

## PR 2：统一网关 MCP 端点与空间动态路由（后端）

- **网关路由（`api/mcp.py`）**：新增通用端点 `/api/v1/ontology/mcp`（不绑定 URL 中的 `workspace_id`）；
- **多空间工具实现**：
  - `list_spaces`：列出当前 PAT 用户在所有空间的角色与当前 `version_hash`；
  - `search_ontology`：支持可选参数 `space_ids: list[str]`，默认在用户所有可读空间内检索；
  - `get_entity_subgraph`：必须传 `space_id`，校验用户空间可读权限；
- **审计中间件**：在 MCP JSON-RPC 请求入口拦截记录 `user_id`、`client: zcode`（来自 User-Agent 或 Header）、`tool`、`space_id` 与时间戳；
- **测试**：跨空间联合检索、无权空间拒绝、单空间过滤、网关与旧版单空间 MCP 共存测试。

## PR 3：语义版本指纹（Version Hash）与防漂移 ETag（后端）

- **指纹生成（`services/ontology_version.py`）**：
  - 定义规范化语义哈希算法：按空间已发布的实体、属性、度量、关联与绑定的有序定义计算 SHA-256；
  - 发布新版本或变更时自动触发版本号与 `version_hash` 刷新；
- **MCP 元数据与条件查询**：
  - 所有 MCP 响应统一包装 `_meta: { space_id, ontology_version, version_hash }`；
  - `get_entity_subgraph` 支持 `if_version_matches`，匹配时返回轻量 `NOT_MODIFIED`；
  - 工具 `check_space_version` 实现；
- **废弃标记与自愈错误**：
  - 度量与实体定义增加 `deprecated`、`deprecation_reason`、`superseded_by` 字段；
  - 增加业务错误 `ERR_SEMANTIC_VERSION_DRIFT`（返回建议自愈动作 `suggested_action`）；
- **测试**：版本发布后 Hash 自动变化、ETag 匹配拦截、软废弃警告输出、自愈错误抛出。

## PR 4：语义能修与能馈——提案生成、反馈工单与审阅闭环（后端与前端）

- **数据层**：新增 Alembic 迁移 `agent_feedbacks` 表（`id`, `space_id`, `created_by_user_id`, `target_concept`, `category`, `description`, `dialogue_context`, `status`, `review_proposal_id`, `created_at`）；
- **语义能修（`propose_ontology_mutation` 工具）**：
  - `api/mcp.py` 实现结构化变更工具，支持 `create` / `update` / `deprecate` 对象类型、属性、关系、度量与绑定；
  - 复用平台原生的原子化提案检查（`parse_agent` / `trial_apply`），通过后直接生成当前空间的 Proposal Batch；
  - 支持 Admin 权限直合配置（`auto_merge_if_admin`）；
- **语义能馈（`submit_ontology_feedback` 工具）**：
  - `api/mcp.py` 增加轻量反馈提交，记录上下文对话并生成工单；
- **前端审阅页**：
  - 在工作空间提案/审阅看板中增加“外部智能体提案与反馈”视图，支持 Diff 对比、一键将反馈转化为修改提案、核准合并；
- **测试**：结构化提案生成与校验、非法来源列拦截、反馈提交入库、反馈转提案并合并流程。

## PR 5：通用 Agent Plugin、Skill 与斜杠命令封装

- **包目录**：`integrations/plugins/ontofoundry-plugin/`：
  - `plugin.json`：声明 MCP 网关服务连接模板与斜杠命令入口；
  - `skills/semantic-grounding/SKILL.md`：编排语义对齐执行工作流（语义优先、版本感知自愈、闭环修/馈触发）；
  - `commands/`：预置 5 个核心斜杠命令模板（`/onto-search`, `/onto-metric`, `/onto-sync`, `/onto-propose`, `/onto-feedback`, `/onto-spaces`）；
  - `rules/ontology-alignment.md`：版本防漂移校验规约、软废弃主动告警规约；
- **客户端接入指南**：编写针对 zcode、Cursor、Claude Code 等客户端的安装与配置示例；
- **端到端演练**：在虚构工作空间（如 `fiction_procure_space`）模拟“查、修、馈、环”全流程演练。
- **端到端演练**：在虚构工作空间（如 `fiction_procure_space`）模拟“长会话版本漂移自愈”与“口径纠偏反馈回流”全流程。

## 验证与验收

- 每个后端 PR 执行全量 `pytest` 与 `ruff check`；
- 前端 PR 运行 `vitest` 与 1440×900 视觉回归测试，局域网 IP 验证；
- 最终验收：在真实 zcode 客户端加载该 Plugin，输入业务问题验证概念检索、版本漂移自动检测与反馈回流。
