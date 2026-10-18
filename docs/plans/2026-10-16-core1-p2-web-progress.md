# core-1 P2 前端实施记录

## 基线与范围

- 日期：2026-10-16
- 分支：`feat/core1-p2-web`，基线提交：`5afb43d`（`docs: fix the core-1 P2 REST contract between backend and frontend`）
- 依据：`docs/design/2026-10-14-core-model-and-format-adapters.md`、`docs/plans/2026-10-14-core-model-and-format-adapters-plan.md`（P2-15～P2-21）及 `docs/plans/2026-10-16-core1-p2-api-contract.md`
- 变更规模（相对 `HEAD`，不含新增未跟踪文件）：`128 files changed, 9107 insertions(+), 29232 deletions(-)`；另新增 16 个前端源码与测试文件。

## 完成项（P2-15～P2-21）

- **P2-15 TS/HTTP 切换**
  - 更新 `apps/web/src/api/types.ts`、`apps/web/src/api/client.ts` 与 `apps/web/src/api/core.generated.ts`（配合 `scripts/generate_core_types.mjs`）：草稿模型唯一切换到 `schema_version: "core-1"` 九集合（`object_types`、`properties`、`link_types`、`rules`、`metrics`、`datasets`、`mappings`、`material_objects`、`material_links`）。
  - 移除 `hydrateNativeResponse`、`_legacy_form`、`legacy_mappings`、`legacy_joins` 等旧模型兼容逻辑；新增指标预览（`metricsApi.preview`）、事实提案修订（`proposalsApi.reviseFact`）、数据集与资产目录（`catalogApi`）、重复事实候选（`DuplicateCandidate`）及四工具只读契约类型。
  - 新增 `apps/web/src/lib/coreModel.ts` 提供 core-1 草稿构造、继承/有效定义推导与元素索引查询。

- **P2-16 编辑器与映射数据层**
  - 重写 `apps/web/src/lib/elementModel.ts`、`objectMapping.ts`、`objectMappingEditing.ts`、`relationEditing.ts`、`elementInspector.ts`、`instanceGraph.ts`、`instanceHints.ts`，新增 `datasetEditing.ts`、`derivedEditing.ts`、`metricEditing.ts`、`instanceDisplay.ts`。
  - 全部编辑与展示直接读写 core-1 元素定义与 Dataset 来源绑定，移除旧语义树与 native entry 回写；支持单父继承属性/关系/规则只读溯源、虚拟父具体子类绑定、有序复合键及文档事实 `display_text` 推导。

- **P2-17 详情弹窗与映射表改造**
  - 改造 `ElementInspector.tsx`、`InspectorDialog.tsx`、`ElementPanels.tsx`、`PropertyMappingTable.tsx`、`RelationMappingTable.tsx`、`LinkMappingPanel.tsx`、`ObjectTablePicker.tsx`、`MappingWidgets.tsx`、`ObjectRelationGraph.tsx`、`ElementInstances.tsx`。
  - 对象面板支持同义词、标题属性、单父继承与派生条件；关系面板支持 `inverse_name`、三基数及 `direct` / `mapping_table` 绑定；属性面板支持复合标识与唯一性独立勾选、列绑定与表达式计算绑定切换。
  - 原生 `<dialog>`、`<select>`、手写表格和页签全面替换为 Ant Design 5（`Modal`、`Drawer`、`Form`、`Input`、`Select(showSearch)`、`TreeSelect`、`Checkbox`、`Tabs`、`Table`、`Tag`、`Alert`），布局迁移至 Tailwind CSS v4。

- **P2-18 子对象派生条件编辑器**
  - 新增 `apps/web/src/components/elements/DerivedConditionEditor.tsx` 与 `apps/web/src/lib/derivedEditing.ts`。
  - 使用 Ant Design `Segmented`、`Form`、`TreeSelect`、`Select`、`Input`、`InputNumber`、`DatePicker`、`Switch` 实现按条件（`simple` 分支）与写表达式（`expression` 分支）平级切换，支持属性条件与有方向的关联“有 / 没有”（`exists`）筛选，父对象继承条件只读显示。

