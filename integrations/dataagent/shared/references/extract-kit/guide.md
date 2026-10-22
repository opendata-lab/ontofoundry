# 固定抽取写法包

分别调用 `show_example.py --guide`、`--values`、`--part 01` 至 `--part 05`，同回合可并行，不合并 stdout；每次 ≤8 KiB。01–05 为引用闭合的裸 items 数组。澄页图书馆仅示范写法，定义取本轮输入。prepare_result 填固定头、before/hash：定义取 draft/element_hashes，实例按 target_kind+target_id 取 instance_baseline 的 element/hash，不重算。client_ref 引用本批；fields 键为属性英文标识；source_id 为映射局部字面量。

- 01：单标识 required/unique/identifier；复合分量 required/identifier、不 unique。材料或表结构明确给出名称属性才设 title_property_id；可不设，按标识显示，不从字段名猜。值类型含基础类型及独立约束；属性用 value_type_id 引用，基础类型一致。必填不按 nullable 推导，值域不含必填；矛盾交人工审阅。
- 02：direct 两组属性逐对对应；many_to_one 多端指向至多一端，反向不另建关系。可空引用不加 required；无 join_type。
- 03：普通／复合键映射，key_columns 按物理次序。表数据集填 connection_id、表位置和已知列；未同步则列为空，不猜映射／SQL／指标，提示“先在数据管理同步该表，再发起补齐”。押金、赔偿 UNION ALL 各带日期，避免多次赔偿重复累计押金；列声明不代表探测成功。
- 04：simple count 计行、不填 measure；其他聚合引用列。filters 各项 AND；eq/ne/gt/ge/lt/le 单值，in/not_in 列表，between 两值，is_null/not_null 为 []。time_field 引用数据集列。ratio 分量为同 Dataset 的数值 simple，各留过滤和时间；零分母 NULL。跨关系约束用“对象.关系.属性”，特殊字符标识加双引号。规则非 SQL，不执行筛选。
- 证据换成本轮 id/hash、原文位置与原文。05 的 [] 表示无具体实例；有则定点查 material_object／material_link 正例，不把假设当实例。

取值查 --values 并对照契约。增量先查 show_element，再读 `--incremental-guide`、`--part update`；改名称／说明或删除加 `--part edit`。高级写法定点查；未覆盖则说明缺项，不遍历或读取 Schema。
