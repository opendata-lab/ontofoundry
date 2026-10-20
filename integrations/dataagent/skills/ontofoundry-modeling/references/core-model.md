# core-1 模型

草稿九集合：object_types、properties、link_types、rules、metrics、datasets、mappings、material_objects、material_links。
各集合是 UUID 元素。字段以本轮 JSON Schema 为唯一标准，禁止额外字段。

对象单父 extends 为 UUID/null；synonyms 是业务别名，description 是业务说明。
属性归 owner_type_id，七种 value_kind；identifier 与 unique 分开，复合标识按属性 UUID 排序。
关系只有 source_type_id/target_type_id 两端，三种基数；可选 source_role_name/target_role_name 分别描述两端业务角色（例如来源下属、目标主管），不替代完整 verbalizes 关系含义；name 是所属对象内唯一 ASCII 关系标识，不填 technical_name/inverse_name，不猜测角色名。正向展示目标角色，反向展示来源角色；direct 按两组属性 UUID 配对，mapping_table 的两端列组各自匹配键宽。
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

关系示例：name=reports_to，来源角色下属、目标角色主管，verbalizes=["{source}汇报给{target}", "{target}管理{source}"]。角色名可空，不从旧词语猜测；无读法时给空数组。每条读法必须包含两个端点，不使用未知占位符。


## 标识、标题与实例值

单属性业务标识必须同时设 identifier=true、required=true、unique=true。例如“星港客户”的 customer_no 唯一标识一个客户。复合标识则把各分量设 identifier=true、required=true，但分量不必单独 unique：虚构门店中 (region_no, store_no) 联合唯一，store_no 在不同区域可重复；只有业务保证单分量也唯一时才设 unique=true。标识分量顺序由属性 UUID 排序推导，不用物理键数组顺序替代。

title_property_id 指向本对象或继承的属性 UUID，也可引用同批新增属性的 client_ref。例如客户指定 customer_name 作标题；不设置时继承祖先标题属性，再按完整业务标识、证据引文、UUID 逐级回退。标题只在读取时推导，不向文档对象添加 name/display_text。

material_objects.values 的键是有效属性的 technical_name，不是属性 UUID、中文名称或 client_ref。例如属性 technical_name=customer_name 时写 values={"customer_name":"小岚"}。0/false 都有值，缺少完整标识仍可保存文档事实；关系事实最小提案例子见建模模式。
