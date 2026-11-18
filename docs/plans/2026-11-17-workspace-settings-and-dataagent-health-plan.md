# 空间设置重整与 DataAgent 连通性归位实施计划

日期：2026-11-17。设计见[空间设置重整与 DataAgent 连通性归位设计](../design/2026-11-17-workspace-settings-and-dataagent-health.md)。基于当前 `main`（已合入[用户管理与空间公开](../design/2026-11-12-user-management.md)），无数据库结构变化，不涉及 Alembic 迁移。

## 任务

1. **后端接口归位（WS-01）**：
   - `apps/api/src/ontofoundry_api/services/dataagent_health.py`：`dataagent_health(settings: Settings)` 移除 `workspace_id` 参数，固定使用 `session_ref="ontofoundry:system:diagnostics"`。
   - `apps/api/src/ontofoundry_api/api/workspaces.py`：删除 `GET /{workspace_id}/settings/dataagent-health`。
   - `apps/api/src/ontofoundry_api/api/system.py`：新增 `GET /api/v1/system/dataagent-health`（`tags=["system"]`，仅平台管理员，复用 `platform_admin`）。

2. **前端页面改造（WS-02、WS-03、WS-04）**：
   - `apps/web/src/pages/BuilderPage.tsx`：第 155 行 `!capabilities.agent_configured` 阻断文案改为 `"DataAgent 建模服务未配置，请联系部署管理员"`；核对并更新 `BuilderPage.test.tsx`。
   - `apps/web/src/api/types.ts`：清理未再使用的 `DataAgentHealth` 类型（确认全库无残留引用）。
   - `apps/web/src/pages/SettingsPage.tsx`：按设计第 4 节重构，移除 `DataAgent 连通性` 区块与请求，移除 `max-w-settings`；整合 `空间信息`（`@container` + `FormRow` + `slug` 复制 + 自适应 `说明` + 表单内保存/重置与脏态同步）和底部分割区 `空间公开`；重构 `空间成员`（`PanelToolbar` + `+ 添加成员` 内联渐进展开栏 + `用户名 / 角色 / 操作` 三列表格 + `Popconfirm` 二次确认移除 + `Skeleton` / 重试 / `Empty` / 分页 + `Panel footer` + `useErrorMessage` 浮动报错）。

3. **文档与合约清单同步**：
   - 已同步更新 [2026-10-17-ui-visual-consistency.md](../design/2026-10-17-ui-visual-consistency.md)、[2026-11-11-runtime-agnostic-semantic-layer-for-agents.md](../design/2026-11-11-runtime-agnostic-semantic-layer-for-agents.md)、[2026-09-21-dataagent-conversation-sdk-integration-design.md](../design/2026-09-21-dataagent-conversation-sdk-integration-design.md)、[2026-11-16-agent-platform-interface.md](../design/2026-11-16-agent-platform-interface.md)、[2026-10-16-core1-p2-api-contract.md](2026-10-16-core1-p2-api-contract.md) 与[演示手册](../demo/coffee-channel-sales/演示手册.md)。

4. **测试与视觉基准**：
   - 后端：`apps/api/tests/test_dataagent_diagnostics.py` 改为验证 `GET /api/v1/system/dataagent-health`（覆盖四项检查、缺失 Agent、未登录返回 401、非平台管理员返回 403、原工作空间路由返回 404）；`apps/api/tests/test_workspace_access.py` 从 `MANAGE` 移除 `W + "/settings/dataagent-health"`。
   - 前端：`apps/web/src/pages/SettingsPage.test.tsx` 覆盖无 DataAgent 连通性区块、表单内保存/重置与脏态清除、空间公开开关确认弹窗、内联展开按用户名搜索添加成员、三列表格与行内角色调整、`Popconfirm` 移除确认、非管理员 `NoAccessResult` 及加载失败重试。
   - 视觉与验证：更新 `apps/web/e2e/visual/fixtures.ts` 和 `apps/web/e2e/visual/lists-settings.spec.ts`（删除 `settings-health.png` 用例与旧快照，更新 1440×900 `settings.png` 基准并按一致性设计第 3 节检查对齐、字号、状态和密度）；全部编辑完成后统一运行后端 pytest、ruff、前端 tsc/eslint/vitest 与 `npm run test:visual`。

## 验收

| 场景 | 预期 |
|---|---|
| DataAgent 诊断接口 | `GET /api/v1/workspaces/{id}/settings/dataagent-health` 返回 404；`GET /api/v1/system/dataagent-health` 平台管理员返回四项检查；`login` 模式下未登录 401、非平台管理员 403 |
| 构建页提示 | 未配置 DataAgent 时不再提示“去空间设置” |
| 空间设置全宽排版 | 1440×900 下无右侧灰底空洞、无 DataAgent 连通性、两块面板一屏内完整呈现 |
| 表单与成员安全护栏 | 未修改时保存禁用；`+ 添加成员` 就地展开只搜用户名与选干净角色；移除需 `Popconfirm` 确认；初始加载用骨架屏，报错浮动显示 |
| 回归验证 | 后端测试、`ruff`、前端 `tsc`/`eslint`/`vitest` 与 `npm run test:visual` 全部通过 |

## 发布与回退

- **发布**：常规前后端应用升级，无数据库迁移。
- **回退**：直接回退版本镜像即可。
