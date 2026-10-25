# 增量：不新增概念的修改

改名、补指标或映射、补已有概念的实例等不扩大范围，直接写变化，不需确认。若发现要新增概念，停下改读[计划](plan.md)。

1. 直接 `show_element.py --work-pack <工作包> <名称>...` 取目标与引用元素：中文名称、英文标识、实体.属性、实例取值（`类型:取值`）或 id 都可精确查；歧义按候选重查。不读工作包索引页、context_file 全文、脚本源码或 Schema。
2. 只运行 `show_example.py --incremental-guide`、`--part update`；改名／说明或删除加 `--part edit`；实例查 `show_example.py material_object --operation update`（新实例 `create`）。不够时才定点读一份方法：[类型](../extract-types.md)、[映射](../extract-mappings.md)、[指标规则](../extract-metrics-rules.md)。不读原则、示例目录，不加载实例抽取技能。
3. 用已有 UUID 引用，本批 create 用 client_ref；update 复制完整定义去 id 后修改，不写 before/hash；证据写材料 id、行号与原文，sha256 由脚本补。变化写 modeling/parts/01-update.json（实例写 05-facts.json），`check_part.py --work-pack <工作包> modeling/parts/01-update.json modeling/parts/05-facts.json` 后合并。删除先查依赖。

完成后读[收尾](finish.md)。
