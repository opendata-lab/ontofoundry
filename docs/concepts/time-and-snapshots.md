# 时间与快照

[概念概览](README.md) · [主设计文档 §3.6、§3.7](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源都是虚构的；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。

## 1. 概述

数据里的时间有好几种，回答的问题各不相同：

- **订单金额**记录的是一笔笔发生过的交易。12 月 30 日卖了 100，31 日卖了 200，12 月的销售额就是 300，跨日期相加是对的。
- **库存**记录的是某一天的状态。上海仓 12 月 30 日有 100 件，31 日有 120 件，并不代表一共有 220 件。问“12 月底的库存”，要取 31 日那一天的值。

core-1 只在两个地方声明时间，其余规则都由这两处推出：

1. **数据集的快照日期列**：告诉平台“这张表每天存一份全量状态，日期在这一列”。只给每日全量快照表填写。
2. **simple、expression 指标的时间字段**：告诉 agent “这个指标按哪个时间归到周期”，例如订单金额按下单时间还是支付时间统计。可以不填；ratio 不保存时间字段，分别使用分子、分母的定义。

快照数据集（声明了 snapshot_date_column）每个周期取最后一个有数据的日期，其他数据集取周期内全部行；然后按指标自身算法在整个范围上重新计算，去重、均值、比率等不把每日结果相加。

核心只提供这些语义，具体的 SQL 由 agent 拼。不同数据集日期不一致时如何关联、整个周期没有数据时如何显示，也由 agent 根据问题处理并说明所用日期。

## 2. 四种时间

| 时间 | 回答什么问题 | 例子 | 在模型里的位置 |
|---|---|---|---|
| 快照时间 | 这一行是哪一天的状态 | 组件每日快照表的 `snapshot_date` | 数据集的 `snapshot_date_column` |
| 业务时间 | 这件事什么时候发生 | 订单的下单时间、支付时间；组件的上线日期 | 对象的日期类属性，或数据集的日期类列 |
| 指标的时间字段 | 这个指标按哪个时间归到周期 | 订单金额按下单时间统计 | simple、expression 的 `time_field`；ratio 使用分量定义 |
| 技术时间 | 数据什么时候被加载或更新 | `update_time`、`etl_time` | 可以建成属性，一般不作为指标的时间字段 |

**怎么判断一张表是不是快照表**：看每一行代表什么。

| 表的类型 | 常见后缀 | 每行代表 | 日期列是什么 | 统计时如何选行 |
|---|---|---|---|---|
| 每日全量快照 | `_df` | 某天某个实体的状态 | 快照时间，在数据集上声明 | 每周期取最后有数据的一天 |
| 每日增量分区 | `_di` | 某天发生的事 | 业务时间，不声明快照 | 取周期内全部行，再按指标算法重算 |

“代码行日统计”“接口每日调用次数”这类表虽然每天一行，但记录的是当天发生的数，属于增量分区，不声明快照。

## 3. 字段

| 字段 | 类型 | 什么时候填 | 说明 |
|---|---|---|---|
| `Dataset.snapshot_date_column` | 字符串，可以为空 | 每日全量快照表填写快照日期列；其他表留空 | 声明后，每周期按该数据集最后有数据的日期选行，实例浏览默认只取最新一天 |
| `Metric.time_field` | 日期类列引用，可以为空 | 仅 simple、expression 可填；ratio 不保存 | simple、expression 均只选自己的 dataset_id 所指数据集列；快照日期列也可选，ratio 各用分量时间 |

## 4. 怎么计算

快照数据集（声明了 snapshot_date_column）每个周期取最后一个有数据的日期，其他数据集取周期内全部行；然后按指标自身算法在整个范围上重新计算，去重、均值、比率等不把每日结果相加。

“最后一个有数据的日期”以整个数据集为范围，同一数据集的所有行用同一天，不按实例、地区或子对象各取最近日期。对象有普通主表和快照附表时，各列按所在表声明处理，每个数据集独立选日期。问“当前”时取各快照数据集最新的日期，指定某一天时用那一天。选定快照后，按业务时间分组的指标再按自己的 time_field 归组；没有时间字段就不按时间分组。

ratio 使用分子、分母各自的 time_field。例如退款率 = 退款金额（按退款时间）÷ 销售金额（按下单时间），2 月结果为 2 月退款除以 2 月销售。需要其他口径时换相应分量，不另设 ratio 时间字段。

## 5. 例子

### 5.1 数据集与指标

[示例 12](../design/core-1-examples/12-snapshot-and-trends.json) 的组件数量表是每日全量快照：

```json
{
  "id": "d87c134f-d101-5fae-8841-427b309a61cd",
  "name": "component_daily",
  "dialect": "mysql",
  "schema_name": "snapshot_demo",
  "table_name": "component_daily",
  "description": "每日全量快照：每行是某个组件或仓库在某天的状态。",
  "snapshot_date_column": "snapshot_date",
  "columns": [
    {
      "name": "component_id",
      "physical_type": "varchar",
      "comment": "组件编号"
    },
    {
      "name": "snapshot_date",
      "physical_type": "date",
      "comment": "业务快照日期"
    },
    {
      "name": "quantity",
      "physical_type": "integer",
      "comment": "数量"
    },
    {
      "name": "warehouse_code",
      "physical_type": "varchar",
      "comment": "仓库编码"
    }
  ]
}
```

“组件期末数量”的时间字段是快照日期列，数据集已经声明快照：

```json
{
  "id": "00000000-0000-4000-8000-000000061101",
  "name": "组件期末数量",
  "technical_name": "component_closing_quantity",
  "description": "时间字段是快照日期；数据集声明了快照，按周期取最后一个有数据的日期。",
  "synonyms": [],
  "kind": "simple",
  "aggregation": "sum",
  "measure": {
    "dataset_id": "d87c134f-d101-5fae-8841-427b309a61cd",
    "column": "quantity"
  },
  "filters": [],
  "evidence": [],
  "time_field": {
    "dataset_id": "d87c134f-d101-5fae-8841-427b309a61cd",
    "column": "snapshot_date"
  },
  "dataset_id": "d87c134f-d101-5fae-8841-427b309a61cd"
}
```

### 5.2 期末取值

| 组件 | 快照日期 | 数量 |
|---|---|---|
| A | 12-29 | 9 |
| B | 12-29 | 7 |
| A | 12-31 | 10 |

问“12 月期末数量”：这个数据集 12 月最后有数据的日期是 12-31，所有行都用这一天，结果是 10。B 在 12-31 没有数据，不会退回 12-29 用它的 7。

```sql
WITH chosen_day AS (
  SELECT MAX(snapshot_date) AS d
  FROM snapshot_demo.component_daily
  WHERE snapshot_date >= '2026-12-01' AND snapshot_date < '2027-01-01'
)
SELECT SUM(q.quantity) AS closing_quantity
FROM snapshot_demo.component_daily AS q
JOIN chosen_day AS c ON q.snapshot_date = c.d;
```

错误的算法有两种：每个组件各取自己最后一条，得到 10 + 7 = 17；把所有行加起来，得到 26。两者都不是这里定义的期末。

### 5.3 快照表上的业务时间

| snapshot_date | 组件 | 上线日期 |
|---|---|---|
| 12-30 | A | 10-05 |
| 12-30 | B | 12-20 |
| 12-31 | A | 10-05 |
| 12-31 | B | 12-20 |
| 12-31 | C | 12-31 |

- “组件数”，时间字段为快照日期：12 月取 12-31，结果是 3。
- “截至 12 月底的组件按上线月份计数”，时间字段为上线日期：先取 12 月最后有数据的快照 12-31，再按上线日期归月，12 月是 2（B、C），10 月是 1（A）。如果不先取快照，A 会被数两次。

### 5.4 实例浏览

对象绑定的数据集是快照表时，浏览实例默认只看最新一天，否则同一个组件会每天出现一次。也可以指定日期，查看当时有哪些组件、各自是什么状态。

## 6. 建模建议

**先判断表的类型。** 每行是“某天的状态”才是快照表；每行是“某天发生的数”是增量分区，日期只是业务时间。把增量分区表误声明为快照，月度合计就只剩月末一天。

**快照表里的“当日发生数”。** 有些全量快照表顺带放了一列“当日调用次数”。这一列是事件，跨日期相加才对。建模时应把这类列移到每日增量表；模型不提供指标例外开关。

**时间字段要写明口径。** 订单 O2 在 1 月 30 日下单、2 月 2 日付款。按下单时间，它算 1 月；按支付时间，它算 2 月。两种月度金额都对，口径不同，所以要在指标上选定时间字段，不要让 agent 猜。

**窗口表不要相加。** 近一月、近三月这类窗口统计分别建成属性或来源，并说明窗口起止。窗口互相重叠，不能相加；日均值不能再平均成总体均值。

删除数据集或列、调整来源位置和快照声明时，列出直接引用与 ratio 间接依赖的指标，相关修订归同一依赖组。范围保持的来源搬迁只更新 SQL 参考，不能确认等价则列潜在影响，不扫描数据证明等价。对象成员、继承、属性或关系定义的变化不触发指标定义修订。

## 7. 校验与限制

- 快照日期列和 simple、expression 的时间字段必须能定位到登记数据集的日期类列；ratio 不得保存 time_field，分量时间字段允许不同。两个分量必须引用同一数据集。
- 平台不检查多个数据集的日期是否一致，不证明快照是否完整。
- 取期末固定为“周期内最后一个有数据的日期”，不提供取期初。
- 日期不齐时如何关联、空周期如何显示（补零、留空或省略），核心都不规定，由 agent 处理并说明。
- 元数据快照（列类型、注释的采集）和业务日快照是两个不同的概念；MCP 返回的版本也不是业务数据的历史版本。

## 8. 与业界做法的对照

核查日期：2026-10-15。

| 产品 | 时间字段 | 时间聚合声明或显示设置 |
|---|---|---|
| [dbt 语义层](https://docs.getdbt.com/docs/build/semantic-models) | 模型的 `agg_time_dimension` 为默认时间轴，新版 simple metric 可覆盖 | 旧版 [measure](https://docs.getdbt.com/docs/build/measures#non-additive-dimensions) 和新版 [simple metric](https://docs.getdbt.com/docs/build/simple) 都有 `non_additive_dimension`；旧 measure 已弃用 |
| [Snowflake 语义视图](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view) | 时间作为维度显式声明 | 在 metric 上写 `NON ADDITIVE BY`，按声明的排序取末值参与聚合 |
| [Tableau Pulse](https://trailhead.salesforce.com/content/learn/modules/tableau-pulse-fundamentals/create-metric-definitions) | 定义指标时必填 Time Dimension | `Show values to date as` 只控制图上各点的累计显示，顶部当前值仍为周期累计；此资料未证明等价的期末快照规则 |
| [Databricks 指标视图](https://docs.databricks.com/aws/en/uc-semantics/metric-views/advanced-techniques) | 时间作为维度声明，并可用作窗口的 order 字段 | measure 的 window 中声明 `semiadditive: first/last`，查询未按 order 字段分组时取首值或末值；不等同于整个数据集统一选日 |
| [Microsoft Fabric IQ](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-bind-data) | 实体可以绑定时间序列来源 | 在数据绑定一侧处理，未核实与本平台同构的指标级声明 |
| [Palantir Foundry](https://www.palantir.com/docs/foundry/time-series/time-series-overview) | 对象有专门的时间序列属性 | 在数据一侧处理，未核实与本平台同构的指标级声明 |
| [Apache Ossie](https://github.com/apache/ossie/blob/main/core-spec/spec.yaml) | 字段有“是否时间维度”的标记 | 没有快照字段 |

我们的 time_field 与 dbt 的 agg_time_dimension 在归周期的用途上相近，core-1 允许不填，dbt 对定义指标的模型要求时间维度和默认时间轴。我们只在数据集上声明快照，不在指标上声明；dbt 在旧 measure 或新 simple metric 上、Snowflake 在 metric 上、Databricks 在 measure 的窗口中声明相应时间聚合规则。core-1 的数据集声明也供实例浏览使用，混入快照表的事件列应拆到每日增量表。

导出到 Ossie 时，数据集的快照声明写进该数据集的描述，simple、expression 的时间字段写进指标描述，按 RT-60 逐项报告，不能从说明文字自动回读。