- **P2-19 指标/数据集弹窗与实时预览**
  - 新增 `DatasetPanel.tsx`、`MetricPanel.tsx`、`MetricForm.tsx`、`MetricPreview.tsx` 及 `lib/metricEditing.ts`、`lib/datasetEditing.ts`。
  - 覆盖 `simple` / `ratio` / `expression` 三种指标、`Dataset` 登记与列清单查看；未保存指标表单直接调用预览接口，校验 `definition_hash` 与请求序号防止过期响应覆盖，表单改动后标记结果“已过期，需重新预览”，并排展示总值、按月趋势、快照日期与 SQL 参考。

- **P2-20 四类资源浏览、数据映射与空间导航**
  - 改造 `SemanticView.tsx`、`lib/semanticExplorer.ts`、`OntologyGraph.tsx`、`OntologyViewPage.tsx`、`OntologyOverview.tsx`、`MappingsPage.tsx`、`DatasetPicker.tsx`、`DataConnections.tsx`、`WorkspaceTabs.tsx`、`AppShell.tsx`、`WorkspaceDirectoryPage.tsx`、`TypeCatalogPage.tsx`、`ConnectionsPage.tsx`、`SettingsPage.tsx`。
  - 语义视图统一为对象、关系、指标、数据集四类筛选（`Segmented` + `Input.Search` + `Tree` + `Table`），指标不作为本体图节点，规则归属所属对象/属性弹窗；数据映射页收敛为“数据集”和“本体映射”双标签；页签栏与离开拦截确认迁为 Tailwind + Ant Design `Modal` / `Alert`。

- **P2-21 建模会话、九类提案、发布与文档事实**
  - 改造 `BuilderPage.tsx`、`SessionPicker.tsx`、`TableMaterialPicker.tsx`、`ModelResults.tsx`、`ProposalPanel.tsx`、`ProposalCard.tsx`、`ProposalDetail.tsx`、`FieldDiff.tsx`、`EvidencePopover.tsx`、`elementMeta.ts`、`reviewMeta.ts`、`PublishPanel.tsx`、`ConflictResolver.tsx`、`ReleaseReview.tsx`、`DeliveryPage.tsx`、`InstancesPage.tsx`、`useModeling.ts`、`useProposals.ts`、`useSnapshot.ts`。
  - 支持九类核心元素提案审阅、依赖联动与撤销，支持重复文档事实候选提示及显式修订为更新已有事实（`reviseFact`）；移除旧 `actions`、`ontology_requires` 以及临时下线的 Ossie 导入/下载入口。
  - `eslint.config.js` 清空全部原生 `<select>` / `<dialog>` 历史文件豁免，全局强制禁止新增原生下拉与弹窗。

## 删除的文件与 CSS

### 删除的样式文件（12 个）

- `apps/web/src/styles/base.css`
- `apps/web/src/styles/element-inspector.css`
- `apps/web/src/styles/global.css`
- `apps/web/src/styles/object-mapping.css`
- `apps/web/src/styles/ontology-overview.css`
- `apps/web/src/styles/ontology-reading.css`
- `apps/web/src/styles/page-tabs.css`
- `apps/web/src/styles/proposals.css`
- `apps/web/src/styles/publish.css`
- `apps/web/src/styles/reference.css`
- `apps/web/src/styles/semantic-view.css`
- `apps/web/src/styles/semantic.css`

> 现仅保留 `apps/web/src/styles/tokens.css`（唯一设计变量来源）与 `apps/web/src/styles/index.css`（CSS `@layer` 声明与基础入口）。

### 删除的组件、库与测试文件（27 个）

