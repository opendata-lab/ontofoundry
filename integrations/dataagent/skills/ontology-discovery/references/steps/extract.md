# 抽取：按已确认的范围展开

清单已获批准（modeling/entities.json），不再改范围；“已有”概念用 show_element 取 id，只为“新增”写 create；清单外的新概念列为未交付项。

1. 读 plan.md、entities.json、材料（read_input.py 保留行号）；看列时一次 `--describe-tables t1,t3,…`。同回合执行 `show_example.py --extract 1`、`--extract 2`。
2. 在 entities.json 每个有表的实体上补 `table`、`title_property`，按需 `exclude_columns`、`boolean_columns`、`properties`（只写要改的列）；顶层 `value_types` 只收取值候选里确属统一值域的列。运行 `expand_tables.py --work-pack <工作包>` 生成并检查 01-types、03-datasets；报错改 entities.json 重跑，不手改这两个文件。无表实体和额外属性写 01b-types.json，查询、关联表数据集和多表映射写 03b-datasets.json。
3. 写 02-links（关联候选只是提示，名称、读法、基数自己定）、04-metrics-rules、05-facts（无实例写 []；实例方法在 `entity-extraction/references/extract-facts.md`，不在 ontology-discovery）。精力留给关系、指标、规则，不写生成脚本或 python 自检。
4. `check_part.py --work-pack <工作包>` 一次检查其余片段；含 04 时列出未被引用的材料口径行和未兑现的计划：补提案，或在回答里说明为何不建。notes 只记要点。
5. 未覆盖写法按报错命令或 `<target_kind> --operation create|update|delete` 定点查。复杂继承读[模式](../modeling-patterns.md)，交换读[Ossie](../reading-ossie.md)，转换读[补全](../import-completion.md)。

完成后读[收尾](finish.md)。
