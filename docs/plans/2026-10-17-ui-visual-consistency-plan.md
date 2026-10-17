# 界面视觉一致性推广计划

设计：`docs/design/2026-10-17-ui-visual-consistency.md`

## 现状

截至 2026-10-17，`src/pages` 与 `src/components` 中共 38 个文件含有违反设计第 5.1 节的写法（Tailwind 任意值、`!` 强制覆盖、`style=`），合计约 380 处。数据映射页已在试验中改造完成。

## 分支与交付

- 新分支 `feat/ui-visual-consistency`，基于 core-1 P2（PR #23）的最终提交；PR #23 合并后改基于 main。
- 每批完成后统一运行 `vitest`、`tsc -b`、`lint`、`build` 和截图比对，并用局域网 IP 做一次浏览器检查。
- 每批给出改造页面的改前改后截图，用户确认后进入下一批。

## U0 基础

1. 合入试验 A 的 `tokens.css`、`antdTheme.ts`、`components/layout/`（`PageHeader`、`PageBody`、`Panel`、`PanelToolbar`、`StatusMark`、`SectionTitle`）和数据映射页改造。
2. 修复试验中遗留的 Ant Design 弃用用法（`Progress` 的 `strokeWidth` 改为 `size`）。
3. 增加设计第 5.1 节的 lint 规则：已改造文件为 error，其余为 warn。
4. 增加 Playwright 截图测试：固定 1440×900、固定虚构示例数据，先覆盖数据映射页两个页签。
5. 更新 `AGENTS.md` 前端约定（设计第 5.3 节）。

### U0 完成记录（2026-10-17）

- 合入试验 A 的设计变量、主题、`components/layout/` 和数据映射页；`Progress` 改用 `size`，数据映射页无 Ant Design 弃用警告。
- `eslint.config.js` 按设计第 5.1 节增加规则：已改造文件（数据映射页、`DatasetPicker`、`MappingWidgets`、`PageHeader`、`components/layout/`）为 error，其余为 warn；图谱画布和 `Markdown` 按例外表放开对应规则。当前 0 error、251 warn，分布在 37 个文件，即后续批次的工作量。
- 新增 `@playwright/test` 1.63.0 截图测试（`npm run test:visual`，更新基准用 `test:visual:update`）：Vite 固定端口 5199，1440×900，接口全部由测试拦截，数据由 `docs/design/core-1-examples/` 的继承与部分映射示例构造，覆盖已映射、部分映射、未绑定、虚拟父对象和快照数据集；数据映射页两个页签各一张基准图。拦截只匹配以 `/api/` 开头的路径，避免拦到 Vite 的 `/src/api/` 模块。
- `AGENTS.md` 前端约定补充布局组件、截图对比和 `test:visual` 要求。
- 检查：vitest 33 个文件 152 项通过，`tsc -b`、`lint`（0 error）、`check:core-types`、`build` 通过，`test:visual` 连续两次通过。

## U1 应用框架

`AppShell`、`WorkspaceTabs`、`Brand`、`AsyncState`、`TagList`：顶栏、侧栏、页面页签条与加载/空状态。框架影响所有页面，单独一批。

## U2 列表与设置类页面

`TypeCatalogPage`（本体对象目录）、`ConnectionsPage` 与 `DataConnections`、`SettingsPage`、`WorkspaceDirectoryPage`、`DeliveryPage`。都是“页头 + 面板 + 表格/表单”结构，直接套用数据映射页的模式。

## U3 发布与提案

`PublishPanel`、`ConflictResolver`、`ReleaseReview`、`ProposalPanel`、`ProposalCard`、`ProposalDetail`、`EvidencePopover`、`ModelResults`。

## U4 元素弹窗

`ElementInspector` 及 `ElementPanels`、`PropertyMappingTable`、`RelationMappingTable`、`LinkMappingPanel`、`ObjectTablePicker`、`DatasetPanel`、`MetricPanel`、`MetricForm`、`MetricPreview`、`DerivedConditionEditor`、`ElementInstances`。需要先在设计第 4 节补充详情弹窗的键值区和小节布局。

## U5 本体构建与画布类页面

`BuilderPage`、`BuilderConversationEmpty`、`SessionPicker`、`TableMaterialPicker`、`OntologyViewPage`、`OntologyOverview`、`OntologyGraph`、`ObjectRelationGraph`、`SemanticView`、`InstancesPage`、`Markdown`。画布部分按设计第 7 节例外处理。

## U6 收尾

lint 规则全部改为 error；截图测试覆盖每个主要页面；删除不再使用的样式变量和类。

## 验收

- lint 无 warn、无例外表以外的豁免；
- 截图测试全部通过，基准图经用户确认；
- 每个页面对照设计第 3 节检查通过：两层容器、两条对齐线、三档字号、状态只用 `StatusMark`、表格密度一致；
- 功能测试全部通过，局域网 IP 浏览器检查无回归。
