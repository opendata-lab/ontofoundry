# 待办清单

记录已确认要做、但当前不做的事项。

- 新的待办追加到这里，不另建零散的 TODO 文件。
- 每条写清楚现状、要做什么、来源（含日期）。
- 开工时，中大型变更先按 AGENTS.md 写 `design/` 和 `plans/`，并在这里附链接。
- 做完后移到文末“已完成”，保留结果链接。

## 主键含日期的非快照表与表类型证据

现状：`expand_tables.py` 只认每日全量快照（`snapshot_date_column`），见 `docs/design/2026-11-18-large-material-modeling.md` LM-04、LM-06。要做，按内网实际遇到的先后：
- 主键 `(ds, 编号)` 的流水表现在要在 01b、03b 手写；可给 `entities.json` 加按业务编号作标识的写法（Foundry 的事件对象也只用业务主键）。
- `links` 经 `via` 生成的关联表数据集不能声明快照列，每日全量的关系表会混入已解除的旧关系。
- 展开关系用的键按列定义顺序收集、映射键按主键顺序，两者不一致时复合键会错位（main 上原有）。
- 平台给工作包补证据：Doris 分区列、OpenDataWorks 的 `update_type`（di/df）与 `layer`、最近两个分区的键重合度。只作证据，表类型仍由 Agent 声明、用户确认。
来源：用户 2026-11-25；Neon 评审 `~/.agents/handoffs/2026-11-25-neon-table-kinds-review/`（不入库）。

## 建模命令行（确定性生成与本地预检）

现状：有表的实体、属性、映射由 `entities.json` 加 `expand_tables.py` 生成（场景 B 中占 91% 的提案）；查询数据集、指标、规则、特殊关系仍手写提案 JSON，只占 9% 的提案，却占约 30% 的输出，修错和反查 client_ref 又用了 10 个回合。要做：把这部分改为命令或紧凑写法生成，提交前用工作包里的契约、上下文、表清单和材料清单做本地预检（同源，不复制规则）；示例改为按需的 `--help`。先做小步（扩展 `expand_tables.py`、`prepare_result.py` 提交前预检），在场景 B 上对比后再决定是否统一成完整命令行。来源：用户 2026-11-18；可行性评估见 `~/.agents/handoffs/2026-11-18-gemini-modeling-cli/`（不入库），依据 `docs/design/2026-11-18-large-material-modeling.md` §5.1 的运行数据。2026-11-19～20 内网复测（同设计 §7）：模型服务每回合 63–109 秒，40 分钟单轮只够约 22–38 回合，而抽取在本地需约 35 回合；压低回合数是内网能一轮跑完的前提。

已有的专项待办：[Ossie 上游结构跟进](plans/2026-10-20-ossie-upstream-alignment-todo.md)。

## 本体 MCP

首版（个人令牌、用户网关、跨空间检索）已确认，待实施：
- 设计：[外部智能体接入本体语义层设计](design/2026-11-11-runtime-agnostic-semantic-layer-for-agents.md)
- 计划：[外部智能体接入本体语义层实施计划](plans/2026-11-11-runtime-agnostic-semantic-layer-plan.md)

来源：2026-10-28 对照 Palantir Ontology MCP 文档（链接见文末“参考”），以及 2026-11-11 针对 zcode 等外部智能体消费本体语义与版本更新的讨论。

### Palantir 中 Agent、MCP、本体的关系（参考）

| 关系 | Palantir 的做法 | 依据 |
|---|---|---|
| 本体与空间 | 一个空间对应一个本体（1:1）；私有空间对应私有本体，共享空间对应跨组织的共享本体。官方明确说“和其他团队合作不是新建第二个本体的理由”，团队之间用项目角色控制权限 | 文档原文 |
| MCP 服务器与本体 | 一个 MCP 服务器就是一个 Developer Console 应用。建应用时选一个本体，SDK 生成后不能再改；在这个本体里挑要暴露的对象类型、动作类型、查询函数，并可限制只读写指定项目里的资源 | 文档原文 |
| Agent 与 MCP 服务器 | 文档写的是“可以组合多个 MCP 服务器”，并列出环境里的所有 Ontology MCP 服务器（MCP Hub） | 文档原文 |
| 一个 Agent 跨多个本体 | 没有专门机制，也没有“一个应用含多个本体”的说法。推断是连多个 MCP 服务器，每个服务器对应一个本体 | 推断，文档未直接写 |
| Agent 作为工具 | 平台内的 Agent（AIP Chatbot，原名 AIP Agent）可以保存成函数，再经 MCP 作为工具暴露给外部 Agent | 文档原文 |

