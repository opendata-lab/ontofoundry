# 建模 Agent token 效率实施计划

日期：2026-10-20。状态：Claude review 完成，用户已确认，2026-10-20 开始离线实现。

依据：[token 效率设计](../design/2026-10-20-modeling-agent-token-efficiency.md)。不改变核心模型、提案契约或 Ossie 语义；不建立新的模型字段、业务状态、数据库表或迁移。

## 1. 评审与进入条件

1. 将 scratchpad 的 `token-diagnosis.md`、设计和本计划一并交给 Claude review。本轮不通过模型／CLI 自动发起 review，用户自行交接；报告不入库。
2. Review 核对四份 trace 的归因和用量守恒、缓存原因的证据等级、跨 Dataset ratio 的阻断事实、节省估算不重叠、所有原有校验的保留。
3. 用户已确认设计 §9：不可表达单项不阻断整批，“不要追问”同样交付合法范围并说明缺项；修正共用两轮预算。
4. 实施前复核 git 状态和当前工作区的核心模型／名称统一变更。历史旧字段和 MCP 接口不能作为新技能范本；上传 Schema 与当前 JSON 内容相同，但不能假定后续一直不变。
5. 用户另行进入实现轮后，按以下顺序编辑；全部编辑完成后统一跑测试。除用户明确要求，不 commit/push。运行时建议由另仓库独立评审，不能在本仓库顺手修改。

## 2. 固化离线基线与预算工具

涉及文件（实施轮拟新增／修改）：

- `integrations/dataagent/skills/ontofoundry-modeling/tests/`：去凭据、虚构业务名的四类样本，不能复制原始 trace 入库。
- `integrations/dataagent/skills/ontofoundry-modeling/scripts/`：离线输入预算／trace 统计工具，具体文件名实施时确定。
- `apps/api/tests/test_t3_proposal_results.py`：上传和提示词边界的 mock 测试。

工作：固定 U/C/O/I 定义、TSV COPY 转义读取方式、主用途映射和回退规则；按任务输出总量、轮次、每类用量以及不确定项。只对已有 trace 分类，其他运行标记无法分类。静态重放保留必要读取、生成和校验成本，不将删掉某类轮次冒充完成任务。

预算统计分别报告上传 bytes、模型实际选择读取的 bytes、估计 tokens 和系统／工具开销；中心估计 bytes/3，区间 bytes/4–bytes/2，记录 hash 和估计方法。真实 usage 只能来自最后一次运行，不用估计数替代。

测试：四任务逐轮总和必须分别为诊断报告中的 U/C/O，T44 零用量不能丢；一行 Schema 和 COPY 双反斜线不能误解析；缺 trace 时明确 N/A。虚构 fixture 不含业务连接名、真实业务表、headers 或 token。检查重放的收益和子集不被重复相加。

## 3. 建立示例和确定性辅助脚本

涉及文件：`integrations/dataagent/skills/ontofoundry-modeling/references/`、`scripts/check_result.py`、拟新增 `scripts/prepare_result.py` 及其 tests。

1. 为九类 target 建最小完整示例和可用的 create/update/delete 外壳；复杂分支按需分文件。已有事实例子继续保留，不把单一零售模式当唯一建模模式。
2. 明确 Mapping.fields 属性 name、局部 source_id、复合 key_columns、同批引用、完整证据、ratio 同 Dataset、count 不给 measure、expression 边界；为同 Dataset ratio 给合法正例、跨 Dataset ratio 给不出提案、说明缺项与建议的例子。
3. 辅助脚本只从本轮固定上下文取结果头、before/hash，组装／合并 items，检查重复引用；不填业务默认值，不推理语义，不补证据，不改指标公式。临时片段限工作区内，最终文件原子替换。
4. 错误格式携带 JSON Pointer、item 引用、错误代码、短说明和示例定位；Schema oneOf 分支筛选不能隐藏真实失败。摘要≤4 KiB、完整错误落盘，记录总错误和省略数量，退出码不变。读文件／JSON 解析失败也要短报错。
5. 局部修改后始终整批检查。保留 Schema、操作、引用、重复目标、完整固定头、before/hash 校验；新示例、生成脚本不能只通过较弱的自写 jsonschema 检查。

测试：每个示例补虚构 header/context 后执行真实 `check_result.py`，再通过服务端最终图与证据测试；负例覆盖错误判别字段、非法引用、同名局部来源、values 中像引用的字面量、过期 hash、错误 before、人工证据修改、坏行号、半写产物和重复 client_ref。验证错误摘要短且完整报告仍含全部错误、非零退出码保留。复杂语义后端拒绝也算校验成功发现问题，不能要求脚本对所有非法图都报错。

