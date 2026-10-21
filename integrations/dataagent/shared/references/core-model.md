# core-1 语义

## 关系

关系是二元实例联系。many_to_one 从多端指向至多一端；one_to_one 两向唯一；many_to_many 无两向唯一保证。声明不证明实际数据唯一。角色名区分自关联的业务身份，verbalizes 表达同一关系正反完整读法；反向展示无需另造关系。多方实例重化中间对象。direct 按两组属性配对，mapping_table 按端点键宽匹配列组。

## 继承

单父 is-a。父有绑定须覆盖全部子实例，子 shared_parent，逐层限制父成员；虚拟父无映射，以具体子类来源并集读取，身份含具体类型与有序带类型键。只存本地定义并复用继承 UUID。derived_by 分支 OR、分支内条件 AND，再与成员扩展来源交集。覆盖和互斥需业务依据，程序只校验声明与图。

## 标识与属性

定义 UUID、实例 UUID、业务标识、物理键各有用途。单属性标识须必填且唯一；复合分量必填，但各分量不必单独唯一。业务分量顺序按属性 UUID 推导，与物理 key_columns 次序不同。七种值语义为 string、integer、float、decimal、boolean、date、datetime；未知业务类型不默认字符串。

名称 display_name 可重复，name 是稳定英文标识；路径与实例值键使用 name，同义词归 synonyms，description 说明业务含义与边界。title_property_id 指向有效属性；未设则继承祖先标题，再依完整标识、证据引文、UUID 回退，均为读取时推导。

## 来源

Dataset 可基于表／视图或基于表达式的只读 SQL，列不自动变成属性。表来源填连接与表位置；表达式来源只引用已登记表，不把多张业务表 JOIN 后的重复行当原始粒度。Mapping 的 main 决定对象成员，普通附表 LEFT JOIN 补值；成员来源取交集。sources.id 是映射局部字面量，各映射独立。字段按属性 name 绑定 column 或同行 expression，不能聚合、跨对象或引用其他计算属性。shared_parent 沿用父来源，仅写新增定义。无绑定可先保留业务语义，不伪造就绪。

## 指标

simple 聚合单 Dataset 的列，固定条件 AND；count 是行数，排空计数算法用 expression。ratio 引用同 Dataset 的两个数值 simple，各自过滤和时间保留，零分母 NULL。expression 保留单 Dataset 完整聚合算法。逐行百分比是属性，指标无本体归属，与对象成员范围独立。快照声明与业务时间不同；各 Dataset 独立选全表周期末日，日期范围半开。

## 规则

Rule 归具体对象、属性、关系或值类型；值类型只拥有 constraint，属性以 value_type_id 复用值域并保持基础类型一致。约束不删除记录，derivation Rule 是业务派生说明，不执行计算或筛选成员；同行计算归字段绑定，成员定义归 derived_by。

## 实例

实例不属于 core-1：draft/element_hashes 只含定义，实例由 instance_baseline 固定。更新／删除复制其 element/hash（含 revision），不重算旧集合哈希。文档对象的 values 按属性 name；0/false 有值，缺编号可保存。关系实例两端引用对象实例。相同编号不合并 UUID；更新须明确目标，保留人工证据及其 UUID。材料 hash、原行号、quote 可核对，但不证明文字蕴含所提含义。

## 正例索引

写法统一用 `scripts/show_example.py <target_kind>`。完整正例与覆盖索引见 [catalog](examples/catalog.json)：关系／实例 facts、继承 inheritance／virtual-parent、标识 identifiers、来源 mapping／membership、指标 metrics、规则 rules、更新 operations／reuse-fact。当前设计来源：仓库 docs/concepts/README.md（安装包外的概念说明）。值类型与表达式数据集已支持，分别遵循现行值类型、数据集来源设计的已确认决定。抽取轮按 SKILL 的固定包路线，不将本文件作为回读入口。