对应到我们：工作空间相当于 Palantir 的“空间加本体”，一个空间一个 MCP 地址（`/api/v1/ontology/workspaces/<id>/mcp`）。已有客户端可继续挂载各空间地址。2026-11-12 已确认新增个人令牌网关，首版支持工作空间目录和跨空间语义查询，见上方专项设计与计划。差别在于 Palantir 的一个 MCP 服务器只暴露手选的资源子集，我们暴露整个空间。

### 1. 工具按对象类型生成

- **现状**：MCP 只有固定的通用工具 `search_ontology`、`get_ontology`、`search_objects`、`resolve_entity`、`get_object`，由参数指定类型。暴露范围是整个工作空间。
- **Palantir**：对象类型通过一个 SQL 工具查询；每个动作类型、查询函数各是一个工具，工具描述可以在本体管理里按“给 Agent 看的描述”单独填写。暴露哪些资源在应用里挑选。
- **要做**：
  - 按对象类型生成工具（名称、描述、参数来自对象类型和属性）；
  - 每个 MCP 地址可以选暴露哪些对象类型；
  - 想清楚和现有通用工具的关系（保留检索类工具，还是全部替换）；
  - 评估对象类型很多时工具列表的 token 成本，以及工具列表变化后的通知。
- **待定**：工具粒度（每类型一个查询工具，还是统一 SQL 工具加类型说明）；我们没有动作类型（决定 #37），首期只有读。

### 2. 修改本体结构的 MCP 服务

- **现状**：建模的写入只走提案。Agent 产出结果文件，平台检查后入库，人工审阅后接受。MCP 只读。
- **Palantir**：结构修改由另一个 Palantir MCP 提供，70 多个工具，能改对象类型、关系类型、动作类型，但不能写业务数据；与面向使用者的 Ontology MCP 分开。
- **要做**：
  - 设计一个面向建模者的 MCP 服务（与只读的本体 MCP 分开），提供对象类型、属性、关系、值类型、规则、指标、数据集的增改工具；
  - 写入仍落成待审提案，并复用试应用的检查（[串行化与原子化](design/2026-10-26-serial-atomic-modeling.md)），不绕过审阅；
  - 和现在“运行结束交结果文件”的方式怎么并存或替代，需要先设计。

### 3. MCP 支持 OAuth

- **现状**：外部访问只用部署时配置的固定令牌（[固定 MCP 令牌](design/2026-10-22-fixed-mcp-token.md)），只读，按空间里最早加入的管理员做成员检查，所有调用方共用一个身份。
- **Palantir**：MCP 复用应用的 OAuth 2.0 配置，“没有单独的鉴权系统”。
  - 授权码方式代表用户，令牌按用户权限收窄，支持 PKCE（公开客户端必须使用）；
  - 客户端凭据方式用于服务对服务；
  - 申请 `offline_access` 才有刷新令牌，刷新令牌每用一次就轮换；
  - 令牌权限取三者交集：用户权限、应用上配置的限制、申请的操作范围（如 `api:use-ontologies-read`）。
  - 文档没有提到 MCP 授权规范里的受保护资源元数据和动态客户端注册。
- **要做**：
  - 平台作为 OAuth 2.0 授权方（或接入现有统一认证），支持授权码加 PKCE、客户端凭据和刷新令牌；
  - 令牌权限取用户权限、工作空间和操作范围的交集；
  - 评估是否实现 MCP 授权规范的受保护资源元数据，让 MCP 客户端自动发现授权地址；
  - DataAgent 侧代用户调用时如何传递用户身份（与 DataAgent 服务化架构的凭据设计一起考虑）；
  - 固定令牌是否保留为内网部署的简易方式。
- **补充（2026-11-12）**：首版用户网关先用个人令牌（不过期、可撤销）。MCP 客户端浏览器授权已决定在网关首版之后实施（设计 SL-16），接入同一网关并保留个人令牌；平台登录（本地账号、统一认证与用户信息钩子）见[平台登录](design/2026-11-12-platform-login.md)。