- 旧契约转换与视图层：`apps/web/src/api/client.native.test.ts`、`apps/web/src/lib/nativeDraft.ts`、`apps/web/src/lib/nativeDraft.test.ts`、`apps/web/src/lib/nativeDraft.fixture.json`、`apps/web/src/lib/draftView.ts`、`apps/web/src/lib/draftView.test.ts`、`apps/web/src/lib/objectMapping.fixture.ts`
- 旧语义模型与读法组件：`apps/web/src/components/SemanticModels.tsx`、`apps/web/src/components/SemanticModels.test.tsx`、`apps/web/src/components/semantic/MappingTreeEditor.tsx`、`apps/web/src/components/semantic/SemanticObjectForm.tsx`、`apps/web/src/lib/semanticEditing.ts`、`apps/web/src/components/RelationshipRoles.tsx`、`apps/web/src/components/VerbalizationEditor.tsx`、`apps/web/src/components/VerbalizationEditor.test.tsx`、`apps/web/src/lib/verbalization.ts`
- 暂下线待 P4 重做的导入组件：`apps/web/src/components/OssieImportDialog.tsx`、`apps/web/src/components/OssieImportDialog.test.tsx`
- 已合并或退役的旧控件与页面：`apps/web/src/components/ConceptTag.tsx`、`apps/web/src/components/DataAssets.tsx`、`apps/web/src/components/ExpressionsEditor.tsx`、`apps/web/src/components/TagEditor.tsx`、`apps/web/src/components/elements/ElementActions.tsx`、`apps/web/src/components/elements/IdentifierBar.tsx`、`apps/web/src/components/elements/RelationCards.tsx`、`apps/web/src/components/proposals/EvidenceQuote.tsx`、`apps/web/src/components/proposals/ReviewIcon.tsx`、`apps/web/src/components/proposals/ReviewOverlays.tsx`、`apps/web/src/pages/ObjectDetailPage.tsx`

## 新增文件（16 个）

- 组件：
  - `apps/web/src/components/elements/DatasetPanel.tsx`
  - `apps/web/src/components/elements/DerivedConditionEditor.tsx`
  - `apps/web/src/components/elements/MetricForm.tsx`
  - `apps/web/src/components/elements/MetricPanel.tsx`
  - `apps/web/src/components/elements/MetricPreview.tsx`
- 领域与编辑逻辑：
  - `apps/web/src/lib/coreModel.ts`
  - `apps/web/src/lib/datasetEditing.ts`
  - `apps/web/src/lib/derivedEditing.ts`
  - `apps/web/src/lib/instanceDisplay.ts`
  - `apps/web/src/lib/metricEditing.ts`
- 测试与测试辅助：
  - `apps/web/src/components/elements/MetricPreview.test.tsx`
  - `apps/web/src/lib/derivedEditing.test.ts`
  - `apps/web/src/lib/metricEditing.test.ts`
  - `apps/web/src/lib/objectMapping.test.ts`
  - `apps/web/src/test/apiRecords.ts`
  - `apps/web/src/test/drafts.ts`

## 契约问题与源码缺陷记录

- **前后端契约问题**：无。
- 前端产品源码缺陷：测试中发现 `Alert` 的 `closable` 传对象时须含 `closeIcon: true` 才渲染关闭按钮，已在 `WorkspaceTabs.tsx`、`BuilderPage.tsx`、`SettingsPage.tsx` 修正（`Modal` 走通用 closable 逻辑，不受影响）。

## 评审修正

只读评审（对照契约与设计）后，经协调者逐条核对，以下 10 项成立并已修正，均有测试覆盖；其余评审项经核对不成立（引用不存在的代码，或与契约 §9“决定请求只发选中项、不自行指定原子组”、§6“search_objects 仅文档事实”相反），不做修改。

