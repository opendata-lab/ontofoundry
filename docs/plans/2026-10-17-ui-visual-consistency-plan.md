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

### U1 完成记录（2026-10-17）

- 改造 `AppShell`、`WorkspaceTabs`、`Brand`、`AsyncState`、`TagList`。新增 `ApplicationFrame` 和 `AsyncSurface`，先在设计第 4 节记录现有框架与异步反馈布局；其他页面代码未修改。
- 顶栏、侧栏、品牌装饰、页签标题截断宽度及图标尺寸集中到 `tokens.css`；侧栏改为 6px 圆角，品牌文字使用 16px 档位，页签使用 12px、28px 高度和统一语义色。品牌四块菱形构造保留。页签条通过引用 tokens 的 Tailwind 工具类控制，移除任意值、强制覆盖和内联样式，选择器局限于独立的条区域；页面仍作为 Tabs items.children 渲染，内容高度仅约束直接子元素。路由错误 Result 的字号通过 Ant Design 主题统一。
- 五个文件全部加入 lint error 清单。当前 **0 error、223 warn，分布在 33 个文件**；比 U0 记录减少 28 warn。
- 新增框架功能测试，覆盖导航当前项、收起/展开、访客可见范围、搜索快捷键与空结果、加载失败后重试。已有页签功能测试保持通过，覆盖唯一 aria-controls、首次激活、保活、滚动位置、未保存关闭保护、离开空间保护和后台忙碌提示。
- 视觉用例复用原有虚构数据与接口拦截，保留数据映射两个页签，新增本体发布页及“三个页面打开 + 一个后台未保存页签”。新用例还检查内部 Tabs 样式不随框架页签切换改变、每个已访问页签的 aria-controls 唯一对应、设置表单与滚动位置保留，以及关闭未保存页签可取消。
- 检查：`vitest --run` 34 个文件、157 项通过；`tsc -b`、`lint`、`check:core-types`、`build`、`git diff --check` 通过。构建仍提示已有大体积 chunk。按本次运行环境要求，仅使用 Playwright webServer 的本机回环端口与接口拦截，未连接数据库或进行局域网验证。
- 截图验收：更新基准后 `test:visual` 连续两次通过（4 个用例）。页签条用例改为按 `[role=tab][aria-selected]` 计数，因为 rc-tabs 的关闭按钮也带 `role="tab"`。基准图已人工查看：框架与数据映射页、本体发布页一致，页面内部 Tabs 不受页签条样式影响。

## U2 列表与设置类页面

`TypeCatalogPage`（本体对象目录）、`ConnectionsPage` 与 `DataConnections`、`SettingsPage`、`WorkspaceDirectoryPage`、`DeliveryPage`。都是“页头 + 面板 + 表格/表单”结构，直接套用数据映射页的模式。

### U2 完成记录（2026-10-17）