### 4. 外部智能体接入的后续方向（未确认）

- **现状**（2026-11-12）：首版为用户网关的三个只读工具和 `plugins/ontofoundry` 客户端插件，见上方设计第 3 节。
- **要做**：设计第 10 节列出的后续方向各自开工前先写设计，说明来源、语义还是执行优化、删掉会失去什么、已有结构能否表达：反馈处理（SL-04 扩展：状态、回复、转提案）、插件内斜杠命令（SL-11）、查询委派（SL-10）、结构化变更提案（SL-12）、调用记录转建模输入及记录的查看与清理（SL-15）。
- **注意**：SL-13（属性绑定业务 API／MCP 返回值）和 SL-14（业务动作）与“执行细节不进入模型”的原则和决定 #37 冲突，需先确认是否推翻 #37。
- **来源**：2026-11-11 外部智能体接入讨论，2026-11-12 设计修订时从设计正文移出；原详细草稿见 PR #51 的提交历史。

## 建模质量

### 1. 指标口径与业务规则的语义正确性

- **现状**（2026-11-15）：[表多时降低建模成本](design/2026-11-15-modeling-scale.md)实施后，青禾 34 表回归（`apps/api/evals/acceptance/results/2026-11-15-modeling-scale-regression-2/`）11 个指标都有定义，但复购率口径错误（会员跨两天各下一单得 0%，应为 100%）；拒收不计库存、闭店不计在营两条规则只检查数量非负或日期，没有表达材料的约束。
- **决定**（2026-11-15，用户）：不在技能里按个案补说明，难以维护。这类语义判断由 Agent 完成、经人工审阅提案把关；回归只记录模型表现。平台事实（可用函数、列名）用从平台代码生成的本地检查表达。
- **要做**：暂无。若以后要改进，只考虑通用机制（如审阅界面展示指标口径与引用的材料行并排对照），先写设计。
- **来源**：2026-11-15 第二次回归的质量核对（`quality.md`）。

### 2. 技能评审余项

- **现状**（2026-11-15）：Codex、Gemini 对建模技能的评审（`~/.agents/handoffs/2026-11-15-codex-skill-method-review/`、`2026-11-15-gemini-skill-method-review/`）中，主要项已在 MS-08–MS-10 处理，以下未做。
- **要做**（按价值排序，均以删减或合并为主）：
  - 本地检查同一归属下的重名、规则表达式里的关系路径（两次回归各因此用掉一次平台修正轮次），按平台代码生成或比对；
  - 两个连接下同名 schema.table 时，展开脚本与列检查按连接区分表；
  - `check_part`、`prepare_result` 加载但不用 context，`--context/--schema/--output` 路线无法提交，可删；
  - `init_workflow` 与 `prepare_result` 各有一份工作文件清单和归档遍历，合为一处；`read_input` 的 `fit_lines`、`resolve_pointer` 无调用者；
  - 示例目录：11 个 `delete-*.json` 只差 target_kind；`catalog.json` 的 examples 数组同时是测试清单，需先把测试元数据移到 tests 再精简；
  - 部分测试断言说明文字原句，改为断言行为和输出。
- **来源**：2026-11-15 技能评审。

### 3. 提案入库时按依赖组逐组校验整张图

- **现状**（2026-11-15）：`contracts/proposals.py` 的 `group_items` 对每个依赖组调用 `_validate_group`，每次都校验整张候选图，耗时随批次大小平方增长。SQLite 上本地测得（对象加属性，含一次批次读取）：200 条约 0.3 s，400 条约 1.1 s，绝大部分耗在 `parse_result`。只在智能体提交批次时发生，不影响审阅时的接受。
- **要做**：改成增量校验或只校验组内新增元素及其引用，同时保留按组定位错误的报错方式；先补一个按组报错的测试再改。
- **来源**：2026-11-15 排查“200 条提案接受一条很慢”时发现；批次读取的同类问题已修复。

### 4. 性能审查余项