1. 实例浏览：无会话时数据库实例改用已发布读接口 `GET O/objects`、`GET O/objects/{ref}/neighborhood`（游标分页、服务端 ref/display_text/实际 type_id/snapshot_dates），虚拟父对象可列出各具体子对象实例并集，非成员读者也可浏览；有会话时仍用 mapping-preview / instance-neighborhood。（`ElementInstances.tsx`、`InstancesPage.tsx`）
2. 绑定方式：无映射且祖先无映射的对象，只有存在已绑定后代时才算虚拟父，否则为未绑定；虚拟父编辑态不再允许绑定主表。（`coreModel.ts`、`ObjectTablePicker.tsx`）
3. 修改父对象时清空本层成员条件；本对象为共用父对象数据而新父链无绑定时移除本对象映射。（`ElementPanels.tsx`）
4. 条件值校验：`not_in` 不含空值、数值类型不收非数字值、布尔 in/not_in 存布尔；指标“介于”改为起、止两个输入，相等上下界可输入。（`derivedEditing.ts`、`metricEditing.ts`、`DerivedConditionEditor.tsx`、`MetricForm.tsx`）
5. 共用父对象数据的子对象查看继承关系时，只读原因改为“使用父对象的绑定”。（`relationEditing.ts`）
6. 关系端点含虚拟父对象时，数据绑定页提示改在各具体子对象的「关系」页配置。（`LinkMappingPanel.tsx`）
7. 提案卡片与详情显示组内联动数量；决定请求仍只发选中项及其依赖。（`ProposalCard.tsx`、`ProposalDetail.tsx`）
8. 冲突“自定义”初值不再使用展示占位“（无）”：字符串字段空值为空串，其他字段为 JSON。（`ConflictResolver.tsx`）
9. 表达式指标“结果类型”文案改为“可选；未指定时留空待补全”，不暗示 SQL 类型推断。（`MetricForm.tsx`）
10. 本体草稿面板补“文档关系”分类，映射行显示中文实例来源；提案与发布差异中的文档事实、来源/目标实例显示名称而非 UUID。（`ModelResults.tsx`、`reviewMeta.ts`、`PublishPanel.tsx`）

## 测试与构建结果

在 `apps/web` 下使用 Node `v22.19.0` 统一执行 `npx vitest --run && npx tsc -b && npm run lint && npm run build`（评审修正之后）：

- **Vitest**：33 个测试文件全部通过，145 passed / 0 failed / 0 skipped。
- **tsc -b**：通过（0 errors）。
- **lint**：通过（0 errors，0 warnings）。
- **build**：通过；样式产物约 58 kB（gzip 约 11.6 kB）。

## 集成与浏览器验收

前后端合并到 `feat/core1-p2` 后，在可丢弃的 SQLite 库（开发环境认证、未连 DataAgent、未连业务数据库）上启动合并后的 API，前端开发服务器经局域网 IP 以 HTTP（非安全上下文）访问。数据用 `docs/design/core-1-examples` 的虚构示例 01、06、07 经会话保存→预览→发布写入（示例中引用外部材料的证据改为人工确认，因材料不属于该空间而被服务端正确拒绝）。

验收通过的路径：

- 工作空间目录、全局分层总览（层级统计、对象节点打开弹窗）、语义视图四类资源与本体图（继承虚线、自关系、虚拟父）。
- 对象弹窗：共用父对象数据的子对象（继承属性与绑定只读、成员扩展表）、编辑属性描述后保存，服务端返回 200 并生成新版本，页面版本号随之更新。
- 成员条件编辑：读回已有简单条件；新增“有 签约方（合同）”关联条件后保存，服务端接受生成的 `party.level = 'VIP' AND EXISTS (party.REVERSE(signer))`，重新打开仍按条件行显示。
- 指标弹窗与数值预览：未配置数据连接时给出“无法预览：数据集尚无可用来源连接”。
- 数据映射页的数据集与本体映射两个标签；文档事实实例列表的 display_text（标识值，仅人工证据时回退 UUID）。

验收中发现并已修正的界面问题：

1. 资源管理器四类筛选文字被截断：压缩分段控件内边距。
2. 侧栏底部“收起导航”按钮被裁切：改为分隔线下的独立按钮。
3. 对象概览描述列表末行跨列不齐（antd 控制台告警）：末行改为占满剩余列。
4. 共用父对象数据的子对象，属性绑定的来源下拉显示“附表 extension”：改为“成员扩展表 / 扩展表”。
5. 数据映射页“已映射”标签被拉满整列，且虚拟父对象被计入“未映射”：标签按内容宽度显示，虚拟父不计入映射状态筛选。
6. 弹窗内容滚动时页签随之滚走：页签吸顶。

