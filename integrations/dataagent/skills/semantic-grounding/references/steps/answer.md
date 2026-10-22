# 结构化理解与回答


按 output-schema.json 输出完整 JSON。workspace_id、version_id 取服务端响应，不作为工具入参，不虚构 id。指标、类型、实体、筛选和时间字段的引用均带 id，名称仅展示；filters 的 value 与 value_from（如 entities[0]）选一，无时间条件为 null。

实体名称调用 `resolve_entity(mention, object_type_id)`，状态以工具为准：MATCHED 写其 entity_ref 与 match，名称包含命中时回答写明按哪个实例理解；AMBIGUOUS 时 entity_ref/display/match 为 null，clarification 列候选追问，停止统计，确认后重做理解；NOT_FOUND 且 coverage 为 partial 时不断言不存在。缺定义、身份或条件均在 unresolved 写原文及原因，不补口径。只有 unresolved 为空、clarification 为 null、实体均确认才查询。

JSON 用于单独评测本体映射，当前由 Agent 输出，自动写问数运行记录待平台接入。随后用 DataAgent 自有工具查询，中文说明范围、时间、结果及证据。display_name 称“名称”（为空用 name），name 称“英文标识”；执行适配不写回模型。
