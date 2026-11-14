# 固定抽取写法包

全量抽取用 `show_example.py --extract 1`、`--extract 2` 两次读完原则、本说明、取值速查和 01–05（同回合可并行，每页低于 DataAgent 16 KB 的直接显示上限）；单独的 `--guide`、`--values`、`--part NN` 只用于定点补查，每次 ≤8 KiB。01–05 为引用闭合的裸 items 数组。澄页图书馆仅示范写法，定义取本轮输入。结果只写 items；before、hash 与 material_sha256 由平台按本轮上下文补齐，片段不写。client_ref 引用本批；fields 键为属性英文标识；source_id 为映射局部字面量。

- 01：单标识 required/unique/identifier；复合分量 required/identifier、不 unique。材料或表结构明确给出名称属性（如注释为“名称”的列）就设 title_property_id；没有名称属性可不设，按标识显示，不从字段名猜。值类型含基础类型及独立约束；属性用 value_type_id 引用，基础类型一致。必填不按 nullable 推导，值域不含必填；矛盾交人工审阅。
- 02：direct 两组属性逐对对应；many_to_one 多端指向至多一端，反向不另建关系。可空引用不加 required；无 join_type。direct 的 target_property_ids 及映射表的 source_key/target_key 必须是端点的唯一属性（unique）或完整标识；关联列不唯一时不写 data_join，在说明里列为候选。
- 03：普通／复合键映射，key_columns 按物理次序。映射不写 name、display_name、description、evidence。表数据集只用已同步的关联表，填 connection_id、表位置和列；未同步的表不提数据集，提示“先在数据管理同步该表，再发起补齐”。押金、赔偿 UNION ALL 各带日期，避免多次赔偿重复累计押金；列声明不代表探测成功。
- 04：simple count 计行、不填 measure；其他聚合引用列。filters 各项 AND；eq/ne/gt/ge/lt/le 单值，in/not_in 列表，between 两值，is_null/not_null 为 []。time_field 引用数据集列。ratio 分量为同 Dataset 的数值 simple，各留过滤和时间；零分母 NULL。跨关系约束用“对象.关系.属性”，特殊字符标识加双引号。规则非 SQL，不执行筛选。值类型规则只引用该值类型自己的英文标识（如值类型 loan_phase 写 loan_phase IN (...)，不写属性名）；属性与关系规则从归属对象出发。规则只写可校验的表达式，口径说明和注意事项写进 description 或回答。
- 证据写本轮材料 id、原文位置与原文；material_sha256 由平台补，不要自己填。05 的 [] 表示无具体实例；有则定点查 material_object／material_link 正例，不把假设当实例。

取值查 --values 并对照契约。增量先查 show_element，再读 `--incremental-guide`、`--part update`；改名称／说明或删除加 `--part edit`。高级写法定点查；未覆盖则说明缺项，不遍历或读取 Schema。