说明：局域网访问开发服务器时，后端的来源检查需把该地址加入 `ONTOFOUNDRY_CORS_ORIGINS`；正式部署由 API 同源提供前端，不受影响。

## 未完成项与后续计划

1. **真实数据与智能体链路验收**：本次浏览器验收未连接业务数据库与 DataAgent；数据库实例浏览、指标真实取数、建模提案生成与审阅需在部署环境连接数据源和 DataAgent 后验收。
2. **导入与导出功能**：Ossie 与原生单文件导入三步对话框按计划在 P4（`P4-05`）恢复，导出在 P5 恢复。
3. **跨聚合改名联动（`affected_items`）**（已完成）：已接入 `POST W/element-saves/preview` 只读预检接口，元素保存前先用候选 `ElementSave` 调预检，有受影响元素时弹窗展示种类、名称与服务端 `reason` 供用户确认，确认后将去掉 `reason` 的 `affected_items` 原样带入保存请求（详见下方“保存影响预检”一节）。
4. **成员条件多跳路径与多分支**：编辑器的“按条件”模式只覆盖一层直接父对象条件；含多跳路径或多个分支的已有条件以表达式显示和编辑，语义不变但不再保持结构化分支。

## 控件补齐

在 PR #23 收尾阶段，将剩余手写控件与容器统一替换为 Ant Design 5 控件（保持 13px 主题基准与紧凑布局，不新增 CSS 文件）：

1. **工作区页签栏（`components/WorkspaceTabs.tsx`、`components/WorkspaceTabs.test.tsx`）**：由手写 `<button>` 与自定义方向键切换改为 Ant Design `Tabs`（`type="editable-card"`、`hideAdd`、`size="small"`），隐藏 `Tabs` 自带内容区，继续由现有 `TabPanel` 挂载与保活各页面；保留点击导航、`requestClose` 关闭拦截（忙碌提示、未保存确认）、页签图标、标题截断、未保存圆点与 `aria-label="关闭 {标题}"`，维持 12px 字号与约 30px 紧凑高度。
2. **上传业务知识拖拽区（`pages/BuilderPage.tsx`、`pages/BuilderPage.test.tsx`）**：由原生 `<button>` + 隐藏 `<input type="file">` + 手写拖拽事件改为 Ant Design `Upload.Dragger`（`multiple`、`accept=".md,.markdown,.txt,.json,.yaml,.yml,.csv"`、`showUploadList={false}`、`beforeUpload` 走现有 `upload` 逻辑并返回 `false`），保留禁用态、上传中文案、支持格式与单文件大小说明，并新增上传交互单测。
3. **条件行级校验错误（`components/elements/DerivedConditionEditor.tsx`、`components/elements/MetricForm.tsx`）**：派生条件编辑器与指标过滤条件行的行下红色 `Text` 改为 `Form.Item` 的 `validateStatus` 与 `help` 承载，保留原有错误文案。
4. **禁用按钮原因提示（`components/publish/PublishPanel.tsx`、`components/proposals/ProposalPanel.tsx`）**：“发布 vN”与“全部接受”按钮去掉禁用态下浏览器不显示的原生 `title`，改为外包 `<span>` 的 Ant Design `Tooltip`。
5. **边框与底色容器卡片化（`components/elements/ElementPanels.tsx`、`components/elements/ElementInstances.tsx`、`components/publish/PublishPanel.tsx`、`components/elements/MetricPreview.tsx`、`components/proposals/EvidencePopover.tsx`）**：规则编辑块、实例详情块、发布面板顶部信息框、指标预览总值与按月趋势框、证据条目统一改为 `Card`（`size="small"`），紧凑内边距保持原有视觉密度。
6. **证据来源标识描述列表（`components/proposals/EvidencePopover.tsx`）**：“来源标识”手写 `<dl>` 改为 Ant Design `Descriptions`（`size="small"`、`column={1}`）。
7. **检查项与说明列表（`components/publish/PublishPanel.tsx`、`pages/DeliveryPage.tsx`）**：发布检查页的检查项列表（合并冲突 / 本体校验 / 合并基准，带状态图标）与错误/警告列表、交付页的 MCP 工具说明列表统一改为 Ant Design `List`（`size="small"`）。

