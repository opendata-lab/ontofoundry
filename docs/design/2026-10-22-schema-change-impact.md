# 表结构变化影响预览与局部重建（P2）

日期：2026-10-22。状态：已确认，待实施（路线图步骤 5，用户授权按计划推进）。来源：语义锚定路线图 P2“基于 Schema 变化的局部重建”；Codex 核心竞争力方案方向三“来源变化驱动的局部维护”。血缘不参与（SG-09）。

## 1. 现状

- 表结构同步已按库保存变化记录（`MetadataSnapshotRecord.changes_json`）：表新增／消失，列新增／消失／修改，含修改前后值；数据表接口已返回 `changes`，界面未展示。
- `dataset_references(draft, dataset_id)` 能列出引用某数据集的元素。
- 建模已支持增量场景：关联表后发起对话，Agent 只改变化部分。

## 2. 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| SC-01 | 新增只读接口 `GET /connections/{id}/assets/impact?schema_name=`：对该库最近一次同步记录的每条变化，列出绑定到这张表的数据集，以及当前已发布本体中引用这些数据集的元素；能判断到列的（映射字段绑定、指标的度量列／时间列／筛选列、数据集列清单）标为“引用该列”，其余标为“引用该表”。实时计算，不存储（AR-04 同原则）。 | 已确认 |
| SC-02 | 数据表页的表详情增加“结构变化”页签：逐条显示变化和受影响的定义；有受影响定义时提供“发起局部建模”：新建一个建模会话，标题为“结构变化：<表名>”，自动关联这张表，然后打开构建页，由用户在对话中说明要怎样调整。平台不自动启动 Agent 运行（沿用 Codex 方案 Q-05 的推荐：先展示影响，由用户启动）。 | 已确认 |
| SC-03 | 只分析已发布本体；进行中会话里的未发布定义不在影响范围内。 | 已确认 |

## 3. 返回结构

```json
{
  "connection_id": "…", "schema_name": "fiction_sales",
  "items": [
    {
      "table": "fiction_orders", "column": "supplier_code", "kind": "removed",
      "before": {"name": "supplier_code", "type": "varchar(32)"}, "after": null,
      "datasets": [{"id": "…", "name": "orders"}],
      "affected": [{"kind": "property", "id": "…", "name": "supplier_code", "display_name": "供应商编码", "via": "column"}]
    }
  ]
}
```

## 4. 验收

- 删除被映射字段绑定的列：该属性（经映射）以 `via: column` 出现；只引用表的指标以 `via: table` 出现。
- 无变化或无绑定数据集时 `items` 为空或 `affected` 为空，不报错。
- “发起局部建模”创建的会话已关联该表，构建页打开该会话。
