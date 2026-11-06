# 抽取：按已确认的范围展开

概念清单已获批准（modeling/entities.json）。按清单展开属性、关系、数据集、映射、指标、规则和实例，不再改范围；“已有”概念用 show_element 取 id 引用，只为“新增”写 create；清单外的新概念写进回答的未交付项，留待下次确认。

1. 读齐 modeling/plan.md 与 entities.json、材料（`read_input.py <材料>` 保留行号）、列（计划候选用 `read_input.py <tables_file> --describe-tables t1,t3`，续读照提示；不全量读表）。
2. 读 principles.md，执行 `show_example.py --guide`、`--values`、`--part 01` 至 `--part 05`。不按业务选包；已读内容不重读。01–04 已含值类型、规则、查询数据集。
3. 修订计划与笔记，写 01。按 01-types、02-links、03-datasets、04-metrics-rules、05-facts 写 modeling/parts/<名称>.json 裸数组，无实例写 []；实例方法读 `entity-extraction/references/extract-facts.md`（不在 ontology-discovery）；清单 examples 的具体事物在 05 作文档实例。每一两份即 `check_part.py --work-pack <工作包> 01 02`，只看摘要。notes≤2 KB，压缩后先读 plan/notes。
4. 未覆盖写法按报错命令或 `<target_kind> --operation create|update|delete` 定点查正例，无覆盖则说明缺项。复杂继承读[模式](../modeling-patterns.md)，交换读[Ossie](../reading-ossie.md)，转换读[补全](../import-completion.md)。MCP 访问文件只给 prepare_result，不读不打印。文本按 --start/--end 续页；JSON／CSV 先 --outline，再 --pointer／--rows／--query 定点读。Schema 给检查器。

完成后读[收尾](finish.md)。
