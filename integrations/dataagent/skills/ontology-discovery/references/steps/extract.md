# 抽取：按已确认的范围展开

用户已确认概念清单（prior_plan_file）。按清单展开属性、关系、数据集、映射、指标、规则和实例，不再改范围；清单外的新概念写进回答的未交付项，留待下次确认。

1. 初始化已带 --prior-plan 恢复前轮计划；批量读齐 modeling/plan.md 与 entities.json、材料（`read_input.py <材料>` 保留行号）、列（照初始化打印的分批读表命令，每批一次）。
2. 同回合读 principles.md，分别执行 `show_example.py --guide`、`--values`、`--part 01` 至 `--part 05`。不按业务选包；已读的示例、表结构和计划步骤不重读。
3. T3–4 修订 plan／entities 或 issues／notes 并写 01；指标不阻塞类型落盘。按 01-types、02-links、03-datasets、04-metrics-rules、05-facts 写 modeling/parts/<名称>.json 裸数组，无实例写 []；清单 examples 中的具体事物在 05 作为文档实例提出。每写一两个即 `check_part.py --work-pack <工作包> 01 02`，只看摘要。notes≤2 KB，压缩后先读 plan/notes。
4. 未覆盖写法按报错命令或 `<target_kind> --operation create|update|delete` 定点查正例，无覆盖则说明缺项。复杂继承读[模式](../modeling-patterns.md)，交换读[Ossie](../reading-ossie.md)，转换读[补全](../import-completion.md)。缺输入才用工作包只读 MCP，不输出 headers。大材料用 --start/--end。Schema 只给检查器。

完成后读[收尾](finish.md)。