## 4. 调整平台输入组织

涉及文件：

- `apps/api/src/ontofoundry_api/services/dataagent.py`：稳定指令与动态输入组织、精确路径、预算提示、输入清单。
- `apps/api/src/ontofoundry_api/services/proposals.py`：已有 `proposal_context`、固定头和完整上下文维持语义；必要时委托新的服务函数生成派生工作包。
- `apps/api/src/ontofoundry_api/api/agent_conversation.py`：只接入上传、参数与权限检查；新增业务选择／工作包派生放 `services/`。
- 拟新增 `services/modeling_input.py`：确定性生成材料／Dataset／已有元素索引、示例选择和预算统计，最终命名实施时确认。
- `apps/api/tests/test_t2_pinned_context.py`、`test_t3_proposal_results.py` 及新增输入打包测试。

工作：完整固定上下文、完整 Schema、原材料继续给检查器；模型默认只读小工作包／速查／必要示例／小材料。本例不裁剪两份 7,351 B 材料。工作包包含旧材料清单（不是只有“本轮新增上传”）、原行号范围、材料 hash、六 Dataset 的 UUID 与列信息、已有元素摘要及精确回读入口。保留上传去重。

大输入采用保留原文件的派生片段，显式范围与遗漏索引；update/delete 必须保留完整真实目标和 hash，相关继承、反向引用和依赖不能被关键词裁剪掉。派生工作包不持久化到核心模型，不改 contracts/Pydantic/前端类型。

测试：mock DataAgent upload/deliver，无网络；比较空业务草稿、已有六 Dataset、改四名称、大材料、无新材料但有历史材料、多源映射和继承场景。断言相同静态内容顺序稳定、动态值位于后部、run_token/hash 不丢、原材料字节／行号不变、完整上下文仍可校验。不存在材料／索引不完整时要明确失败，不能静默省略。

## 5. 重写技能流程和错误收敛

涉及文件：`integrations/dataagent/skills/ontofoundry-modeling/SKILL.md`、`references/core-model.md`、`references/modeling-patterns.md`、适用的其他 references、`integrations/dataagent/agents/agent_ontofoundry.md`、`integrations/dataagent/README.md`。

工作：首轮批量小输入→语义预检→完整生成→检查→最多两轮定点修正→简短说明。明确使用已知路径；禁止 find 全盘、env、猜技能位置、通读无关 references、遍历 `$defs` 和连续 Schema result_ref 分页。提供源文件精确取路径／行的操作示例，stdout≤8 KiB。首次写结果目标≤T4。

仅必要业务信息缺失沿用 needs-input；技术格式错误不能提问解决。不可表达单项不出提案，合法内容照常交付并说明缺项、原因及建议，无需事先授权，“不要追问”同样适用，不新增状态。

核对 `api/agent_conversation.py` 已有结果拒收修复链和 `test_t3_proposal_results.py` 的修复用例，新增服务层运行预算传播：初次生成、Agent 自修正和平台拒收修复共用最多两轮修正额度。明确一次真实验收只触发一次 deliver，不允许后台偷偷再请求模型。实现若需改调度或持久化结构，先扩充设计并评审，不临时添迁移分支。

测试：静态检查技能全部路径可用、每项示例可跑、工作区边界正确；fixture 验证技术错误→失败、业务缺失→needs-input、完整结果→通过、修正预算耗尽→明确失败。不要把静态关键词检测当 Agent 行为证明；轮数和理解质量最终由一次真实运行验证。

## 6. DataAgent 建议单独交接

仅列建议，不在本仓库或本轮执行：

- 已有建模 Agent 的 max_turns=12 已由 Claude 设置并发布，其余运行时项仅交接建议。
- 共享模型 max_output_tokens 暂不下调；核验独立覆盖支持后再决定是否给该 Agent 单轮 16,384。不能假设平台 deliver 已支持该参数。
- 增加累计用量预算、压缩 generation／bytes／脱敏前缀 hash 观测；文本 fetch 单位和钳制后的 next_offset 明示。离线回放不能调用模型压缩器。
- 使用现有 `CompactionSession` 验证低于水位原样、跨代固定前缀、超大受保护尾部等情况；不以提高阈值或关闭治理替代源头控制。