### 控件补齐后测试与构建结果

在 `apps/web` 下使用 Node `v22.19.0` 执行 `npx vitest --run && npx tsc -b && npm run lint && npm run build`：

- **Vitest**：33 个测试文件全部通过，**148 passed / 0 failed / 0 skipped**。
- **tsc -b**：通过（0 errors）。
- **lint**：通过（0 errors，0 warnings）。
- **build**：通过（`vite build` 产物正常，CSS 约 58.21 kB / gzip 11.48 kB）。

## 保存影响预检

配合 PR #23 G1 与更新后的接口契约 §4.2 / §9，前端接入只读元素保存影响预检：

1. **契约类型与接口客户端（`api/types.ts`、`api/client.ts`）**：新增 `ElementSaveImpact = { current_version_id: UUID | null; session_revision: number | null; affected_items: (AffectedItem & { reason: string })[] }`；在 `modelingApi` 新增 `previewElementSave(workspaceId, payload: ElementSave)` 调用 `POST /api/v1/workspaces/{id}/element-saves/preview`。
2. **元素弹窗保存预检与确认流程（`components/elements/ElementInspector.tsx`）**：
   - 点击保存后，先用与保存一致的候选 `ElementSave` 调用 `modelingApi.previewElementSave`；若 `affected_items` 为空则直接调用 `saveElement`（不携带 `affected_items` 字段）。
   - 若 `affected_items` 非空，弹出 Ant Design `Modal`（含 `List`、`Tag`）列出每个受影响元素的种类中文名、元素名称（从草稿按 `target_id` 解析，未命中时回退显示 ID）与服务端 `reason`，说明“确认后这些元素会随本次保存一并改写”。确认后剥离 `reason`，原样将服务端返回的 `{ target_kind, target_id, expected_target_hash }` 数组作为 `affected_items` 传入 `saveElement`；取消则关闭确认框、不保存并保留编辑内容。
   - 预检与确认保存之间若草稿内容发生变化，自动失效当前预检结果并在保存时重新触发预检；浏览器端不自行计算 `expected_target_hash`。
   - 预检返回的 409 版本/revision 过期或 422 范围/校验错误按既有保存错误横幅展示，不进入确认框。
3. **指标预览分量去重确认（`lib/metricEditing.ts`）**：确认 `previewRequest` 中比率指标的 `components` 已按唯一 UUID 去重。
4. **单测补充（`components/elements/ElementInspector.test.tsx`）**：基于 `example("07-instances-and-evidence")` 将客户属性 `customer_no` 改名为 `customer_code` 的场景，补充 3 项用例（无受影响项直接保存且不弹框；有受影响项展示 `reason`、取消不保存、确认后带上去掉 `reason` 的 `affected_items` 保存；预检报 409 时展示错误且不保存）。

### 保存影响预检测试与构建结果

在 `apps/web` 下使用 Node `v22.19.0` 执行 `npx vitest --run && npx tsc -b && npm run lint && npm run build`：

- **Vitest**：33 个测试文件全部通过，**151 passed / 0 failed / 0 skipped**。
- **tsc -b**：通过（0 errors）。
- **lint**：通过（0 errors，0 warnings）。
- **build**：通过（`vite build` 产物正常，CSS 约 58.26 kB / gzip 11.48 kB）。

## PR #23 第二轮评审修正

围绕 PR #23 第二轮评审中的前端问题（N5、A3，以及 N7 的前端类型部分）完成修正与回归测试：

