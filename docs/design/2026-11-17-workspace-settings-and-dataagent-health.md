# 空间设置重整与 DataAgent 连通性归位设计

日期：2026-11-17。状态：已确认（WS-01～WS-04）。来源：DataAgent 连通性属于部署级检查、不应放在工作空间设置；现行空间设置页使用 `max-w-settings` 导致 1440×900 右侧大面积留白且缺少防误删与状态同步；平台已由[用户管理与空间公开](2026-11-12-user-management.md)确立全平台唯一 `username`，空间设置成员栏应精简为围绕用户名操作，去掉冗余双列和多余描述文字。

实施见[实施计划](../plans/2026-11-17-workspace-settings-and-dataagent-health-plan.md)。不涉及核心本体模型（`docs/concepts/` 不变），不修改 `users` 表结构。

## 1. 现状问题（基于当前 `main`）

1. **作用域错配**：`GET /api/v1/workspaces/{workspace_id}/settings/dataagent-health`（`api/workspaces.py`）检查的是全局环境变量 `Settings.dataagent_*`，`workspace_id` 只用于拼接请求头 `session_ref`。把它放在空间设置页底部，既在每个空间重复展示同一份部署信息，也把服务端地址、`website_id` 与环境变量名暴露给了空间级用户；同时 [BuilderPage.tsx](../../apps/web/src/pages/BuilderPage.tsx) 未配置时仍提示“请先在空间设置中配置 DataAgent”。
2. **版式与安全护栏不足**：[SettingsPage.tsx](../../apps/web/src/pages/SettingsPage.tsx) 四个 `Panel`（空间信息、空间公开、空间成员、DataAgent 连通性）全受 `max-w-settings`（880px）左偏限制，在 1440×900 下右侧空出约 328px 灰底且底部被折叠；「移除」成员无 `Popconfirm` 二次确认与行级锁定；「保存空间信息」在未改动时常亮，表单未同步 `workspace` 刷新，成员加载与失败状态缺少骨架屏和重试入口。
3. **成员表与添加栏信息冗余**：[用户管理设计](2026-11-12-user-management.md)（UM-01）已实现 `users.username` 全平台不区分大小写唯一、不允许重名，但设置页表格仍同时占着 `用户（display_name）` 和 `用户名（username）` 两列，表上方夹着整段说明文字，表底常驻 `AutoComplete` 添加条。

## 2. 已确认决定

| 编号 | 决定 | 说明与来源 | 状态 |
|---|---|---|---|
| WS-01 | **DataAgent 连通性移出空间设置** | 删除 `GET /api/v1/workspaces/{workspace_id}/settings/dataagent-health` 与设置页「DataAgent 连通性」区块；改为平台级只读运维接口 `GET /api/v1/system/dataagent-health`（不绑定 `workspace_id`，需登录会话）。属于部署运维诊断，不进入本体模型。 | 2026-11-17 用户确认 |
| WS-02 | **构建页提示修正** | `BuilderPage.tsx` 在 `!capabilities.agent_configured` 时提示改为“DataAgent 建模服务未配置，请联系部署管理员”，不再引导去空间设置。已配置但连通或 Agent 异常时，发消息仍由对话 BFF 按 [DataAgent 集成设计](2026-09-21-dataagent-conversation-sdk-integration-design.md) §6.9 返回可诊断报错。 | 2026-11-17 用户确认 |
| WS-03 | **空间设置上下铺满两段式布局** | 取消设置页 `Panel` 的 `max-w-settings` 限制，铺满 `PageBody` 宽度（保留 `--settings-max-width` 供详情弹窗继续引用）。整合为两个全宽 `Panel`：上块「空间信息」（内含 `@container` + `FormRow` 并排「空间名称」与只读「空间标识」、全宽「说明」、表单内「保存空间信息」与「重置」，以及底部分割区「空间公开」开关与确认弹窗）；下块「空间成员」。属于控制台页面排版，不新增本体概念。 | 2026-11-17 用户确认 |
| WS-04 | **极简成员管理（用户名单列 + 内联渐进添加 + 防护）** | 成员列表精简为 `用户名`、`角色`、`操作` 三列（直接展示唯一 `username`）；点击工具栏「+ 添加成员」在表格上方内联展开极简添加栏（`AutoComplete` 按用户名搜索 + 干净的 `可查看 / 可编辑 / 管理员` 角色下拉，不包含额外描述文字与多余小字提示）；保留行内角色切换（`PATCH /members/{id}`）与 `LAST_ADMIN` 保护；移除接入 `Popconfirm` 二次确认，可见性说明放进 `Panel footer`。 | 2026-11-17 用户确认 |

（按 AGENTS.md 核对：上述 4 项均为接口作用域清理与前端排版交互优化，不新增任何本体模型字段、数据库表或迁移；删去其中任意一项都会退回全局配置混入空间、左偏留白、双列冗余或无确认误删的现状。）

## 3. DataAgent 连通性平台级接口（WS-01）

- **路由**：新增 `GET /api/v1/system/dataagent-health`（`tags=["system"]`），替代并删除 `api/workspaces.py` 的 `GET /api/v1/workspaces/{workspace_id}/settings/dataagent-health`。
- **鉴权**：要求 `Depends(current_principal)`（`dev` 模式自动生效、`login` 模式需登录会话，未登录返回 401，避免匿名请求探测内部服务地址、`website_id` 与 `agent_id`）。
- **服务签名**：`services/dataagent_health.py` 的 `dataagent_health(settings: Settings)` 移除 `workspace_id` 参数，固定使用 `session_ref="ontofoundry:system:diagnostics"`；响应体维持 `{"ok": bool, "checks": [{"name", "ok", "message", "hint"}]}`。