部署前本仓库改动应按 README 将技能复制到 SKILLS_ROOT_DIR 并重启；提示词同步到已有 Agent 管理后台并发布。这些属于实现完成后的部署步骤，须在相应任务获授权后执行。本轮不访问后台、不验证凭据。

## 7. 统一离线测试与退出门槛

实施轮全部编辑完成后统一运行，不逐处改逐处测。按仓库已有依赖环境选用命令，避免下载依赖或隐式联网：

```bash
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python -m pytest -p no:cacheprovider integrations/dataagent/skills/ontofoundry-modeling/tests
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python -m pytest -p no:cacheprovider apps/api/tests/test_t1_proposal_contract.py apps/api/tests/test_t2_pinned_context.py apps/api/tests/test_t3_proposal_results.py
```

以上 venv 路径实施前核实；新增输入预算和辅助脚本测试并入同一测试阶段，不假定现有测试已覆盖新功能。按实际调用路径补上最终图／证据／服务端语义校验用例。所有 DataAgent 和 MCP 请求 mock，禁止真实模型调用。没有前端／部署访问方式变更，不需要视觉测试或局域网验收；若实施扩大到前端／部署配置，另按 AGENTS.md 补截图、视觉测试和局域网验证。

离线门槛：

- 四份历史 usage 求和和分类核对通过，缺证据处明确标记，收益不重复相加。
- 九类与三操作示例通过强度不减的校验；跨 Dataset ratio、错误证据、过期上下文等负例按正确层次拒绝。
- 首轮静态选择输入 bytes/3≤12,000，后续新增≤8,000；捕获系统／工具预算，未知部分不能假称计入。stdout≤8 KiB、错误摘要≤4 KiB；完整校验文件仍存在。
- mock 测试证明材料去重、旧材料清单、稳定顺序、固定头／hash、原证据行号、修复预算和产物消费边界。
- 无凭据写入文档或 fixtures，无代码以外的模型字段变更，无未授权文件修改；review 问题已逐项关闭。

本轮已进入离线实现，全部编辑后统一测试，失败项修正后复验；实际结果见 scratchpad 的 token-impl-report.md。

## 8. 一次真实运行验收和回退

1. 用户确认待决项，离线门槛全通过；记录 Agent、技能、平台、Schema 的版本／hash 和有效预算。准备虚构六表、两材料预期清单，不使用历史结果文件。
2. 验收四个可表达指标并清楚说明退款率缺项、同数据集约束及共同数据集建议；合法分量照常交付，无需先追问，不改造数据源。
3. 获得真实运行授权且余额可用后，只发一次 deliver；记录逐轮 usage 和产物，不自动重试／后台修复重开任务，不接受或发布提案。
4. 对可交付范围检查：正常≤8／含修正≤10 轮、I≤180,000、U≤40,000、O≤25,000、≤T4 开始写、修正≤2、Schema fetch/search=0、探索／越界=0；全部确认范围和强校验通过。跨数据集指标不出提案，确认合法分量与缺项说明均完整。
5. 与 43 个有用量轮、I=1,377,381、U=201,573 的失败基线比较，同时说明任务范围差异，不能只报成本。记录缓存回退的 generation 与前缀证据；无日志就继续标为推断。
6. 失败只保存脱敏 trace 和检查结果，返回离线诊断，不消耗第二次模型调用。发现漏项／弱化校验，回退技能和模板至预先记录版本；不回滚用户草稿，不删材料，不自动接受失败提案。上传清单／输出消费兼容性须在部署前离线验证。

## 9. 交付与完成定义

实现完成的交付应包含平台输入组织、技能／示例、辅助及检查脚本、测试和实际预算结果；发布完成还需技能同步与已有 Agent 提示词发布记录。真实验收若因额度不可用而未做，明确列为未验收，不能以离线估算替代。

本轮交付实现、离线测试和预算报告；无模型调用、部署、commit 或 push。

## 10. 本轮实现说明（2026-10-20）

用户已确认设计 §9。离线实现采用 modeling_input.py、prepare_result.py、read_input.py、offline_budget.py；计数写既有运行 manifest 与结果 SHA256 绑定的执行侧文件，不扩契约／核心模型／数据库。大材料按原行号有界读取，不自动关键词裁剪；未知 DataAgent 系统／工具预算单列。脱敏四类 usage fixture 和可选原 trace 验证守恒，不宣称模拟了新生成行为。统一测试、预算数值和剩余真实验证项写本轮 scratchpad 的 token-impl-report.md，不将评审报告入库。
