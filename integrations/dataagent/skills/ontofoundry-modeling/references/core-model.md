# core-1 模型

草稿九集合：object_types、properties、link_types、rules、metrics、datasets、mappings、material_objects、material_links。
各集合是 UUID 元素。字段以本轮 JSON Schema 为唯一标准，禁止额外字段。

对象单父 extends 为 UUID/null；synonyms 是业务别名，description 是业务说明。
属性归 owner_type_id，七种 value_kind；identifier 与 unique 分开，复合标识按属性 UUID 排序。
关系只有 source_type_id/target_type_id 两端，三种基数；direct 按两组属性 UUID 配对，mapping_table 的两端列组各自匹配键宽。
规则只归对象、属性或关系；约束不等于成员条件。derived_by 多分支 OR、每分支条件 AND；逐层限父成员。

Dataset 扁平登记 name/dialect/schema_name/table_name/columns/snapshot_date_column；不填连接凭据、连接别名、采集时间。
Mapping 用 sources 引用 Dataset，独立绑定主来源必须叫 main，与数组顺序无关。普通附表是 LEFT JOIN；成员来源取交集。
字段绑定可选 column 或同行 expression；不能引用其他计算属性或跨对象。shared_parent 只存本地新增定义。
inherited_link_bindings 输入是 `{link_type_id, data_join}` 条目数组，关系引用可用 client_ref。

simple 指标只统计自己 Dataset；count 是行数，不给 measure；其余聚合给列。
ratio 只给 numerator_id/denominator_id，两个都是同数据集数值 simple，不填派生的数据集/类型/时间字段。
expression 指标保留同数据集完整聚合算法，不擅自改写 NULL/去重/过滤语义。指标与对象成员独立。
时间范围半开；快照各数据集独立选择全表末日，不能先按指标过滤缩小日期。

文档事实只存 id/type_id/values/evidence，无独立 name/display_text。缺编号合法；0/false 有值。
同编号事实按 UUID 独立，不自动合并；如用户明确选择，更新已有事实并追加证据，保留证据 UUID。
