---
name: ontofoundry-modeling
description: 根据材料和已有模型提出 core-1 增量提案，供用户审阅。
---
# 建模执行清单

技能目录 `.claude/skills/ontofoundry-modeling`，脚本用 `"$DATAAGENT_PYTHON_BIN" .claude/skills/ontofoundry-modeling/scripts/<脚本>`。不搜索环境或列目录；中间文件写 modeling/。每次 stdout≤8 KiB，同一工具回合发出多条有界调用，不把输出拼成一条。

工作包有 prior_plan_file → 抽取轮；否则新增实体或优化 → ①②；小改动、无新增实体或用户要求一次完成 → 内部列清单后③。

抽取轮取得工作包后下一工具回合：运行 `init_workflow.py --work-pack <工作包>`（有前轮计划加 `--prior-plan <prior_plan_file>`），同时批量读齐：前轮计划、材料用 `read_input.py <材料>` 保留原行号、表结构用 `read_input.py <tables_file> --tables <工作包全部相关key，逗号分隔>`。表结构只读一次；超限按原行号／表 key 分组，同回合多次调用。context_file 只给检查器；修改／删除才按 pointer 读完整目标及 element_hashes。

①计划：读 methodology.md 判断场景，写 plan.md 首行；全量／增量写 entities.json，优化写 issues.json。计划轮只读材料与表目录，不读列、原则、抽取示例或 Schema，不跑检查器。协议模板可读：[实体](references/examples/protocol/entities.json)、[问题](references/examples/protocol/issues.json)。
②确认：回答表格（实体类型、英文标识、依据行号或表、对应表、说明；优化列问题／改法／影响），附拟建关系概要；按[确认模板](references/examples/protocol/needs-input-entities.json)或[选择模板](references/examples/protocol/needs-input-issues.json)写 needs_input_file 后结束，不写提案。协议模板用于流程文件，区别于③的抽取示例。
③抽取：输入齐后同一工具回合分别读 principles.md，并执行 `show_example.py --guide`、`--values`、`--part 01`、`--part 02`、`--part 03`、`--part 04`、`--part 05`。固定包不按材料名称选择写法。不回读 methodology/core-model/抽取方法或示例目录。最迟 T3–4：同一步按用户回复修订 plan.md、entities.json 或 issues.json、notes.md，并写首个 01 片段；复杂指标未定不阻塞类型落盘。按 01-types、02-links、03-datasets、04-metrics-rules、05-facts 写 modeling/parts/<名称>.json 裸数组，无事实写 []。每写一两个即 `check_part.py --work-pack <工作包> 01 02`（编号即片段）；写后不回显整份 JSON，只看检查摘要。notes≤2 KB，压缩后先读 plan/notes。增量只写变化；优化只 update/delete 并处理依赖。
④合并：`prepare_result.py --schema <schema_file> --context <context_file> --output <result_file> modeling/parts/`，整批检查通过后原子写入。
⑤修正：最多两轮，与平台拒收修复共用 execution；只改报错片段再合并，加 --repair（平台已计次的新上下文首次不加）；耗尽保留诊断，不能删计数。
⑥输出：按原则中文说明修改、依据与未交付项。未同步表无列只提有依据的实体／属性／关系与基于表 Dataset，不猜列，不构造依赖未知列的映射、SQL 或指标；提示“先在数据管理同步该表，再发起补齐”，同步后用一次小改动／增量补齐。技术失败不冒充业务提问或成功。

Schema 只给检查器。未覆盖写法按报错命令或 `<target_kind> --operation create|update|delete` 定点查正例；仍无正例则交付已覆盖的合法范围并说明缺项，不读或遍历 Schema。复杂继承读[模式](references/modeling-patterns.md)，外部交换读[Ossie](references/reading-ossie.md)，转换读[补全](references/import-completion.md)。输入确实不足才用工作包配置的只读 MCP，不输出 headers。大材料用 --start/--end，JSON 用 --pointer。
