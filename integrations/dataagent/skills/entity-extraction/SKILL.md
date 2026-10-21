---
name: entity-extraction
description: 按已有本体约束从文档抽取文档实例、属性值和关系实例，核对身份、引用与原文证据；材料包含具体对象或具体关系陈述时使用，可与 ontology-discovery 在同一运行中组合。
---
# 实例抽取执行清单

技能目录 `.claude/skills/entity-extraction`；脚本用 `"$DATAAGENT_PYTHON_BIN" .claude/skills/entity-extraction/scripts/<脚本>`。stdout≤8 KiB，同回合多条调用，不拼接输出。

1. 取得工作包，运行 `init_workflow.py --work-pack <工作包>`，有前轮计划加 `--prior-plan <prior_plan_file>`。用 `read_input.py <材料>` 保留原行号，按范围完整阅读材料；用 `show_element.py --work-pack <工作包> <英文标识或id>...` 定点取得具体类型、有效属性、关系端点及已有实例。歧义按候选重查，超限分页，不读 context_file 全文或 Schema。
2. 读 [实例方法](references/extract-facts.md)、[原则](references/principles.md)，同回合执行 `show_example.py --values`、`show_example.py --part 05`。区分定义与实例：规则“员工需有主管”不是具体关系，“小岚向小舟汇报”可形成两个文档实例和一个关系实例。示例、假设、否定、计划不自动成为已成立的实例。对外称“文档实例”“关系实例”；脚本与契约仍用 material_object、material_link、values、evidence 等原字段。
3. 只引用已确认的类型和属性，UUID 引用已有定义，同批新定义用 client_ref。身份不明或同号多记录时保留证据并请用户确认，不擅自合并或更新；只有明确指向 UUID 才更新，保留已有人工证据。原文金额未知不能补值，0 与 false 是真实值。证据使用原材料 id/hash/行号/quote，不从聊天回答编造。
4. 写 `modeling/parts/05-facts.json` 裸数组，无实例写 []，运行 `check_part.py --work-pack <工作包> modeling/parts/05-facts.json`。只写变化，及时检查，notes≤2 KB，压缩后先读 plan/notes。
5. 同一运行组合 ontology-discovery 时，共享 modeling/、execution 和修正计数；定义片段 01–04 与实例片段 05 合并为一个结果文件，不分别提交、不覆盖其他 Skill 片段。发现缺少业务概念时按任务加载 ontology-discovery 提出定义提案与相关实例提案，交人工审阅。单独抽取时只交本次片段。output-schema.json 是本技能的实例子集说明；检查器始终用工作包 schema_file（平台完整提案契约），允许组合输出。
6. `prepare_result.py --schema <schema_file> --context <context_file> --output <result_file> modeling/parts/`，定义按 draft/element_hashes、实例按 instance_baseline 自动补 before/hash，通过才写入。最多两轮修正，共用 execution；只改报错片段再合并，加 --repair（平台已计次的新上下文首次不加），不删除计数。中文说明实例、证据、歧义与未交付项；技术失败不冒充业务提问或成功。

匹配、授权和确定性判级归平台工具；当前仅使用已上线的读取工具，不假设实例消歧服务已可用。Schema 只给检查器，未覆盖按报错命令定点查正例。业务数据库行不自动写成文档实例，不因名称近似认定同一身份。
