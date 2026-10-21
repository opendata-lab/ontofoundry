# 建模 Agent harness 优化实施计划

日期：2026-10-20。状态：用户已授权离线实现；以 [设计](../design/2026-10-20-modeling-agent-harness.md) §11 第8–13项覆盖旧正文，及 [token效率设计](../design/2026-10-20-modeling-agent-token-efficiency.md) §9为准。

## 1. 范围与确认

已读 AGENTS.md，保留当前 name/display_name 与 token 优化未提交改动。此次只改仓库源码、技能、提示、文档和离线测试；不访问 DataAgent、DeepSeek 或外部服务，不部署、不 commit/push，不改排除目录。

- 不采用来源 A1；材料可支持未同步表的 Dataset 提议，方法及最终说明提示“需先在数据管理同步该表”。表未同步校验和审阅 UI 留待 SQL 数据集设计，不增加服务端拦截。
- 只提供正例，不建立 negative 或 semantic-cases 阅读目录。错误输入在测试内构造；业务常见坑及数字差异归各抽取方法。
- 系统正文按 §2.1 四行加“思考过程和回答使用简体中文”。正文后无配置说明。问数 Agent 保留全部查询语义。
- 共同必读 ≤8,200 B、混合任务方法决策段 ≤6,000 B、首轮总量 ≤36,000 B；原材料和范围不缩减。

## 2. 实施批次（全部编辑后统一测试）

1. 先记录离线字节基线，区分配置文件和系统正文；计划按确认表修订后执行。
2. 重排 SKILL 执行清单、quick-reference 九类地图、principles、methodology 及四份 extract 方法。每个方法提供行号索引、判断标准、数字坑例和具体提问／推荐；core-model ≤4,500 B，patterns 不重复 JSON。其余上限依设计 §5、§8。
3. 保留全部正例，修正主管关联与 quantity×unit_price 示例，补标识、重化、虚拟父、成员、事实值／复用、登记和 needs-input。catalog 双向发现；所有提案例经完整 Schema、checker、server_parse。协议例单独走协议验证，不送提案 Schema。提供 `show_example.py <target_kind> [--operation create|update|delete]`，返回最小正例及必要依赖，stdout ≤8 KiB；未知类型列出选项。测试脚本输出本身也经两层校验。
4. 建模每轮只给动态工作包、token、输出路径和用户消息；结果头／材料／Schema／MCP 留在工作包。普通对话独立模板。修复时重建新 context 与工作包，保留 pinned draft、原材料索引／Schema、累计预算；MCP 凭据随新 token 重新签发，固定原版本和发起用户，新提示附服务端真实错误，不贴完整头。
5. checker 和 prepare 错误给精确位置／client_ref、期望、实际、可执行查写法命令；摘要 ≤4 KiB，完整错误落盘，失败不替换最终文件。保留全部现有检查；不复制最终图验证器。needs-input 非空问题及同轮互斥确定性检查区分404与暂态下载故障。
6. 增加建模首轮、无材料、有历史材料、有MCP、修复和普通对话快照；错误 mutation 验证真实位置、期望／实际和命令。跨本地／平台修复共用最多两次预算。
7. offline_budget 按实际系统正文计算，对照 §8.2 列单文件／共同／方法／示例／工作包／首轮预算及单主题路线。配置体积单列，未知工具包装显式未知。README 写同版部署、五行正文、全部技能脚本及后续真实验收事项，不运行历史清库流程。

## 3. 统一验证

全部编辑结束后执行（不访问外部系统，服务测试使用临时测试数据库）：

```bash
cd apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests
# 以下在仓库根目录
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python -m pytest -q integrations/dataagent/skills/ontofoundry-modeling/tests
apps/api/.venv/bin/ruff check apps/api/src apps/api/tests integrations/dataagent/skills
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python integrations/dataagent/skills/ontofoundry-modeling/scripts/offline_budget.py
```

