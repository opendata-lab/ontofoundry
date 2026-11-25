# DataAgent 会话按创建人归属实施计划

日期：2026-11-24。设计见[DataAgent 会话按创建人归属设计](../design/2026-11-24-dataagent-per-user-conversations.md)。

## 任务

1. 客户端（DU-01、DU-04）：`services/dataagent.py` 的 `DataAgentClient` 以 `username` 取代 `session_ref`，新增 `dataagent_client`、`session_client`；`api/agent_conversation.py`、`services/modeling_runs.py`、`services/model_result.py` 改用 `session_client`；`services/dataagent_health.py` 与 `api/system.py` 以请求的平台管理员调用。
2. 创建人校验（DU-02）：`api/agent_conversation.py` 的发消息、取消、回答接口调用 `_require_creator`；`contracts/session_writes.py` 的 `SessionRead` 与 `services/sessions.py` 的 `session_data` 增加 `created_by`，重新导出 JSON Schema；`apps/web/src/api/types.ts`、`pages/BuilderPage.tsx` 对非创建人禁用输入框。
3. 迁移（DU-03）：`alembic/versions/20261124_000001_dataagent_per_user.py` 清空旧绑定。
4. 文档：[DataAgent 集成设计](../design/2026-09-21-dataagent-conversation-sdk-integration-design.md) §6.4 指向本设计。

## 验证

- `apps/api`：`pytest`（含 `test_agent_conversation_bff.py` 新增的非创建人用例、请求头断言改为创建人用户名）。
- `apps/web`：类型检查、单元测试，构建页非创建人截图对比（1440×900）。
- 与 DataAgent `feat/user-accounts` 联调：创建人发问成功；另一成员查看会话但输入框禁用、接口 403；旧会话首条消息开新对话；诊断页通过。

## 上线与回退

- 与 DataAgent 账号改造同一窗口：先升级 DataAgent 并在其「Widget 接入」登记本站点（无需站点访问密钥，BFF 从后端无 `Origin` 调用），再升级本仓库并运行迁移。
- 回退：迁移不可逆（旧对话 ID 不保留），回退本仓库代码后旧会话同样从新对话开始。
