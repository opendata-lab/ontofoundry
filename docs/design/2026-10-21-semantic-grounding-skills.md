# 语义锚定：原子化 Skill 与场景组合

日期：2026-10-21。状态：已确认，待实施。来源：用户 2026-10-21 与 ChatGPT 的讨论（Semantic Grounding Service、semantic-extraction 目录结构）及当日决定。

## 1. 定位

把自然语言中的概念、实体、关系和指标映射到工作空间的已发布本体，形成两个方向：

- **写入**：业务资料 → 语义抽取 → 本体提案／实体实例 → 人工审阅 → 发布。
- **读取**：用户问题 → 语义识别 → 本体映射（带 id）→ 查询执行。

共享的映射能力放在平台 MCP 工具里，所有 Agent 调同一套；Skill 只写方法（何时调哪个工具、结果如何使用、输出什么）；各场景通过 Agent 挂载的 Skill 和平台的任务说明组合。

## 2. 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| SG-01 | 拆为三个独立 Skill，每个自带输出 Schema，单独打包、单独安装：`ontology-discovery` 从文档、表结构发现对象类型、属性、关系（及数据集、映射、指标、规则），判断新增还是复用；`entity-extraction` 按本体约束抽取实体、属性值和关系实例，并调用 `resolve_entity` 消歧；`semantic-grounding` 把用户问题中的业务术语映射到本体对象和指标。 | 已确认 |
| SG-08 | Skill 负责执行策略，Tool 负责确定性能力：检索、候选召回、判级、校验在平台 Python 服务中完成；Skill 只决定何时调用、如何使用结果，Agent 只在工具返回语义歧义（如 `AMBIGUOUS`）时辅助判断或追问用户。 | 已确认（2026-10-21） |
| SG-09 | 不接入 opendataworks Portal MCP：其血缘是调度任务自动记录的表级加工关系，不表达业务关系；表与字段注释、表结构已由平台自己的表结构同步取得，数仓分层通常体现在表名前缀中。变化影响由平台的表结构同步记录定位。DataAgent 自带的问数查询工具不受影响。 | 已确认（2026-10-21） |
| SG-02 | 采用 AI 动态 workflow，不做确定性流程编排，不新建 Agent 或流程引擎：Agent 挂载可用的 Skill，平台的任务说明只给出目标（建模、抽取实例、回答问题）和材料，由 Agent 按任务与材料自行判断组合哪些 Skill、调用哪些工具。各 Skill 的 description 写清适用条件，供 Agent 选择。 | 已确认（2026-10-21，用户调整） |
| SG-03 | 共享匹配能力做成平台 MCP 工具：`search_ontology`、`get_ontology`、`search_objects`、`resolve_entity`。 | 已确认 |
| SG-04 | 不新增 `submit_proposal` 工具：提案仍由运行结束时的结果文件整批提交，平台整批校验入库（绑定运行标识，避免半途提交与重复提交）。 | 已确认（2026-10-21） |
| SG-05 | `validate_extraction` 不做成 MCP 工具：沿用 Skill 自带的 `check_part.py`、`prepare_result.py` 做本地校验，平台入库再校验一次。 | 已确认（2026-10-21） |
| SG-06 | 共享参考文档（核心模型、原则、取值表）与共享脚本只保留一份源码，打包时复制进各 Skill 包，不手工维护多份副本。 | 已确认 |
| SG-12 | 共享资源按完整清单复制：检查器 `check_result.py` 及全部共享脚本、`examples/`、`extract-kit/`、运行依赖与许可文件；`show_example` 只读取本包内的模板。三个安装包分别在隔离目录中验收，不能借用旧 `ontofoundry-modeling` 目录。`offline_budget.py` 与测试不进包。 | 已确认（2026-10-21，Codex 评审） |
| SG-13 | 不做 Workflow 路由：建模与实例抽取都投递给同一个建模 Agent，续跑和自动修复沿用现状；Agent 在运行内动态组合 Skill。 | 已确认（2026-10-21，用户调整） |
| SG-14 | 运行凭据固定签发 `ontology:read`、`instances:read`、`mappings:read`，不按运行类型区分（见 Entity Resolver ER-13）。问数沿用 DataAgent 的现有配置。 | 已确认（2026-10-21，内网使用、简单优先） |
| SG-15 | 平台不按运行目标限制提案种类：例如“只抽取实例”的运行中，Agent 发现本体缺少概念时，可同时提出定义提案与相关实例提案，由人工审阅决定是否接受；平台不记录运行类型，也不据此拒收提案。 | 已确认（2026-10-21，简单优先） |
| SG-07 | 三个 Skill、MCP 服务登记信息和各 Agent 配置作为一个插件包统一发布（`plugin.json` 记录版本、内容和要求的平台最低版本）。DataAgent 目前不支持整包加载：安装脚本只复制 Skill 到 `SKILLS_ROOT_DIR`，MCP 登记与 Agent 配置由管理员按包内说明在后台完成；DataAgent 原生插件加载属于 opendataworks 改动，另行排期。 | 已确认（2026-10-21） |