失败后集中修复，再重跑受影响检查；已通过且未变化的检查不重复。核对无弱化最终图／证据／权限／并发，无新增来源拦截，无外部请求，无未授权目录编辑。此次无前端或部署实现，不执行视觉测试／局域网部署验证。

## 4. 交付与后续

终端输出分组改动、测试结果、改前后系统正文／每轮提示／共同必读／首轮总量和真实运行待验事项；报告保存到用户指定 scratchpad 的 harness-impl-report.md。

部署及唯一一次真实请求需后续授权。平台、技能、新系统提示配套部署；核对 max_turns=12、不重置旧执行预算。真实验收与 token 效率设计共用一次：≤T4 写入、正常≤8／含修正≤10轮、修正≤2、I≤180,000、U≤40,000、O≤25,000、无 Schema 探索，合法范围完整、缺项解释与证据通过。不把离线字节统计当模型行为证明；失败保存证据，不自动再次运行。

## 5. 第二批：分步建模与建模工作流（设计 §11 第 14、15 项）

状态：已实现（2026-10-21，待真实验收）；与本节的偏差见设计 §14。依赖数据集来源 DS-17 的表目录与紧凑工作包；值类型完成后正例与 01-types 片段包含 value_type。

### 5.1 工作区与文件

DataAgent 会话工作区内新增 `modeling/`（与 `output/` 平级，仍在工作区内，prepare 的路径检查同样适用）：

| 路径 | 写入阶段 | 内容与约束 |
|---|---|---|
| `modeling/plan.md` | ① 计划，③ 抽取时更新 | 首行 `场景：全量｜增量｜优化｜小改动`；范围、实体或变化或问题清单、来源表、阶段勾选、待决定问题；≤4 KB |
| `modeling/entities.json` | ① 计划 | `{"scenario", "items":[{"name","display_name","basis":[{"material_id","line"}|{"table"}],"tables":[],"status":"new|existing|drop"}]}`；全量和增量的实体或变化清单 |
| `modeling/issues.json` | ① 计划（优化场景） | `{"items":[{"element_id","problem","fix","impact":[element_id]}]}` |
| `modeling/notes.md` | ③ 抽取过程 | 证据对照与判断记录，≤2 KB；上下文压缩后先读它 |
| `modeling/parts/NN-*.json` | ③ 抽取 | items 数组片段：01-types、02-links、03-datasets、04-metrics-rules、05-facts；可再按实体分组为 `01-types-a.json` 等，按文件名排序合并 |
| `modeling/checks/` | ③④⑤ | 片段快速检查与合并完整检查的报告（摘要 ≤4 KB，全文落盘） |

### 5.2 脚本接口

| 脚本 | 变化 |
|---|---|
| `scripts/init_workflow.py --work-pack <路径>`（新增） | 建 `modeling/` 骨架，按工作包写 plan.md 模板（场景、已有元素与表目录摘要的位置）；幂等，已存在的文件不覆盖 |
| `scripts/check_part.py <片段>...`（新增） | 片段快速检查：Schema 中单条 item 的形状、片段内 client_ref 唯一与引用闭合（跨片段引用列为“待合并检查”，不报错）、display_name 缺失提示；不计修正次数 |
| `scripts/prepare_result.py` | `fragments` 允许传目录（`modeling/parts/`），按文件名排序展开；其余行为不变（固定头、before/hash、完整检查、原子写、修正计数） |
| `scripts/read_input.py` | 新增 `--tables a,b,c`：从工作包或固定上下文按名称批量输出这些数据集的列（紧凑一行一列），stdout ≤8 KiB，超出时分页提示；保留 `--pointer`、`--start/--end` |
| `scripts/show_example.py` | 位置参数接受多个 target_kind；新增默认 `--no-deps` 行为（只输出示例本身，依赖用一行说明），`--with-deps` 时附带；CI 仍用带依赖的完整示例校验 |
| `scripts/offline_budget.py` | 增加“第一步（计划）”与“第二步（抽取）”两条路线的首轮预算：计划 ≤14 KB，抽取 ≤22 KB |

