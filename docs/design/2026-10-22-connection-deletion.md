# 数据连接删除

用户于 2026-10-22 确认方案 A：连接被引用或存在排队、运行中的同步任务时拒绝删除；无引用时显式删除本地元数据，再删除连接，不操作业务数据源。

## 已确认决定

| 项目 | 决定 |
|---|---|
| 权限 | 与创建、编辑连接相同，仅空间管理员可删除 |
| 引用范围 | 当前发布版本的数据集、未放弃会话草稿的数据集、这些会话中 pending 的数据集提案、linked_tables |
| 引用冲突 | 409 CONNECTION_IN_USE，中文提示及逐条引用类型、显示名或名称、所在位置 |
| 同步冲突 | 任意库存在 queued/running 任务时返回 409 SYNC_RUNNING |
| 清理 | 同一事务内按 batches → jobs → snapshots → connection 顺序显式删除 |
| 接口 | DELETE /api/v1/workspaces/{workspace_id}/connections/{connection_id}，成功 204 |
| 界面 | 管理员行操作增加 Ant Design Popconfirm；失败保留连接并以 Alert 列出引用；成功移除列表行 |
| 数据结构 | 不增加字段、状态、迁移；引用清单即时推导，不存入业务模型 |

已放弃（abandoned_at 非空）的会话不参与检查；v0.2.x 修复分支没有放弃会话，所有会话都参与检查。历史发布版本不阻止删除；accepted/rejected/superseded 提案不单独阻止删除。提案检查 after_json 中的数据集来源；待审删除提案使用 before_json。

错误沿用 ServiceError 信封：`error.code`、`error.message` 和由 details 展开的 `error.references`。每条引用为 `{type, name, location}`，type 为 dataset / dataset_proposal / linked_table；location 为“已发布版本”或会话标题。该结构属于接口诊断，不新增核心模型概念。

确认文案：删除连接 {name}？已同步的表结构会一起删除，不影响源数据库。
