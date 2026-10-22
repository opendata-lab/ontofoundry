# 增量：不新增概念的修改

改名、补指标或映射、补已有概念的实例等不扩大范围，直接写变化，不需确认。若发现要新增概念，停下改读[计划](plan.md)。

1. 先 `show_element.py --work-pack <工作包> <英文标识或id>...` 取目标与引用元素的定义／hash／引用者，歧义按候选重查，超限分页。不读 context_file 全文、脚本源码或 Schema。
2. 同回合读 principles.md，运行 `show_example.py --incremental-guide`、`--values`、`--part update`；名称／说明修改或删除加 `--part edit`。按任务定点读方法：类型或英文改名读[类型](../extract-types.md)，表与绑定读[表](../extract-tables.md)、[映射](../extract-mappings.md)，聚合与约束读[指标规则](../extract-metrics-rules.md)，文档实例用 entity-extraction。
3. 用已有 UUID 引用，仅本批 create 用 client_ref；update 复制完整定义去 id 后修改，不写 before/hash。T3–4 写 modeling/parts/01-update.json 并 `check_part.py --work-pack <工作包> modeling/parts/01-update.json`。只写变化；删除先查依赖。仅改中文名称读完整目标及 update 正例。

完成后读[收尾](finish.md)。