### 5.3 平台改动

1. **工作包**（`services/modeling_input.py`）：增加 `scenario_facts`：`draft_empty`、相对基线新增的材料 id、相对基线新增的已登记表；只保留最小索引——表目录（表名、显示名、注释、列数，不含列）与已有元素索引（类型、英文标识、名称、id）。增加 `workflow_dir: "modeling/"`。
2. **待确认时保存计划**（`services/model_result.py`）：结果为 awaiting_reply 时，除 needs-input 标记外下载 `modeling/plan.md`、`modeling/entities.json`（或 issues.json），存入该会话的运行清单；下载失败不影响 awaiting_reply，仅记录。
3. **第二次运行**（`api/agent_conversation.py`）：若上一次运行为 awaiting_reply 且有保存的计划，本次工作包加 `prior_plan`（保存的文件内容，原样）与 `user_reply`（本次用户消息原文），并把文件重新上传到 `modeling/`（DataAgent 工作区可能已清理）。
4. **修复与续跑**：修复提示增加“在 modeling/parts/ 已有片段上修改，只改报错指向的片段”；修复工作包携带同一 `workflow_dir`。
5. **失败诊断**：运行失败时尝试下载 `modeling/plan.md`、`notes.md` 与 `parts/` 文件清单（不下载大文件全文），作为诊断附在运行记录，构建页失败说明显示“已完成到第几阶段”。
6. 每轮提示只增加一个动态事实：`工作流：modeling/`；场景由 Agent 判断，不在提示中预设。

### 5.4 技能

- SKILL.md 执行清单改为六阶段：①计划 ②确认 ③抽取 ④合并 ⑤修正 ⑥输出；写明各阶段读取的方法章节、可跳过的情形（小改动、用户要求一次做完、无新增实体）、每阶段写哪些文件。
- methodology 增加四类场景各自的计划产物与确认方式：全量（实体清单）、增量（变化清单，有新增实体才确认）、优化（问题清单，用户选择条目，只写 update/delete，连带处理依赖）、小改动（跳过计划）。
- needs-input 正例增加“确认实体清单”与“选择要修复的问题”两种协议例；回答中的表格格式写在交付约定里。
- 片段命名、合并顺序、notes 的更新时机写在 SKILL；不复制到每轮提示。

### 5.5 测试

| 层 | 用例 |
|---|---|
| 脚本 | init 幂等；check_part 跨片段引用不报错、片段内悬空引用报错；prepare 目录合并顺序与多文件等价；read_input --tables 批量与分页；show_example 多类型与 --no-deps，输出仍可被完整示例校验覆盖 |
| 平台 | awaiting_reply 时保存计划文件、下载失败仍为 awaiting_reply；第二次运行工作包含 prior_plan 与 user_reply 并重新上传；修复工作包保留 workflow_dir；失败诊断只取清单与小文件 |
| 场景快照 | 全量首轮（空草稿）、增量（新增材料与表）、优化（无新输入）、小改动的工作包与提示快照 |
| 预算 | 计划路线 ≤14 KB、抽取路线 ≤22 KB；第二步轮数预估：读取 2、写片段 3、合并 1、修正 ≤2、说明 1 |

统一验证命令同 §3；涉及构建页失败说明的文字改动需补对应前端单测，无新页面。

### 5.6 真实验收（与 token、harness、数据集、值类型合并）

星河零售：第一次运行（全量，期望只给实体表格并写 needs-input）→ 对话回复确认（例如去掉一个实体、改一个名称）→ 第二次运行生成全部提案，退款率走“表达式数据集 + 单数据集比率”，会员等级走值类型。分别记录两次运行的轮数与 I/U/O，合计对照 token 设计目标；不自动重跑。