1. **N5（`ElementInspector` 忙碌态禁用与预检返回时候选一致性校验）**：
   - 在 `components/elements/ElementInspector.tsx` 中用 Ant Design `ConfigProvider componentDisabled={busy}` 包裹编辑内容区（并保留 `<fieldset disabled={busy}>` 与页签/头部按钮禁用），同时将子组件（`PropertyMappingTable.tsx`、`ObjectTablePicker.tsx`、`LinkMappingPanel.tsx`、`RelationMappingTable.tsx`、`MetricForm.tsx`、`DerivedConditionEditor.tsx`、`MetricPreview.tsx`、`ElementInstances.tsx`）中动态布尔 `disabled` 写法统一改为 `|| undefined`，避免显式 `disabled={false}` 覆盖 `DisabledContext`，确保预检或保存进行中所有 `Select`、`Checkbox`、`Input` 等控件真正不可操作。
   - 通过 `draftRef` 同步追踪最新草稿，在 `previewElementSave` 响应后的所有分支（包括 `affected_items` 为空直接保存分支和有受影响项弹窗分支）均重新构建当前候选并与请求发起时的候选签名比较；若不一致则不保存旧候选、不展示过期影响列表，而是立即用最新候选重新发起预检。
   - 在 `components/elements/ElementInspector.test.tsx` 补充回归测试：验证预检进行中 `Select`、`Checkbox`、`Input` 均处于禁用态，且预检延迟期间若 `Select` 发生变更（即使首次预检返回 `affected_items: []`），不会保存旧候选，而是对新候选重新预检并最终保存最新修改。
2. **A3（`WorkspaceTabs` 页签无障碍关联与名称恢复）**：
   - 在 `components/WorkspaceTabs.tsx` 中将实际页面面板 `<section>` 的 `id` 统一为 `workspace-panel-${tab.id}`，与 Ant Design `Tabs`（`id="workspace"`）生成的 `aria-controls` 一致；清理隐藏 `.ant-tabs-content-holder .ant-tabs-tabpane` 上的重复 `id`/`role="tabpanel"`，并在 `useLayoutEffect` 中同步为 `role="tablist"` 恢复可访问名称“已打开的页面”；忙碌与未保存关闭保护保持不变。
   - 在 `components/WorkspaceTabs.test.tsx` 中恢复 `getByRole("tablist", { name: "已打开的页面" })` 与 `querySelectorAll('[role="tabpanel"]')` 断言，并新增 `aria-controls` 精确指向当前可见 `tabpanel` 元素的断言。
3. **N7（前端物理执行投影与 MCP 读类型补齐）**：
   - 在 `api/types.ts` 中严格按后端 `physical_projection.py` 的 Pydantic 定义新增 `BindingMode`、`MembershipRead`、`EffectiveLinkRead`、`EffectiveBindingRead`，并在 `ObjectTypeRead`、`LinkRead`、`MetricRead` 及新增的 MCP 读协议类型（`MCPElement`、`MCPGetOntology` 等）中声明 `effective_bindings`、`datasets`、`sources` 等字段。

### PR #23 第二轮评审修正检查结果

在 `apps/web` 下使用 Node `v22.19.0` 执行 `npx vitest --run && npx tsc -b && npm run lint && npm run check:core-types && npm run build`：

- **Vitest**：33 个测试文件全部通过，**152 passed / 0 failed / 0 skipped**。
- **tsc -b**：通过（0 errors）。
- **lint**：通过（0 errors，0 warnings）。
- **check:core-types**：通过（0 errors）。
- **build**：通过（`vite build` 产物正常）。

## PR #23 第三轮评审修正

