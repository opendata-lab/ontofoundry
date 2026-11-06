# 增量与 v2 比较

增量为 8 条（夹具 7 条）：refunds Dataset 从 update 变为 create；新增 refund_for_order 关系更新，其余含退款映射、事件数据集与四个指标。首次平台提交通过，修正 0/3。

v2 共 71 个定义（夹具 69 个），7 个指标均存在；延续 v1 新增品类值类型与品类规则的 +2 差异。数量及退款范围比较不代表字段逐项相同。

| 类型 | supplemented | 实际 v2 | 差异 |
|---|---:|---:|---:|
| dataset | 7 | 7 | +0 |
| link_type | 6 | 6 | +0 |
| mapping | 6 | 6 | +0 |
| metric | 7 | 7 | +0 |
| object_type | 6 | 6 | +0 |
| property | 30 | 30 | +0 |
| rule | 5 | 6 | +1 |
| value_type | 2 | 3 | +1 |
