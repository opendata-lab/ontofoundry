---
name: ontology-discovery
description: 从文档、表结构发现实体类型、属性、关系、数据集、映射、指标、规则，判断新增还是复用已有定义，提出供审阅的增量提案。
---
# 建模执行清单

技能目录 `.claude/skills/ontology-discovery`；脚本用 `"$DATAAGENT_PYTHON_BIN" .claude/skills/ontology-discovery/scripts/<脚本>`。文件写 modeling/。stdout≤8 KiB，同回合多条调用，不拼接输出。

小改动／补齐已有实体／无新增实体先走③增量；否则有 prior_plan_file 走③抽取，新增实体或优化走①②；一次完成列清单后③。

取得工作包后运行 `init_workflow.py --work-pack <工作包>`（有前轮计划加 `--prior-plan <prior_plan_file>`），批量读齐：前轮计划、材料用 `read_input.py <材料>` 保留行号、列用 `read_input.py <tables_file> --tables <全部相关key，逗号分隔>`。表结构只读一次，超限分组调用。

①计划：读 methodology.md 判断场景，写 plan.md 首行；全量／增量写 entities.json，优化写 issues.json。只读材料与表目录，不读列／原则／抽取包／Schema，不检查。模板：[实体](references/examples/protocol/entities.json)、[问题](references/examples/protocol/issues.json)。
②确认：表格列类型、标识、依据、对应表、说明与关系；优化列问题／改法／影响。按[确认](references/examples/protocol/needs-input-entities.json)或[选择](references/examples/protocol/needs-input-issues.json)模板写 needs_input_file 后结束，不写提案。
③增量／小改动：先 `show_element.py --work-pack <工作包> <英文标识或id>...` 取修改目标与引用元素的定义／hash／引用者；歧义按候选精确写法重查，超限按返回参数分页。不读 context_file 全文、脚本源码或 Schema。同回合读 principles.md，运行 `show_example.py --incremental-guide`、`--values`、`--part update`；名称／说明修改或删除加 `--part edit`。用已有 UUID 引用，仅本批 create 用 client_ref；update 复制完整定义去 id 后修改，不写 before/hash。写 modeling/parts/01-update.json，T3–4 写首片段，即 `check_part.py --work-pack <工作包> modeling/parts/01-update.json`，再④。只写变化；删除先查依赖。
③抽取：输入齐后同回合读 principles.md，执行 `show_example.py --guide`、`--values`、`--part 01`、`--part 02`、`--part 03`、`--part 04`、`--part 05`。不按业务选包，不回读 methodology/core-model/抽取方法／目录。T3–4 修订 plan.md、entities.json 或 issues.json、notes.md 并写 01；指标不阻塞类型落盘。按 01-types、02-links、03-datasets、04-metrics-rules、05-facts 写 modeling/parts/<名称>.json 裸数组，无事实写 []。每写一两个即 `check_part.py --work-pack <工作包> 01 02`。写后只看摘要。notes≤2 KB，压缩后先读 plan/notes。
④合并：`prepare_result.py --schema <schema_file> --context <context_file> --output <result_file> modeling/parts/`；检查通过写入，自动填 before/hash。
⑤修正：最多两轮，共用 execution；只改报错片段再合并，加 --repair（平台已计次的新上下文首次不加）；耗尽保留诊断，不删计数。
⑥输出：中文说明修改、依据和未交付项。未同步表无列只提有依据的语义及空列表 Dataset，不猜映射／SQL／指标；提示“先在数据管理同步该表，再发起补齐”。技术失败不冒充业务提问或成功。

Schema 只给检查器。未覆盖按报错命令或 `<target_kind> --operation create|update|delete` 定点查正例；无覆盖则说明缺项。复杂继承读[模式](references/modeling-patterns.md)，交换读[Ossie](references/reading-ossie.md)，转换读[补全](references/import-completion.md)。缺输入才用工作包只读 MCP，不输出 headers。大材料用 --start/--end。