**R5 工作区页签重复 ID（`components/WorkspaceTabs.tsx`、`components/WorkspaceTabs.test.tsx`）**：上一轮在渲染后删除 Ant Design 内部空面板的属性，但未访问过的页签首次激活时面板才挂载，会再次出现与实际页面相同的 ID。改为把实际页面作为 `Tabs` 各项的 `children` 交给 Ant Design 渲染：面板的 `id`、`role="tabpanel"`、`aria-labelledby` 与页签的 `aria-controls` 由组件生成并天然对应；面板在首次激活时挂载、隐藏时保持挂载（保活、输入和滚动位置不变），未访问的页签不挂载。去掉另外渲染的页面区和事后清理 DOM 的逻辑；关闭提示条放入 `renderTabBar` 与页签条一起渲染；页签条样式只作用于页签条容器，内容区只用子选择器，避免影响页面内部的 `Tabs`。新增用例：恢复两个页签后首次切换到未访问页签，`aria-controls` 指向的 ID 在文档中唯一且是可见页面。

## PR #23 第四轮评审修正

- F1：弹窗编辑期按属性 UUID 保存绑定；临时技术名重复时不生成冲突键，最终名称唯一后统一重建映射字典，重复时暂停绑定编辑。缓存随编辑生命周期清理，跨页签仍保留。补逐字输入 n → na → nam → name → name2 后预检与保存均保持两项绑定的 Vitest 回归。
- F4：指标与属性条件共用 Ant Design 类型化值编辑器；文本保留原文与前导零，布尔使用选择控件，数值使用 InputNumber，日期沿用 DatePicker 的日期字符串/时间 ISO 约定。切列保留已有值并重新校验，类型不符阻止保存。补文本 001、布尔 true/false、多值、数值范围、日期和切列回归。

在 `apps/web` 先执行 `. ~/.nvm/nvm.sh && nvm use 22.19.0`，再执行完整命令 `npx vitest --run && npx tsc -b && npm run lint && npm run check:core-types && npm run build`，最终退出码 0：

| 检查 | 最终结果 |
|---|---|
| Vitest | 34 个文件、162 passed、0 failed、0 errors、0 skipped |
| `tsc -b` | 通过 |
| lint | 通过，0 errors、0 warnings |
| `check:core-types` | 核心类型与 Schema 一致 |
| build | 通过 |
| 仓库根 `git diff --check` | 退出码 0 |

相较前轮增加 9 项回归。旧 region 文本列测试原先期望数字，已修正为原文字符串；最终全量通过。测试仍有既有 Ant Design Spin 提示，构建仍提示大包体积，不影响通过。按本任务限制不启动服务，不做局域网浏览器访问，不 commit/push。

## PR #23 第五轮评审修正

- N1：属性绑定重建按编辑后图的 `effectiveSources()` 判断来源，保留共享父绑定中的祖先来源；真正失效来源仍移除。补例 06 工具函数回归及真实 ElementInspector 回调回归，核对改名后的预检和保存载荷，覆盖 `note → note2` 以及继续修改列绑定。
- A2：删除 `ConditionValueInput.tsx` 多余末尾空行，使用仓库 diff 检查验证。

全部编辑完成后统一执行指定 Vitest、TypeScript、lint、生成类型检查、构建及仓库 diff 检查，结果见本节后续记录。遵守本次禁止启动应用服务、禁止访问局域网的限制，界面行为由组件回调回归验证，未运行浏览器或局域网验收。不 commit/push；保留已有未跟踪 node_modules。

验证在 `apps/web` 执行，先 `. ~/.nvm/nvm.sh && nvm use 22.19.0`：

| 命令 | 结果 |
|---|---|
| `npx vitest --run` | 35 个文件、166 passed、0 failed、0 errors、0 skipped；19.55 秒 |
| `npx tsc -b` | 退出码 0 |
| `npm run lint` | 退出码 0 |
| `npm run check:core-types` | 退出码 0，类型与 Schema 一致 |
| `npm run build` | 退出码 0；仅有大于 500 kB 的构建分包提示 |
| `git diff --check`、`git diff --check origin/main` | 退出码 0，当前工作树相对主分支也无末尾空行问题 |

本轮增加 4 项回归，未放宽既有断言。最终只补验证记录，未改实现。
