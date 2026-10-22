# 实例抽取

概念已由用户确认；本步骤只把材料中的具体事物和具体关系落为这些概念的实例。

1. 取得工作包，运行 `init_workflow.py --work-pack <工作包>`，有前轮计划加 `--prior-plan <prior_plan_file>`。用 `read_input.py <材料>` 保留原行号，按范围完整阅读材料；用 `show_element.py --work-pack <工作包> <英文标识或id>...` 定点取得具体类型、有效属性、关系端点及已有实例。歧义按候选重查，超限分页，不读 context_file 全文或 Schema。
2. 读 [实例方法](../extract-facts.md)、[原则](../principles.md)，同回合执行 `show_example.py --values`、`show_example.py --part 05`。区分定义与实例：规则“员工需有主管”不是具体关系，“小岚向小舟汇报”可形成两个文档实例和一个关系实例。示例、假设、否定、计划不自动成为已成立的实例。对外称“文档实例”“关系实例”；脚本与契约仍用 material_object、material_link、values、evidence 等原字段。
3. 只引用已确认的类型和属性，UUID 引用已有定义，同批新定义用 client_ref。身份不明或同号多记录时保留证据并请用户确认，不擅自合并或更新；只有明确指向 UUID 才更新，保留已有人工证据。原文金额未知不能补值，0 与 false 是真实值。证据使用原材料 id/hash/行号/quote，不从聊天回答编造。
4. 写 `modeling/parts/05-facts.json` 裸数组，无实例写 []，运行 `check_part.py --work-pack <工作包> modeling/parts/05-facts.json`。只写变化，及时检查，notes≤2 KB，压缩后先读 plan/notes。
5. 同一运行组合 ontology-discovery 时，共享 modeling/、execution 和修正计数；定义片段 01–04 与实例片段 05 合并为一个结果文件，不分别提交、不覆盖其他 Skill 片段。发现缺少业务概念时，先按 ontology-discovery 计划步骤列概念并等待确认，确认前不写定义或实例提案。单独抽取时只交本次片段。output-schema.json 是本技能的实例子集说明；检查器始终用工作包 schema_file（平台完整提案契约），允许组合输出。

匹配、授权和确定性判级归平台工具。新建实例前对实体提及调用 `resolve_entity`：document 来源命中可按实例基线提出更新已有实例，database 来源只作说明；是否同一实体由人工审阅。Schema 只给检查器，未覆盖按报错命令定点查正例。业务数据库行不自动写成文档实例，不因名称近似认定同一身份。

完成后读[收尾](finish.md)。
