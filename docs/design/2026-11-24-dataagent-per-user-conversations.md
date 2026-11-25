# DataAgent 会话按创建人归属设计

日期：2026-11-24。状态：已确认（DU-01～DU-04）。来源：DataAgent 统一账号改造（DataAgent 仓库 `docs/design/2026-11-19-unified-conversation-history-design.md`「独立登录 Widget 的账号归属」）取消了共享会话：宿主转发的每个请求必须带当前登录用户，会话只属于一个用户。本仓库原先在 `X-DataAgent-User-Id` 中传建模会话标识 `ontofoundry:{workspace_id}:{session_id}`（[DataAgent 集成设计](2026-09-21-dataagent-conversation-sdk-integration-design.md) §6.4），需要随之调整。

实施见[实施计划](../plans/2026-11-24-dataagent-per-user-conversations-plan.md)。不涉及核心本体模型（`docs/concepts/` 不变）。DataAgent 侧改造上线前本改动不能单独部署，两边在同一切换窗口上线。

## 1. 现状

- `DataAgentClient` 的用户头是建模会话标识，DataAgent 把它当作一个“每会话一个伪用户”，空间内任何有编辑权的成员都能在同一会话里发问。
- 读时对账（会话列表、单会话读取后在 `BackgroundTasks` 中同步运行状态）和结果结算使用同一个会话标识。
- 部署诊断 `GET /api/v1/system/dataagent-health` 使用固定的 `ontofoundry:system:diagnostics`。

## 2. 已确认决定

| 编号 | 决定 | 说明与来源 | 状态 |
|---|---|---|---|
| DU-01 | **DataAgent 调用以会话创建人身份发出** | `X-DataAgent-User-Id` 改为建模会话 `created_by` 对应用户的 `username`（平台内唯一）。发消息、取消、回答、读消息、下载文件、读时对账与结果结算都用创建人，不论谁触发。DataAgent 站点开启「信任同命名空间用户名」后与 DataAgent 同名账号对应。 | 2026-11-24 用户确认（“widget 传入的用户就是真实用户”） |
| DU-02 | **只有创建人能在会话中发问** | 发消息、取消运行、回答确认/提问由 BFF 校验当前用户是会话创建人，否则 403「只有会话创建人可以在此会话中发消息，请新建自己的会话」。其他有读权限的成员照常查看会话、消息和结果。`SessionRead` 增加 `created_by`，构建页对非创建人禁用输入框并显示同一句说明。 | 2026-11-24 用户确认（“不允许共享会话”） |
| DU-03 | **旧会话解除与 DataAgent 旧对话的绑定** | 旧对话属于已取消的会话伪用户，切换后 DataAgent 中没有归属，只有 DataAgent 管理员能在审计中查看。迁移 `20261124_000001` 清空已有建模会话的 `dataagent_topic_id`、`dataagent_task_id`、`dataagent_run_token`，运行状态回到 `idle`。草稿、提案和材料保留；界面不再显示旧聊天记录，下一条消息开新对话。 | 2026-11-24 用户选择方案 A |
| DU-04 | **部署诊断以请求的平台管理员身份调用** | 诊断接口本来只允许平台管理员，改为以其 `username` 调用 DataAgent，同时验证该账号能看到建模 Agent。 | 2026-11-24 |

## 3. 接口变化

- `SessionRead` 新增 `created_by: str`（用户 ID）。JSON Schema `ontofoundry.session-writes.v1.schema.json` 与前端 `Session` 类型同步。
- 对话 BFF `POST .../agent-conversation/messages`、`/cancel`、`/interactions` 对非创建人返回 403。
- `DataAgentClient(..., username=...)` 取代 `session_ref`；`services/dataagent.py` 提供 `dataagent_client(settings, username)` 和 `session_client(app, session_id)` 两个工厂，其余模块不再各自拼装客户端。

## 4. 取舍

- 不保留旧对话的读取：要保留需由本仓库导出“会话 → 创建人”，再由 DataAgent 一次性补归属，跨仓库脚本成本高于收益（方案 B，未采用）。
- 不按触发人切换身份：同一会话只对应一个 DataAgent 用户，避免同一对话出现多个归属。
