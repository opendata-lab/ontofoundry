# 提案审阅时修改提案内容

日期：2026-10-21。状态：已实施。来源：用户 2026-10-21“提案里的东西最好支持修改”。

## 1. 决定

| 编号 | 决定 |
|---|---|
| PE-01 | 待审阅的新增、修改提案都可以在接受前修改提案内容（after）；删除提案不修改，只能接受或拒绝。 |
| PE-02 | 修改后按与 Agent 结果相同的元素契约校验；证据由平台保留，修改不能增删或改动证据；元素 UUID 不变，依赖它的其他提案不受影响。接受时照常执行完整候选图校验。 |
| PE-03 | 界面保持现有字段差异表的样子，就地修改：鼠标悬停“提案值”单元格显示铅笔图标，点击后在原位置编辑，回车或 ✓ 保存，Esc 或 ✗ 取消。枚举字段用下拉，布尔用开关，数字用数字框，描述／表达式／SQL 用多行文本，其余结构化值用 JSON 文本；当前为空的字段输入以 `[` 或 `{` 开头时按 JSON 解析。保存失败时显示服务端返回的字段路径和原因，重新保存时清除旧错误。id、evidence、extends、type_id 和以 `_id` 结尾的引用字段不可修改。 |
| PE-04 | 来源问题就近显示：未绑定连接、表未同步等诊断显示在对应字段“提案值”的右边，并带「去同步」「修改连接和表」入口；诊断字段不在差异表中时，在差异表上方提示。同步完成后提案详情自动刷新，问题消失即不再显示。 |

## 2. 实现

- 后端：`PATCH /api/v1/workspaces/{workspace_id}/sessions/{session_id}/proposals/{proposal_id}/after`，请求 `{expected_session_revision, fields}`，只带本次修改的顶层字段，服务端合并到当前保存的内容，连续修改不同字段不会互相覆盖；id、evidence、extends、type_id 和 `_id` 结尾的字段返回 422 `FIELD_NOT_EDITABLE`。修订号除行锁外再做比较更新。内容中不再引用的同批提案，其存储的依赖随之移除。条件：提案属于会话、当前有效状态为待审阅、操作为新增或修改；会话修订号匹配（行锁）。after 的 id 固定为提案目标 id，evidence 固定为原提案证据，用 `ELEMENT_MODELS` 校验后保存；重算 fingerprint，清空存储的 field_changes（读取时按 before／after 推导）；会话修订号加一。
- 前端：`proposalsApi.reviseContent`、`useProposals.reviseContent`；`InlineValueEditor` 由 `FieldDiff` 在可修改的提案值单元格中使用；来源诊断由 `useSourceIssues` 生成标记并放到字段差异行的提案值右侧。同步弹窗完成时派发 `ontofoundry:metadata-synced`，`useProposals` 收到后重新加载。

## 3. 不做

- 不新增提案状态或“已人工修改”标记；修改前后的差异由字段差异展示。
- 编辑时不做候选图预校验；接受时的错误提示指向具体问题。
