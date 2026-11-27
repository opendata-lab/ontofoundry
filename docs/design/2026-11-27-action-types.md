# 业务动作定义

日期：2026-11-27。状态：方案已定，待实施。

调研分两路独立进行：Gemini 4 Neon 和 Codex gpt-6.2-sol。设计又经两轮评审，先 Codex，后 Neon。记录都在 `~/.agents/handoffs/2026-11-27-*-action-*/`（不入库）。取舍由用户在 2026-11-27 决定。

## 1. 问题

决定 #37（[核心模型](2026-10-14-core-model-and-format-adapters.md)）在首版删除了 Action，理由是“只有定义没有执行器，本期先做建模问数”。现在本体已通过 MCP 网关提供给外部 Agent（[语义层](2026-11-11-runtime-agnostic-semantic-layer-for-agents.md) SL-14），出现了两类需求：
- Agent 要回答“对工单能做哪些操作、要满足什么前提、做完哪些状态会变”。这些写在制度和操作手册里，本体里没有位置。
- 将来让 Agent 发起业务操作，需要先有一份经审阅、按版本发布的动作清单作为依据。

本设计恢复 Action，但只作为定义：可以建模、审阅、发布、导出，供人和 Agent 读取。平台不执行动作，也不绑定外部接口。

## 2. 同类产品

