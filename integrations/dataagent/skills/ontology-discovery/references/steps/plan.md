# 计划：只定范围

只定概念，细节留到抽取。

1. 读材料保留行号；JSON／CSV 先 `read_input.py <材料> --outline --ref m1`，再 --pointer、--rows 或 --query 定点读。表看 table_scope：≤30 张用 `read_input.py <tables_file> --search-tables` 浏览，否则用需求里的业务词做 1–2 次 `--search-tables 关键词`；候选 t# 写入 plan.md，要看列才能取舍时只对候选 `--describe-tables`。
2. 区分概念与实例：概念是一类东西；具名的具体事物（产品、系统、人、单据）是它的实例。材料列出《晨读》《古籍考》→ 概念“期刊”，二者记为例子，抽取时作为实例提出。单值归属性，跨行统计归指标。
3. 不定关系、属性，不读原则、Schema，不运行 show_example.py，不检查；第 3 轮前定稿。
4. 要用户取舍的点（粒度、口径等）先用 AskUserQuestion 提问，每题 2–4 个选项，标一个推荐；等回答后再写计划，计划里不留待确认问题。
5. 计划模式下调用 ExitPlanMode 提交：首行 `# 标题`，写场景（全量或增量）和概念表（名称／英文标识、说明、依据：材料行号或表、例子；增量标新增／已有）。要求调整就改后重新提交，再次获批准前不抽取。
6. 获批准后（或不在计划模式时直接）照概念清单模板写 modeling/entities.json，场景写 plan.md 首行，依据记入 notes.md，接着读[抽取](extract.md)。