- 改造上述六个文件。本体对象与关系目录、数据连接、工作空间目录统一为面板内的 Ant Design Table；目录筛选与搜索移入 `PanelToolbar`。保留继承属性与关系统计、映射与文档实例计数、关系端点及基数、标签筛选、详情链接、新建、发布、连接测试与保存、空间创建、成员管理和权限边界。
- 设置页使用同宽的并列面板，标题、说明、表单与表格首列统一按 16px 对齐；发布页将内部页签收进面板顶部，服务接入以分割线分区。状态改用 `StatusMark`，表头为 12px、正文为 13px，表格统一使用主题定义的 10px × 16px 单元格内边距。六个文件均移除任意值、强制覆盖、内联样式及状态色 Tag。
- 在设计第 4 节补充目录框架、设置表单及发布页分区模式；新增 `DirectoryFrame`，目录与设置的最大宽度集中到 `tokens.css`。`Panel` 保持内容高度，滚动交由 `PageBody`；`PanelToolbar` 新增 `tabBar` 插槽，避免额外包装破坏 Ant Design 页签导航条的父级选择器。其他页面代码未修改。
- 六个文件全部加入 lint error 清单。当前 **0 error、184 warn，分布在 28 个文件**；比 U1 减少 39 warn，剩余项属于后续批次。
- 新增 7 个视觉用例、8 个截图断言：对象目录、关系目录、数据连接、空间设置（顶部及连通性检查区）、工作空间目录、版本历史、服务接入；更新已有发布页用例，检查当前版本与内部页签。复用 `fixtures.ts`，补齐固定的虚构空间、连接、成员、连通性检查及版本数据。拦截仅匹配以 `/api/` 开头的路径；框架页签计数继续使用 `[role=tab][aria-selected]`。
- 新增 7 项功能测试，覆盖目录搜索、继承统计与会话详情链接、关系端点、连接测试、数据库类型切换后的默认端口、连接保存、成员可见操作及工作空间创建；更新设置页状态断言。检查：`vitest --run` 37 个文件、164 项通过；`tsc -b`（含截图用例）、`lint`、`check:core-types`、`build`、`git diff --check` 通过。构建仍提示已有大体积 chunk。
- 按设计第 3 节静态核对容器层级、对齐线、字号档位、状态显示与表格密度。本轮按运行环境要求未启动服务、未连接数据库、未访问局域网，未运行 `test:visual` / `test:visual:update`，未生成截图。**截图基准更新、1440×900 截图对比及浏览器视觉验收待协调者在沙箱外运行。** 未 commit 或 push。

## U3 发布与提案

`PublishPanel`、`ConflictResolver`、`ReleaseReview`、`ProposalPanel`、`ProposalCard`、`ProposalDetail`、`EvidencePopover`、`ModelResults`。

### U3 完成记录（2026-10-18）

- 改造上述八个组件，沿用 `Panel` / `PanelToolbar` / `SectionTitle` 与 Ant Design 控件。发布上下文、检查结果、历史比较、提案详情与证据按分割线分区，移除嵌套卡片；状态统一使用 `StatusMark`，类型与操作保留中性标签。保留发布预览、校验与冲突阻断、三方对比和自定义合并、版本比较、筛选搜索、批量审核、依赖联动、重复事实修订及证据来源查看的功能和文案含义。
- 八个组件移除 Tailwind 任意值、强制覆盖、内联样式、颜色字面量及彩色状态 Tag，全部加入 lint error 清单。当前 **0 error、125 warn，分布在 21 个文件**；比 U2 减少 59 warn，剩余项属于后续批次。
- 设计第 4 节补充发布与提案的分区模式、窄面板工具栏按组换行及构建结果的剩余高度规则。`Panel` 新增显式 `fill` 选项，默认保留目录等页面的内容高度；构建结果页签的高度选择器只作用于直接子级。`StatusMark` 补充修改和待审状态，并透传原生事件及引用，保留 Tooltip 的悬停交互。详情、证据弹层、冲突列与 JSON 预览的尺寸集中到 `tokens.css`。
- 在 `publish-proposals.spec.ts` 新增 5 个视觉用例、6 个截图断言：发布检查、展开的版本历史比较、冲突处理、提案列表、提案详情与证据弹层（含来源标识和人工确认）。复用 `fixtures.ts` 的接口拦截和虚构工作空间，补齐固定会话、提案批次、证据、合并预览及冲突数据，固定预览时间。接口只拦截以 `/api/` 开头的路径；页签计数使用 `[role=tab][aria-selected]`。新增 1 项功能测试，覆盖证据按钮不会误开详情、来源标识展开及键盘打开详情后保留证据。
- 全部代码编辑完成后，使用 Node 22.19.0 统一运行指定检查：`vitest --run` 37 个文件、165 项通过；`tsc -b`（含视觉用例）、`lint`、`check:core-types`、`build` 及 `git diff --check` 通过。仍有既有日期控件空值提示与构建大体积 chunk 提示。
- 按设计第 3 节静态核对容器层级、对齐线、字号档位、状态显示和表格密度。本轮未启动服务、未连接数据库、未访问局域网，未启动 Chromium，未运行 `test:visual` / `test:visual:update`，未生成截图。**截图基准更新、1440×900 截图对比及浏览器视觉验收待协调者在沙箱外运行。** 未 commit 或 push。

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
