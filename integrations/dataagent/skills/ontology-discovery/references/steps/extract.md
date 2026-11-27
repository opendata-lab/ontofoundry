# 抽取：按已确认的范围展开

计划已获批准（modeling/plan.md），不再改范围；“已有”概念用 show_element 取 id，只为“新增”写 create；清单外的新概念列为未交付项。

1. 读 plan.md；材料读法同计划，`modeling/tmp/` 有上轮整理的结果就直接用；看列一次 `--describe-tables t1,t3,…`。同回合分两次调用 `show_example.py --extract 1`、`--extract 2`，勿用 `&&`。
2. 按计划和模板写 modeling/entities.json（已有则接着改）：有表的实体补 `table`、`title_property`，每日全量快照写 `snapshot_date_column`，按需 `exclude_columns`、`boolean_columns`、`properties`（只写要改的列）；顶层 `value_types` 只收统一值域的取值候选，`links` 每条关系一行（见模板）。清单一定就运行 `expand_tables.py --work-pack <工作包>` 生成 01、02、03；报错改 entities.json 重跑，不手改生成的文件。无表、不合清单的实体和额外属性写 01b，端点无表等特殊关系写 02b，查询数据集和多表映射写 03b。写完一类就落盘，notes.md 记已完成／待补。
3. 写 04-metrics-rules、05-facts（无实例写 []；实例方法在 `entity-extraction/references/extract-facts.md`，不在 ontology-discovery）。精力留给关系、指标、规则，不写生成或自检脚本。
4. 片段写齐后合并提交，平台一次列出全部问题。
5. 未覆盖写法按报错里的命令定点查，或 `--variant <名称>`。复杂继承读[模式](../modeling-patterns.md)，交换读[Ossie](../reading-ossie.md)，转换读[补全](../import-completion.md)。

完成后读[收尾](finish.md)。