| 产品 | 模型里声明 | 执行在哪 |
|---|---|---|
| Palantir Foundry Action Type | 参数（标量、对象引用）、提交条件、效果规则（增删改对象和关系）、副作用；Ontology MCP 把每个 Action Type 暴露成一个工具 | Foundry 的对象写入引擎、Function 代码、Webhook |
| SAP RAP Behavior Definition | 实例动作或静态、工厂动作，输入参数，结果；determination、validation 的触发时机 | ABAP behavior pool |
| Dataverse Custom API | 绑定类型（全局、单实体、实体集合）、请求参数、响应属性、执行权限 | 注册的插件 |
| Salesforce Agentforce Action | 名称、给模型看的说明、输入输出、是否需要用户确认 | Flow、Apex、外部服务、MCP 工具 |
| Fabric IQ Ontology | 没有动作，只有自然语言业务规则 | 动作在本体之外的 Activator、Power Automate |
| Apache Ossie | 规范里没有动作；上游提案 [#106](https://github.com/apache/ossie/issues/106)（open）提议 `behavior.actions[]` 加 `effects[]`（作用的实体、读写、选择器、状态迁移），明确不规定执行方式 | — |

共同点有两条：
- 模型层收敛为五项：归属对象（或全局）、参数、前提、效果、给人和 AI 看的说明。
- 执行几乎都在模型之外，由既有代码、API、Flow 或工具完成。只有 Palantir 自建了对象写入引擎。

## 3. 方案

### 3.1 模型

`CoreDraft` 增加顶层集合 `actions`，与 `rules`、`metrics` 平级：

```json
{
  "id": "10000000-0000-4000-8000-000000000021",
  "name": "dispatch_work_order",
  "display_name": "派单",
  "description": "只有待派单的工单可以派单，派单时必须指定受理班组。派单后工单由该班组受理，状态变为已派单。",
  "synonyms": ["分派工单"],
  "tags": [],
  "target_type_id": "<工单 work_order 的 id>",
  "parameters": [
    {"name": "team_code", "display_name": "受理班组编码", "description": "", "value_kind": "string", "value_type_id": null, "required": true}
  ],
  "effects": [
    {"kind": "set_property", "property_id": "<work_order.status 的 id>", "description": "待派单 → 已派单"},
    {"kind": "add_link", "link_type_id": "<工单—受理班组 关系的 id>", "description": "建立工单与受理班组的关系"}
  ],
  "evidence": []
}
```

一个不挂对象的动作：

```json
{"name": "create_inspection_order", "display_name": "新建巡检工单", "target_type_id": null,
 "parameters": [{"name": "site_code", "display_name": "站点编码", "value_kind": "string", "required": true}],
 "effects": [{"kind": "create_object", "object_type_id": "<work_order 的 id>", "description": "新建一张类型为巡检的工单"}]}
```

| 字段 | 来源 | 语义还是执行 | 删掉会失去什么 |
|---|---|---|---|
| `actions`、`id`、`name`、`display_name`、`description`、`synonyms`、`tags`、`evidence` | Palantir Action Type、旧版 Action；其余字段沿用 core-1 元素的通用字段 | 语义 | 动作没法独立提案、按版本比较和检索。写进 `ObjectType.description` 只能随对象一起改，也没法列出 |
| `target_type_id`（可空） | RAP 实例动作和静态动作、Dataverse 单实体和全局绑定 | 语义：动作作用于该类型的一个已有实例；为空表示不针对已有实例（新建、全局） | 没法校验动作适用于哪类对象，对象详情也没法列出它的动作 |
| `parameters[]`：`name`、`display_name`、`description`、`value_kind`、`value_type_id`、`required` | Palantir、RAP、Dataverse 的参数；值类型沿用 core-1 的七种标量和值概念 | 语义：执行时调用方另外提供的输入 | 不知道要填什么。`Property.required` 说的是实例必须有值，不是“这次操作要另外提供” |
| `effects[]`：`kind`、目标元素 id、`description` | Palantir 效果规则、Ossie #106 的 `effects` | 语义：做完后哪些属性、关系、对象会变 | 没法反查“哪些动作会改工单状态”，影响分析和状态归因只能读自然语言 |

`effects[].kind` 只有四种：
- `set_property`，带 `property_id`；
- `add_link`、`remove_link`，带 `link_type_id`；
- `create_object`，带 `object_type_id`。

效果不写表达式或取值，具体怎么变写在 `description` 里。旧版用 SQL 表达式描述取值，平台不执行却要维护语法，建模 Agent 也容易编造公式，所以不再采用。

前提只写在 `description` 里，不引用 `Rule`。对象规则是对象始终要满足的约束：若写一条“工单状态 = 待派单”的规则，已派单的工单就都不合法了。`Rule.owner_kind` 不增加 `action`。

### 3.2 校验

- **命名**：`name` 和参数 `name` 都是 ASCII 标识，规则与其他元素相同。动作名在工作空间内唯一，参数名在同一动作内唯一，都用 `casefold()` 判重。互换名称时整组接受合法，单独接受其中一条会撞名。`action` 要加进核心集合、`ElementKind`、图索引、身份登记、提案分组和导入自然键，与其他元素共用同一套机制。
- **引用存在**：`target_type_id`、效果里的 id、参数的 `value_type_id` 都必须指向存在的元素。参数的 `value_kind` 与值概念一致。
- **效果的形状**：`effects` 是按 `kind` 区分的判别联合，四个分支各带一个引用字段，写法与 `DataJoin`、`Metric` 相同；JSON Schema、提案诊断和生成的 TS 类型都按 `kind` 分支提示。
- **效果的作用范围**：只校验引用的元素存在且种类正确，不限定属于目标类型。种类正确指 `property_id` 必须指向属性，不能指向指标，其他引用字段同理；同批 `client_ref` 也按种类校验。实例动作常会顺带改关联对象，例如派单时把受理班组的待办数加 1；限定范围的话，建模者会被迫把实例动作改成全局动作，反而丢掉归属。影响哪些实例写在效果说明里。
- **边界**：
  - `parameters`、`effects` 可以为空，各自最多 50 条；
  - 同一动作内不能有完全相同的 `(kind, 引用 id)`，但“转派班组”这种对同一关系先 `remove_link` 再 `add_link` 是合法的；
  - 默认值：`description` 为空串，`required` 为 `false`；
  - 长度：参数和效果的 `description` 最多 200 字。这样 50 个参数加 50 条效果最多约 60 KB，一个动作的完整定义总在 MCP 120 KB 的响应上限以内，不用为动作再做分段读取。证据沿用现有分页。
- **继承**：动作挂在父类型上，对子类型同样适用；不另设字段，也不复制。读取时沿祖先链推导：巡检工单继承工单，巡检工单的详情里也列出“派单”，并标明定义在工单上。
- **引用路径**：`target_type_id`、`parameters[].value_type_id`、`effects[]` 的各个 id 登记到 `walk_references` 和 `reference_index`。这样，同批提案的 `client_ref` 能换成新 UUID，导入重映射能改指本地 UUID，删除检查也能找出引用这些元素的动作。
- **依赖与删除**：删除仍被动作引用的对象类型、属性、关系或值概念时，最终图有悬空引用，提案失败；同一组提案里可以同时改绑或删除该动作。
- **值概念联动**：修改值概念的基础类型时，引用它的动作参数的 `value_kind` 一起改，处理方式与属性相同（`element_save.element_scope("value_type")`、值概念目录的“使用处”）。在提案里也一样：类型变更和为保持一致而对动作参数做的更新、改绑或移除，归入同一个原子组。不这样做的话，分组会先校验值概念，此时动作参数还是旧类型，整批就被拒。
- **编辑方式**：首版动作只经提案增删改，不提供人工编辑表单，`ElementSavePreview.target_kind` 不加 `action`。审阅时 `parameters`、`effects` 和其他引用字段一样锁定，不能改。审阅界面上动作的差异，由服务端从规范化后的 `before`、`after` 计算，不用提交者填的 `field_changes`，并把其中的 id 渲染成元素名。否则提交者漏列一条新效果，审阅人就看不到它。
- **哈希兼容**：
  - 规范化器把 `actions` 登记为按 `id` 排序的集合，`parameters`、`effects` 登记为保持原顺序的数组。未登记的数组字段现在会直接报错。
  - `actions` 为空时不进入规范化结果。`core_canonical.canonical` 现在会序列化默认值，不省略的话旧快照哈希会变。省略写在 `core_canonical._normalize` 处理顶层草稿的地方，`domain/canonical.canonical` 也调用它，两个入口结果一致。
  - 测试覆盖三种情况：缺少 `actions` 和显式空集合的哈希相同；旧快照哈希不变；非空动作能计算提案、元素和快照哈希。
- **读取权限**：动作定义沿用本体读取权限，证据沿用 `can_read_instances`。`authorized_snapshot` 现在按固定集合清空证据，要把 `actions` 加进去。HTTP 版本展示、元素详情、MCP 详情和搜索摘要都要核对。

### 3.3 各层改动

| 层 | 改动 |
|---|---|
| 契约 | `contracts/` 的 core-1、提案、读取 JSON Schema 增加 action；同步更新 Pydantic 模型和前端类型 |
| 后端 | `domain/core.py` 增加模型；补齐引用校验、依赖、差异、合并、快照和提案的 `target_kind: action`（create、update、delete）。各模块里还有十多份各自硬编码的元素种类清单，见计划第 0 步 |
| 前端 | 语义视图检查器里，对象详情列出适用于它的动作，含沿祖先链继承来的（推导，不存储），点开显示参数和效果。动作，包括全局动作，在检查器里有自己的只读视图，搜索结果点进去打开这个视图。提案工作台增加“动作”分类。动作旁固定显示灰色标签“仅定义” |
| HTTP 读取 | 版本展示、`GET /types`、`GET /catalog`、版本摘要计数都纳入动作。元素局部投影 `GET /types/{id}/presentation` 对对象类型带上适用动作，并把效果和参数引用的元素一起放进引用闭包，否则名称解析不出来；它也要支持直接打开一个动作。对象详情的动作集合与 MCP 共用同一个推导函数，证据按上面的读取权限裁剪 |
| MCP 与检索 | `search_ontology`、`get_ontology` 的 `inputSchema` 和检索候选加入 `action`。检索做双向扩展：命中对象类型时带出适用动作，命中动作时带出目标类型；对应的 `SearchViaRead.relation` 加两个值。否则“对工单能做哪些操作”只命中工单，召回不了派单。`get_ontology` 的规则：不传 `ids` 时列表包含动作；对象类型在默认 `include` 下附带分页的动作摘要；单查动作返回完整定义，没有实例读取权限时去掉证据。`tools/list` 的工具名单不变，不新增写工具；外部插件的 `ontology-grounding` 技能和工具描述同步说明动作 |
| Ossie | 动作写入 ZIP 内 `ontofoundry-extension.json` 的 `actions`，按名称为键。每条自包含：显示名、说明、同义词、标签都内嵌，不拆到顶层的 `display_names` 等表；目标类型、效果和参数的值概念都用英文路径或名称（`work_order`、`work_order.status`、值概念名）。导出报告逐条记为 `converted` 加 warning，写明只取纯 `.ossie.json` 会丢失动作；不要记成 `dropped`，否则会进扩展文件的 `unsupported`。导出缓存键 `compiler` 要升级。Ossie ZIP 仍要满足现有前置条件，即至少有一个对象类型；只有全局动作、没有对象类型的模型，用原生完整包往返。ZIP 导入时按归属和元素种类解析路径，同一动作只要有一个引用解析失败，就不导入这个动作，原文留在报告里待补。纯 Ossie 文件本身没有动作信息，所以损失由导出方逐项报告，并登记到[核心设计](2026-10-14-core-model-and-format-adapters.md) §7 的例外表 |
| 原生完整包 | 动作的 UUID、引用、证据和材料原文无损往返，单独测试 |
| 建模技能 | `ontology-discovery` 从制度、操作手册、业务表单抽取动作，只在材料明确写出操作、对象和结果时提出。表里有 `status` 列或历史上出现过一次派单，不能据此推出动作。正例放在 `extract-kit/04.json`：它在第 2 页，余量约 5.5 KiB；第 1 页离 14 KiB 上限只剩不到 900 B，`guide.md` 最多加一句指引。辅助脚本里的清单也要补上：`runpaths.COLLECTIONS`、`show_element` 的引用字段、`show_example` 和 `proposal_diagnostics` 的示例分页、工作包元素摘要和 `draft_empty`。`generate_output_schemas.py` 的 `TARGETS` 白名单要加 `action`，否则技能自己的输出 Schema 仍会拒绝动作提案 |

不需要数据库迁移：草稿和快照存为 JSON。

### 3.4 不做

- 执行动作、绑定外部 API 或 MCP 工具、一动作一工具。以后要做，绑定放在工作空间配置里，不进核心模型；执行还依赖 SL-16 的授权、确认、幂等和审计。
- 对象引用参数（“接单工程师 → 工程师对象”）、结构化前提、`Rule.owner_kind = action`、结果 Schema、批量动作、自动触发。

## 4. 已确认决定

| # | 决定 | 来源 |
|---|---|---|
| 1 | 修订决定 #37：恢复 Action，作为可发布、可读取的定义；平台不执行 | 用户 2026-11-27 |
| 2 | 效果用结构化引用加说明，不写表达式 | 用户 2026-11-27 |
| 3 | 参数首版只用标量（可带值概念） | 用户 2026-11-27 |
| 4 | `target_type_id` 可为空，用于新建和全局动作；全局动作不要求有 `create_object` 效果 | 用户 2026-11-27；评审 |
| 5 | 前提只写在说明里，不引用对象规则 | 调研核对：对象规则是不变式 |
| 6 | 外部工具绑定是执行细节，以后放在工作空间配置里，不进核心模型 | AGENTS.md 产品原则 |
| 7 | 效果只校验引用存在，不限定属于目标类型；首版动作只经提案编辑 | Neon 第二轮评审，2026-11-27 |
| 8 | 参数和效果说明各限 200 字，换掉分段读取；分三个 PR 实施 | Codex 第三轮评审，2026-11-27 |