## 4. 空间设置页面设计（WS-03、WS-04）

全部控件沿用 Ant Design 5、`components/layout/` 与 `styles/tokens.css`（三档字号 `12/14/16px`，不新增手写控件和任意值类）；布局规范同步修订至[界面视觉一致性设计](2026-10-17-ui-visual-consistency.md)第 4 节。

### 4.1 权限与整体骨架

- 保留既有门禁：`!canManage` 时渲染 `<NoAccessResult subtitle="只有该工作空间的管理员可以打开「空间设置」。" />`，不发成员请求。
- 页面标题：`PageHeader title="空间设置"`；正文 `PageBody` 垂直排列两个全宽 `Panel`，不限制 `max-w-settings`。

### 4.2 上块：空间信息与空间公开

- **`PanelToolbar`**：左侧 `SectionTitle title="空间信息"`。
- **表单区**：外层包 `@container`（确保 `<FormRow>` 的 `@container (min-width: 40rem)` 在全宽 `Panel` 内正常分栏），使用受控 `Form.useForm()`（`workspace` 更新且 `!infoDirty` 时同步表单字段）：
  1. **第一行 `<FormRow>`**：左列 `空间名称`（必填、去空白校验、最大 120 字）；右列只读 `空间标识`（等宽文本显示 `workspace.slug` + `复制` 按钮，不套禁用输入框或描边卡片）。
  2. **第二行全宽**：`说明`（`Input.TextArea`，`autoSize={{ minRows: 2, maxRows: 5 }}`，最大 1,200 字）。
  3. **底部操作行（留在表单内，符合[控制台页面布局调整](2026-10-21-console-page-layout.md)）**：`保存空间信息`（主按钮，仅 `infoDirty` 为真时启用，`loading={savingInfo}`）、`重置`（次按钮，仅 `infoDirty` 为真时显示）与 `StatusMark`（保存成功后显示，再次修改任意字段立即清除）。
- **底部分割区（空间公开）**：与表单区以 `border-t border-rule px-4 py-3` 分隔，左侧展示「空间公开」标题与简要状态说明，右侧放置 `<Switch aria-label="对平台全部登录用户公开">`（开启时仍弹 `Modal` 二次确认，关闭直接生效，`loading={publicBusy}`）。

### 4.3 下块：空间成员

- **`PanelToolbar`**：左侧 `SectionTitle title="空间成员" note={loadingMembers ? undefined : `${members.length} 人`}`（遵循 UI-003，加载中不显示 `0 人`）；右侧 `extra` 放置 **`+ 添加成员`** 主按钮（添加栏展开时禁用）。
- **表格上方内联渐进添加栏**（点击 `+ 添加成员` 后展开，`border-b border-rule bg-surface-raised px-4 py-3`；独立状态，不污染 `usePageTab` 的 `dirty`）：
  - `AutoComplete` 搜索已有用户（调既有 `api.searchWorkspaceUsers`）：下拉项只简洁显示 `u.username`（尚未登录的用户在右侧附 12px 弱化文本 `尚未登录`，已是成员标 `已是成员`，不堆砌多余说明；搜不到时保留提示 `"用户不存在，请联系平台管理员在用户管理中创建"`）；
  - `Select` 选择角色（使用既有 `ROLE_OPTIONS`：`可查看` / `可编辑` / `管理员`，不含描述文字）；
  - `添加`（主按钮）+ `取消`（次按钮，点击收起并清空输入与局部变量错误）。
- **成员表格（AntD `Table`，`size="middle"`，超过 20 行分页 `pageSize: 20`）**：
  - 加载态：`Skeleton`；加载失败：面板内展示带「重试」按钮的 `Alert`；空态：`Empty description="暂无空间成员"`。
  - 三列定义：
    1. **`用户名`**：展示 `m.username`，若为当前登录用户（`m.user_id === user.id`）附 12px 弱化字 `（当前用户）`，若 `!m.last_login_at` 附 12px 弱化字 `（尚未登录）`（不用彩色 `Tag`）。
    2. **`角色`**：保留行内 `Select`（`ROLE_OPTIONS`：`可查看 / 可编辑 / 管理员`，`aria-label={`${m.username} 角色`}`，`disabled={memberBusy || deletingId !== null}`，受后端 `LAST_ADMIN` 保护）。
    3. **`操作`**（列头写 `"操作"`，固定窄宽右对齐）：使用 `Popconfirm`（`title={`移除成员 ${m.username}？`}`、`okText="移除"`、`cancelText="取消"`、`okButtonProps={{ danger: true }}`）包裹 `移除` 按钮，带行级 `loading={deletingId === m.id}` 与 `aria-label={`移除 ${m.username}`}`。
- **`Panel` `footer`**：将空间公开/私有的成员访问范围说明放入 `Panel` `footer`（12px 弱化字），让表格紧贴工具栏。
- **操作错误与反馈**：保存、公开切换、添加、改角色、移除各自独立忙碌态；操作错误统一走 `useErrorMessage()`（遵循 UI-023，添加栏内校验/查询失败可就近展示紧凑错误），操作成功使用 `App.useApp().message`。

## 5. 不包含

- 修改 `用户管理`（`/admin/users`）与 `个人中心`（`/me`）页面布局。
- 新增独立平台设置页（仍按 [平台登录](2026-11-12-platform-login.md) 仅通过运维配置文件和接口排查）。
