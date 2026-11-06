# 与 conservative 比较

| 类型 | 夹具 | 实际 | 差异 |
|---|---:|---:|---:|
| dataset | 6 | 5 | -1 |
| link_type | 6 | 6 | +0 |
| mapping | 5 | 5 | +0 |
| metric | 3 | 3 | +0 |
| object_type | 6 | 6 | +0 |
| property | 30 | 30 | +0 |
| rule | 5 | 6 | +1 |
| value_type | 2 | 3 | +1 |

总数 63 → 64；新增品类值类型和品类规则，缺退款空列数据集。退款只有语义，无退款映射、SQL 或指标，答复提示先同步退款。首轮含退款 Dataset 被 SOURCE_NOT_REGISTERED 拒绝；尝试清除 table_name 又被元素校验拒绝，最终删除该 Dataset 后通过。提交 4 次，3 次失败，修正 3/3。名称、标识及关系方向与夹具有差别，未把数量相同当作逐字段完全相等。
