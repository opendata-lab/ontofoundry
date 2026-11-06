# 会话数据表范围与 AI 可读读取实施计划

设计：[2026-11-06 会话数据表范围与 AI 可读的结构化读取](../design/2026-11-06-table-scope-and-ai-ready-reads.md)。按 T7 先做 PR 1、2。

## PR 1：会话表范围（后端）

- Alembic 迁移：`modeling_sessions.table_scope`（`all`/`selected`，默认 `all`）；已有会话 `linked_tables` 非空设 `selected`，其余 `all`。
- `api/modeling.py`：会话读写返回和接收 `table_scope`；去掉 `linked_tables` 的 200 上限；契约、Pydantic 模型、前端类型同步。
- `services/dataset_sources.py`：新增按会话解析范围的函数（`all` 取当前已同步未缺失表；`selected` 跳过已不可用的表并返回略过清单）；`registered_table_catalog` 返回 `observed_at`。
- `api/agent_conversation.py`：运行开始按范围解析，略过的表写入运行记录。
- `services/connections.py`：去掉会话所选表对删除连接的阻止。
- 测试：迁移前后、`all` 包含后续同步的表、缺失表略过不报错、删连接不再被会话阻止。

## PR 2：选表弹窗与左侧摘要（前端）

- 重写 `components/TableMaterialPicker.tsx`：Ant Design `Table`、三个筛选加搜索、跨分页全选、同步时间列、全选全部保存为 `all`。
- `pages/BuilderPage.tsx`：左侧改为摘要。
- 测试：组件测试覆盖筛选后全选、全选全部、清空、`all` 与 `selected` 保存；1440×900 截图对比与 `npm run test:visual`；局域网 IP 验证一次。

## PR 3：读取器（技能脚本）

- `shared/scripts/read_input.py`：文本改行号纯文本与分页提示；新增 JSON 大纲、路径区间、检索；CSV 概览、行列切片、过滤；`search_tables`、`describe_tables` 读本轮表结构快照。
- `init_workflow.py` 删除全量读表批次；`plan.md`、`extract.md`、`extract-tables.md` 改为先检索后读列、证据写引用。
- 隔离测试按 `integrations/dataagent/README.md` 解压 ZIP 运行；预算测试更新。

## PR 4：工作包瘦身、提交时收据与范围校验（后端）

- 工作包只放范围摘要，表结构快照作为运行文件上传，修正轮复用。
- 提交时按实际用表生成小份可读收据，回填证据行号；新增 `TABLE_NOT_IN_SESSION_SCOPE`。
- 每次建模运行都提供 MCP 配置（取消“仅已发布空间”的限制）。

## PR 5：运行时样例与统计（平台 MCP）

- `sample_table` 工具：复用 `table_preview`，有限样本统计，发起人实例读取权限放行，每次运行限定调用次数。
- 技能说明：样例只作提示，不作证据。

## 验证

每个 PR：`apps/api` 全量 pytest、`ruff`；前端 PR 跑 vitest 与视觉测试；技能 PR 重新打包并跑隔离测试。全部完成后做一次真实建模验收（默认全选的空间），对比改前的 token 用量。