## 3. 目录

```text
integrations/dataagent/
├── shared/                      # 唯一源码，打包时复制进各 Skill
│   ├── references/              # core-model、principles、quick-reference、examples/（含 protocol/）、extract-kit/
│   ├── scripts/                 # init_workflow、read_input、show_element、show_example、check_part、check_result、prepare_result
│   └── requirements.txt、LICENSE、NOTICE、PROVENANCE.md
├── skills/
│   ├── ontology-discovery/       # 类型、属性、关系、数据集、映射、指标、规则
│   │   ├── SKILL.md
│   │   ├── references/          # methodology、extract-types、extract-mappings、extract-metrics-rules、modeling-patterns、reading-ossie、import-completion
│   │   └── output-schema.json   # 提案 Schema 中定义类元素的子集
│   ├── entity-extraction/     # 文档实例与关系实例
│   │   ├── SKILL.md
│   │   ├── references/          # extract-facts
│   │   └── output-schema.json   # 提案 Schema 中实例类元素的子集
│   └── semantic-grounding/     # 问题到本体的映射
│       ├── SKILL.md
│       └── output-schema.json   # 结构化理解结果，见 §5
└── agents/                      # Agent 配置：系统提示词与挂载的 Skill
    ├── agent_ontofoundry.md         # 建模与实例抽取（ontology-discovery + entity-extraction）
    └── agent_ontofoundry_qa.md      # 问数
```

两个抽取 Skill 的 `output-schema.json` 由 `ontofoundry.proposals.v1.schema.json` 按目标类型裁剪生成，契约源仍是平台的提案 Schema；同一次运行加载两个 Skill 时，片段合并成一个结果文件，与现在一致。

## 4. 场景

| 场景 | Agent | 通常组合的 Skill（Agent 动态选择） | 平台运行入口 | 产出 |
|---|---|---|---|---|
| 建模 | `agent_ontofoundry` | ontology-discovery（材料含可抽实例时加 entity-extraction） | 建模会话的计划／抽取／补齐 | 定义提案（及实例提案） |
| 实例抽取 | `agent_ontofoundry`（同建模） | entity-extraction | 对已发布版本、选定材料发起的抽取运行 | 实例提案 |
| 问数 | `agent_ontofoundry_qa` | semantic-grounding | DataAgent 问数会话 | 结构化理解结果 → DataAgent 自有查询工具执行 |

实例抽取需要平台新增一个运行入口（选择材料、绑定已发布版本、实例只引用已有类型），任务说明指定使用 entity-extraction，提案进入同一审阅流程。

## 5. semantic-grounding 输出

```json
{
  "workspace_id": "…", "version_id": "…",
  "question": "星河电子近三个月的采购金额",
  "metrics": [{"id": "…", "display_name": "采购金额"}],
  "object_types": [{"id": "…", "display_name": "供应商"}],
  "entities": [{"mention": "星河电子", "object_type_id": "…", "status": "MATCHED", "entity_ref": "…", "display": "星河电子有限公司", "match": "name_contains"}],
  "filters": [{"property_id": "…", "operator": "eq", "value_from": "entities[0]"}],
  "time_range": {"text": "近三个月", "field": {"dataset_id": "…", "column": "order_date"}},
  "unresolved": [],
  "clarification": null
}
```

- 所有引用带 id；名称只用于展示。
- `entities[].status` 为 `AMBIGUOUS` 时，`clarification` 写出追问，不进入查询。
- 该结果写入问数运行记录，用于离线评测“问题→本体映射”是否正确，与 SQL 正确性分开衡量。

## 6. 迁移

- `ontofoundry-modeling` 按 §3 拆分；内容不改写，只移动文件和调整 SKILL.md 中的路径。现行 SKILL.md 的步骤编号和脚本调用保持不变，避免真实运行回退。
- 建模 Agent 改为引用两个抽取 Skill；DataAgent 管理后台同步发布，迁移包与 `迁移说明.md` 更新。
- 拆分后在新会话中做一次真实建模验收（DeepSeek 预算，先确认）。

## 7. 不做

- 不新建流程引擎、Agent 运行时或第二套提案格式。
- 不把向量召回、实体匹配逻辑写进 Skill。
