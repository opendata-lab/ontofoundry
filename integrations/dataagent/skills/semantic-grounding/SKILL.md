---
name: semantic-grounding
description: 问数前将业务术语、指标、对象、实体名称、筛选与时间映射到已发布本体，输出带 id 的结构化理解；缺定义或实体有歧义时说明缺项或追问，再交查询工具执行。
---
# 问题语义锚定

问数先用 OntoFoundry MCP 读取授权定义；search_objects、get_object 只读已接受的文档实例及证据。确定性检索、召回和授权归工具。

取定义的顺序：
1. 把用户问题原句作为 `search_ontology` 的 query，不要先拆词。结果已按相关程度排序，`match` 说明命中原因；`expansion` 项是从直接命中扩展一层带出的相关定义。
2. 只对回答需要的元素调用 `get_ontology(ids=…)` 读取完整定义，不读取全部定义。
3. `unmatched_terms` 是问题中没有对应定义的原文片段。自行从中识别实体名称、时间范围和其他条件，不要当成定义再检索；实体名称交 `resolve_entity`（见下）。
4. 没有检索到所需的指标或对象时，换用更短的业务术语再检索一次；仍没有就说明本体中没有对应定义，不臆造口径。
不传 version_id、workspace_id、connection_alias 或 source。版本由服务端解析，响应版本只供追溯。

例如虚构星港销售空间问“销售额最高的客户”：先取得销售额指标和客户关联定义，再用数据库 GROUP BY 客户、SUM 金额、ORDER BY 金额 DESC，返回查询结果和口径。
遵守以下语义：

- simple 固定过滤始终保留；ratio 两个 simple 分量各自过滤、各自时间字段，使用小数除法及零分母 NULL；不能把分子条件套给分母。
- 每个 Dataset 独立取全表最大快照日期。日期范围为半开区间；月趋势每周期取该数据集末日，先选日后加成员或指标过滤。明确日期精确查当日，不补最近日期。
- 总计在完整时间范围重新聚合；月均值、去重和比率不能相加。无时间字段不编造月趋势，空周期展示由查询解释，不写模型默认。
- 对象成员与指标统计范围独立；父绑定、子类分支 OR、本层成员来源交集逐层应用。虚拟父合并具体来源，身份是具体类型和有序带类型键，不把相同局部键合并。
- 普通附表 LEFT JOIN 不造孤儿对象；direct 与 mapping_table 明确列组，保留复合键次序。声明唯一性不意味着查询时自动去重。
- 跨连接不能假装一个 JOIN。说明风险并分源查询或请用户决定业务对齐方式，不擅自替换来源。
- SQL 引擎语法、转换、精度和日期适配由你处理，不能改变业务定义。规则用于理解，不凭规则伪造数据库结果。

## 结构化理解

按 output-schema.json 输出完整 JSON。workspace_id、version_id 取服务端响应，不作为工具入参，不虚构 id。指标、类型、实体、筛选和时间字段的引用均带 id，名称仅展示；filters 的 value 与 value_from（如 entities[0]）选一，无时间条件为 null。

实体名称调用 `resolve_entity(mention, object_type_id)`，状态以工具为准：MATCHED 写其 entity_ref 与 match，名称包含命中时回答写明按哪个实例理解；AMBIGUOUS 时 entity_ref/display/match 为 null，clarification 列候选追问，停止统计，确认后重做理解；NOT_FOUND 且 coverage 为 partial 时不断言不存在。缺定义、身份或条件均在 unresolved 写原文及原因，不补口径。只有 unresolved 为空、clarification 为 null、实体均确认才查询。

JSON 用于单独评测本体映射，当前由 Agent 输出，自动写问数运行记录待平台接入。随后用 DataAgent 自有工具查询，中文说明范围、时间、结果及证据。display_name 称“名称”（为空用 name），name 称“英文标识”；执行适配不写回模型。
