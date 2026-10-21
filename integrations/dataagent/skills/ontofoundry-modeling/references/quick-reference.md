# 十类元素与路由

| target_kind | 业务意义 | 抽取方法 |
| --- | --- | --- |
| object_type | 有独立身份的业务类型 | [类型](extract-types.md) |
| property | 单实例的单值属性；类型选内置七种之一，或用 value_type_id 引用值类型（value_kind 填该值类型的基础类型） | 同上 |
| value_type | 多个属性共用的值域：基础类型 + 约束规则（rule 的 owner_kind=value_type，表达式里用值类型英文标识作当前值，如 `member_level IN ('普通','金卡')`） | 同上 |
| link_type | 两类型实例之间的联系 | 同上 |
| dataset | 基于表（已登记表／视图 + connection_id）或基于表达式（只读 SQL，`--variant query`） | [映射](extract-mappings.md) |
| mapping | 对象、属性与物理来源的对应 | 同上 |
| metric | 跨行聚合，独立于对象成员 | [指标规则](extract-metrics-rules.md) |
| rule | 对象、属性或关系的业务约束／说明 | 同上 |
| material_object | 材料明确陈述的对象事实 | [事实](extract-facts.md) |
| material_link | 两个对象事实之间的联系 | 同上 |

抽取轮唯一阅读路线见 SKILL.md：输入 → principles → `show_example.py --guide`、`--values`、`--part 01` 至 `--part 05` → 写后检查。表中方法仅供独立任务定点查询，不构成抽取轮第二套必读。协议模板只用于计划／确认；抽取包是裸 items 数组。Schema 只给检查器；未覆盖写法定点查正例，仍无覆盖则交付合法范围并说明缺项，不读或遍历 Schema。复杂继承另读[模式](modeling-patterns.md)。
