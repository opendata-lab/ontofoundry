# 固定抽取写法包

每次分别调用 `show_example.py --guide`、`--values`、`--part 01`、`--part 02`、`--part 03`、`--part 04`、`--part 05`，可在同一工具回合并行，不能拼成一个 stdout。各次均 ≤8 KiB，无需分页。01–05 是裸 items 数组，整套引用闭合，可以依次改写；不是本轮业务答案。固定头、before/hash 由 prepare_result 填入。client_ref 是本批引用，fields 的键是属性英文标识，source_id 是映射局部字面量。

- 01：单属性标识 required/unique/identifier；复合分量 required/identifier，各自不 unique。值类型定义基础类型及独立约束，属性用 value_type_id 引用且基础类型一致。业务必填不从数据库 nullable 推导。值域规则不含必填；平台不证明矛盾，仍须人工审阅。
- 02：direct 的两组属性逐对对应；many_to_one 由多端指向至多一端，反向读法不另建关系。可空引用不加 required，不为保留散客订单添加不存在的 join_type。
- 03：普通与复合键映射，key_columns 保留物理次序。表数据集填 connection_id、表位置与已知列；未同步且无列时用空列数据集，不猜映射／SQL／指标，交付说明列缺项并提示“先在数据管理同步该表，再发起补齐”。表达式数据集 UNION ALL 的销售、退款各带业务日期；不能把订单连接多条退款后重复累计。列声明不代表真实探测成功。
- 04：simple count 计行，不填 measure；其他聚合引用列。filters 各项 AND；eq/ne/gt/ge/lt/le 为单值，in/not_in 为列表，between 为两值，is_null/not_null 为 []。time_field 是数据集列引用。ratio 两分量必须同 Dataset 的数值 simple，各自保留过滤与时间；零分母 NULL。跨关系约束路径为“对象.关系.属性”，特殊字符标识用双引号。规则不是 SQL，不执行筛选。
- 01 的材料证据必须替换为工作包真实 id/hash、原行号及原文，不能生成虚假证据。05 的 [] 表示材料没有具体事实；有事实时定点查询 material_object／material_link 正例，不将说明中的假设或示例当事实。

七种基础类型及其他取值由 --values 提供，CI 对照当前契约；更新／删除及高级写法用 `<target_kind> --operation update|delete` 或检查器给出的确定命令。仍未覆盖则交付已覆盖的合法范围并说明缺项，不读取、搜索或遍历 Schema，不临时自制 Schema 浏览器。
