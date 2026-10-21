# 固定抽取写法包

分别调用 `show_example.py --guide`、`--values`、`--part 01` 至 `--part 05`，可在同一工具回合并行，不能拼成一个 stdout。各次 ≤8 KiB。01–05 是引用闭合的裸 items 数组；澄页图书馆仅示范写法，业务定义须来自本轮输入。固定头、before/hash 由 prepare_result 填入。client_ref 是本批引用，fields 的键是属性英文标识，source_id 是映射局部字面量。

- 01：单属性标识 required/unique/identifier；复合分量 required/identifier，各自不 unique。值类型定义基础类型与独立约束，属性用 value_type_id 引用且基础类型一致。业务必填不从数据库 nullable 推导。值域不含必填；矛盾仍须人工审阅。
- 02：direct 两组属性逐对对应；many_to_one 由多端指向至多一端，反向读法不另建关系。可空引用不加 required，不添加不存在的 join_type。
- 03：普通与复合键映射，key_columns 保留物理次序。表数据集填 connection_id、表位置及已知列；未同步无列时用空列表，不猜映射／SQL／指标，提示“先在数据管理同步该表，再发起补齐”。押金、赔偿事件 UNION ALL 各带日期，避免多条赔偿重复累计押金。列声明不代表真实探测成功。
- 04：simple count 计行，不填 measure；其他聚合引用列。filters 各项 AND；eq/ne/gt/ge/lt/le 单值，in/not_in 列表，between 两值，is_null/not_null 为 []。time_field 引用数据集列。ratio 分量须同 Dataset 的数值 simple，各自保留过滤和时间；零分母 NULL。跨关系约束路径为“对象.关系.属性”，特殊字符标识用双引号。规则不是 SQL，不执行筛选。
- 材料证据须替换为本轮确定的 id/hash、原文位置及原文。05 的 [] 表示没有具体事实；有事实时定点查询 material_object／material_link 正例，不把假设当事实。

取值由 --values 提供并对照契约。增量先查 show_element，再读 `--incremental-guide` 与 `--part update`；名称／说明或删除加 `--part edit`。高级写法定点查询；仍未覆盖则说明缺项，不读取或遍历 Schema。