- **现状**（2026-11-15，SQLite 本地测得）：批次读取的重复实例匹配、文档实例列表的关系校验、决定时多余的实例读取和原子组逐条查询已改为每请求一次。剩余：
  - 发布激活和批量接受实例时，每次写入都重读并哈希全部实例：200 个约 0.85 s，400 个约 2.8 s，期间持有工作空间锁。要在一次批量操作内共享实例状态，后续写入仍要看到前面的变化，并保留逐行版本检查、证据和历史；
  - 相似定义提示对每个提案扫描全部候选：280×280 约 0.3 s，是批次读取剩余耗时的主要部分；
  - 一次草稿校验内对每个映射和对象重建草稿索引，目前为毫秒级；
  - 前端提案卡片和搜索对整个列表重复 `find`／`some`，尚未在浏览器中测量，先测再改。
- **来源**：2026-11-15 Codex 性能审查（`~/.agents/handoffs/2026-11-15-codex-performance-review/`）。

### 5. 多元关系改用多键关联

- **现状**（2026-11-15）：多元关系导入为中间对象，并为每个参与角色生成编号属性（`docs/concepts/identifiers.md`、`link-types.md`）。外键指向物理键时编号绑定只能待补全，按 `docs/design/2026-11-15-accept-completeness.md` AC-04 这类属性无法接受。
- **要做**：不再生成角色编号属性，中间对象直接用表上的多个键列关联参与对象（例：排班 → 医生 用 `schedules.doctor_pk = doctors.doctor_pk`）；同步修改概念文档和 Ossie 导入。
- **来源**：用户 2026-11-15 决定。

### 7. 本体标识与登记表主键不一致时报告

- **现状**（2026-11-24）：Ossie 导入的对象映射直接优先采用数据集声明的主键作为来源键（`adapters/ossie/mappings.py` `identity`），本体标识与表主键不一致时不报告。内网材料中有 3 处：组件标识只有名称而表主键含环境、区域；规则标识只有 key 而表主键为 domain、label、key；问题标识四段而 issue_key 可能本身唯一。
- **要做**：导入报告列出这类差异，交由业务确认哪一边是对的，不自动改标识。
- **来源**：`docs/design/2026-11-24-ossie-relational-identifiers.md` RI-06，用户 2026-11-24“不要将错就错”。

### 6. 校验阶段余项

- **现状**（2026-11-15）：Codex 校验阶段审查（`~/.agents/handoffs/2026-11-15-codex-validation-review/`）列出的缺口已由用户逐项决定，见 `docs/design/2026-11-15-accept-completeness.md` AC-09 至 AC-12；相同业务标识的实例保留只提示。
- **要做**：按该设计第 8 节的顺序实施。
- **来源**：2026-11-15 Codex 校验阶段审查。

## 已完成

（暂无）

## 参考

- [Ontology MCP 概览](https://palantir.com/docs/foundry/ontology-mcp/overview/)
- [Ontology MCP 鉴权与授权](https://palantir.com/docs/foundry/ontology-mcp/authentication-and-authorization/)
- [Ontology MCP 入门](https://palantir.com/docs/foundry/ontology-mcp/getting-started/)
- [Ontology MCP 示例架构](https://www.palantir.com/docs/foundry/ontology-mcp/sample-architecture)
- [MCP 工具与 Agent 配置](https://palantir.com/docs/foundry/ontology-mcp/mcp-tools-and-agent-configuration/)
- [Ontology MCP 示例工作流](https://palantir.com/docs/foundry/ontology-mcp/example-mcp-workflows/)
- [创建 Developer Console 应用](https://palantir.com/docs/foundry/developer-console/create-application/)
- [应用限制](https://palantir.com/docs/foundry/developer-console/application-restrictions/)
- [编写 Foundry OAuth2 客户端](https://palantir.com/docs/foundry/platform-security-third-party/writing-oauth2-clients/)
- [本体概览（本体与空间 1:1）](https://palantir.com/docs/foundry/ontologies/ontologies-overview/)
- [共享本体](https://palantir.com/docs/foundry/ontologies/shared-ontologies/)
- [组织与空间](https://palantir.com/docs/foundry/security/orgs-and-spaces/)
- [AIP Chatbot Studio 工具](https://palantir.com/docs/foundry/chatbot-studio/tools/)
- [Palantir MCP 概览](https://www.palantir.com/docs/foundry/palantir-mcp/overview)
