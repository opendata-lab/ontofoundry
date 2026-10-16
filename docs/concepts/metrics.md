# 指标

[概念概览](README.md) · [主设计文档 §3.6、§3.9、§5.6、§6.5](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 中业务和数据来源均为虚构；完整包形式见[格式与转换](formats.md)。

## 1. 概述

指标保存固定业务口径，例如订单金额求和、订单完成率或每日提交数。**指标只挂数据集，与本体对象、属性、关系不建立关联。** 常见聚合用 simple，比率用 ratio，复杂算法用 expression。单行覆盖率等值仍可作为对象属性；聚合直接使用数据集列。

数据集是登记单位，背后可以是表或视图；指标只引用单个数据集的列，不关心其物理形态。

simple、expression 保存 dataset_id；ratio 的两个 simple 分量必须同一数据集，读取时从分量解析 dataset_id，输入不重复保存。所有指标只引用单个数据集：simple 的 measure、filters.column、time_field，以及 expression 的全部列和 time_field 均限本数据集。expression 只允许本数据集聚合和标量条件，不接受 SELECT、FROM、JOIN 或额外查询作用域，不使用本体路径。

跨数据集条件在查询时处理。例如只在 orders 上定义“订单金额” `SUM(orders.amount)`；用户问“华东区订单金额”时，agent 在查询时沿订单到客户的本体关系筛选客户地区，再按指标口径聚合。这是 agent 回答问题时的行为，不是指标定义的一部分；模型没有数据集之间的关系，指标与本体及本体关系完全无关。

## 2. 字段

| 字段 | 类型 | 填写要求与说明 |
|---|---|---|
| id、name、technical_name | UUID、字符串 | 必填，id 稳定，technical_name 独立寻址 |
| description、synonyms、evidence | 字符串、数组 | 可省略，默认空字符串或空数组 |
| kind | simple / ratio / expression | 必填 |
| dataset_id | UUID | simple、expression 必填；ratio 输入不收，从两个同数据集分量解析 |
| value_kind | 语义类型或 null | simple、ratio 只读推导，输入不收；expression 声明七种类型之一，外部缺失可空待补全 |
| aggregation | 枚举 | simple 必填：sum、avg、median、min、max、count、count_distinct |
| measure | ColumnReference / null | count 不填，数行；其他聚合必填，仅本数据集列 |
| filters | Condition 数组 | simple 默认空，固定条件全部 AND |
| numerator_id、denominator_id | UUID | ratio 必填，引用两个同数据集数值型 simple |
| expression | 字符串 | expression 必填，一条 SQL 聚合表达式，全部列只从 dataset_id 所指数据集选择 |
| time_field | ColumnReference / null | simple、expression 可选日期类列；simple、expression 均限本数据集；ratio 不保存，使用分量各自时间字段 |
| ColumnReference.dataset_id、column | UUID、字符串 | 登记数据集 id 和列名，必须能定位；空列清单待补全 |
| Condition.column | ColumnReference | 固定条件的本数据集列，无 path |
| Condition.operator、values | 枚举、数组 | operator 为 eq、ne、gt、ge、lt、le、in、not_in、between、is_null、not_null；值类型和数量须匹配 |

## 3. 例子

以下均为虚构数据，orders 每张订单一行：

| order_id | amount | status |
|---|---|---|
| O-1 | 100 | 已完成 |
| O-2 | 200 | 已取消 |

订单数为 2，已完成订单数为 1，完成率为 0.5。分子过滤只作用于分子；若放进公共 WHERE，分母也变为 1，结果就错了。以下片段使用[完整示例 01](../design/core-1-examples/01-basic-sales.json)的数据集和指标，不需要对象引用。

```json
{
  "datasets": [
    {
      "id": "b7cc4307-1928-522c-a58b-921b2b697d75",
      "name": "orders",
      "dialect": "mysql",
      "schema_name": "dw",
      "table_name": "orders",
      "description": "虚构示例数据集。",
      "snapshot_date_column": null,
      "columns": [
        {
          "name": "order_id",
          "physical_type": "varchar",
          "comment": "示例登记列"
        },
        {
          "name": "amount",
          "physical_type": "decimal",
          "comment": "示例登记列"
        },
        {
          "name": "status",
          "physical_type": "varchar",
          "comment": "示例登记列"
        },
        {
          "name": "created_at",
          "physical_type": "datetime",
          "comment": "示例登记列"
        },
        {
          "name": "customer_id",
          "physical_type": "varchar",
          "comment": "示例登记列"
        }
      ]
    }
  ],
  "metrics": [
    {
      "id": "00000000-0000-4000-8000-000000006002",
      "name": "订单数",
      "technical_name": "order_count",
      "description": "",
      "synonyms": [],
      "kind": "simple",
      "aggregation": "count",
      "measure": null,
      "filters": [],
      "evidence": [],
      "dataset_id": "b7cc4307-1928-522c-a58b-921b2b697d75"
    },
    {
      "id": "00000000-0000-4000-8000-000000006003",
      "name": "已完成订单数",
      "technical_name": "completed_order_count",
      "description": "",
      "synonyms": [],
      "kind": "simple",
      "aggregation": "count",
      "measure": null,
      "filters": [
        {
          "operator": "eq",
          "values": [
            "已完成"
          ],
          "column": {
            "dataset_id": "b7cc4307-1928-522c-a58b-921b2b697d75",
            "column": "status"
          }
        }
      ],
      "evidence": [],
      "dataset_id": "b7cc4307-1928-522c-a58b-921b2b697d75"
    },
    {
      "id": "00000000-0000-4000-8000-000000006098",
      "name": "完成率",
      "technical_name": "completion_rate",
      "description": "已完成订单数 / 全部订单数；分子过滤不得放公共 WHERE",
      "synonyms": [],
      "kind": "ratio",
      "numerator_id": "00000000-0000-4000-8000-000000006003",
      "denominator_id": "00000000-0000-4000-8000-000000006002",
      "evidence": []
    },
    {
      "id": "00000000-0000-4000-8000-000000006699",
      "name": "有效金额表达式",
      "technical_name": "eligible_amount_expression",
      "description": "保留已定义的算法，由 agent 根据查询引擎调整 SQL。",
      "synonyms": [],
      "kind": "expression",
      "expression": "SUM(CASE WHEN orders.status = '已完成' OR orders.status = '已发货' THEN orders.amount ELSE 0 END)",
      "value_kind": "decimal",
      "evidence": [],
      "dataset_id": "b7cc4307-1928-522c-a58b-921b2b697d75"
    }
  ]
}
```

ratio 按小数相除，零分母为空；精度和物理类型由 agent 按引擎处理，总计重新计算分量。OR、ELSE 0 等算法保持 expression，不近似改成 simple 的 AND 条件。

### 汇总表

代码行日统计每行代表一个仓库一天的汇总：

| 仓库 | 日期 | commit_count |
|---|---|---|
| core | 10-01 | 3 |
| core | 10-02 | 5 |
| web | 10-02 | 2 |

提交数为 10，核心仓库提交数为 8，占比为 0.8，COUNT(*) 为 3，只代表统计行数。有提交仓库数全周期按 repo 去重为 2，不能把两日的 1 与 2 相加。下面片段来自[示例 13](../design/core-1-examples/13-dataset-metrics.json)，无需对象绑定。

```json
{
  "datasets": [
    {
      "id": "00000000-0000-4000-8000-000000013001",
      "name": "code_lines_daily",
      "dialect": "mysql",
      "schema_name": "dev_demo",
      "table_name": "code_lines_daily",
      "description": "代码行日统计。一行代表一个仓库一天的汇总，commit_count 是当日提交数，可跨日求和。不是存量快照，不由它反查业务对象。",
      "snapshot_date_column": null,
      "columns": [
        {
          "name": "repo",
          "physical_type": "varchar",
          "comment": "仓库名"
        },
        {
          "name": "stat_date",
          "physical_type": "date",
          "comment": "事件汇总日期"
        },
        {
          "name": "commit_count",
          "physical_type": "integer",
          "comment": "当日提交数"
        }
      ]
    }
  ],
  "metrics": [
    {
      "id": "00000000-0000-4000-8000-000000013101",
      "name": "提交数",
      "technical_name": "commit_count",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "simple",
      "evidence": [],
      "aggregation": "sum",
      "measure": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "commit_count"
      },
      "filters": [],
      "time_field": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "stat_date"
      },
      "dataset_id": "00000000-0000-4000-8000-000000013001"
    },
    {
      "id": "00000000-0000-4000-8000-000000013102",
      "name": "核心仓库提交数",
      "technical_name": "core_commit_count",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "simple",
      "evidence": [],
      "aggregation": "sum",
      "measure": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "commit_count"
      },
      "filters": [
        {
          "column": {
            "dataset_id": "00000000-0000-4000-8000-000000013001",
            "column": "repo"
          },
          "operator": "eq",
          "values": [
            "core"
          ]
        }
      ],
      "time_field": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "stat_date"
      },
      "dataset_id": "00000000-0000-4000-8000-000000013001"
    },
    {
      "id": "00000000-0000-4000-8000-000000013103",
      "name": "核心仓库提交占比",
      "technical_name": "core_commit_share",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "ratio",
      "evidence": [],
      "numerator_id": "00000000-0000-4000-8000-000000013102",
      "denominator_id": "00000000-0000-4000-8000-000000013101"
    },
    {
      "id": "00000000-0000-4000-8000-000000013104",
      "name": "有提交仓库数",
      "technical_name": "active_repos",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "simple",
      "evidence": [],
      "aggregation": "count_distinct",
      "measure": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "repo"
      },
      "filters": [
        {
          "column": {
            "dataset_id": "00000000-0000-4000-8000-000000013001",
            "column": "commit_count"
          },
          "operator": "gt",
          "values": [
            0
          ]
        }
      ],
      "time_field": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "stat_date"
      },
      "dataset_id": "00000000-0000-4000-8000-000000013001"
    },
    {
      "id": "00000000-0000-4000-8000-000000013105",
      "name": "有效提交数表达式",
      "technical_name": "eligible_commit_count",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "expression",
      "value_kind": "integer",
      "evidence": [],
      "expression": "SUM(CASE WHEN code_lines_daily.repo = 'core' OR code_lines_daily.repo = 'web' THEN code_lines_daily.commit_count ELSE 0 END)",
      "time_field": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "stat_date"
      },
      "dataset_id": "00000000-0000-4000-8000-000000013001"
    },
    {
      "id": "00000000-0000-4000-8000-000000013106",
      "name": "统计行数",
      "technical_name": "stat_row_count",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "simple",
      "evidence": [],
      "aggregation": "count",
      "measure": null,
      "filters": [],
      "time_field": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "stat_date"
      },
      "dataset_id": "00000000-0000-4000-8000-000000013001"
    }
  ]
}
```

## 4. 建模建议

客户数在客户数据集数行；下单客户数在订单数据集对 customer_id 去重，须明确数据有效性假设。示例 01 声明外键有效，重复下单的客户仍只计一次。需要客户地区等其他数据集的条件时，由 agent 查询时沿本体关系筛选，不另建地区指标。

快照数据集每周期取最后有数据的一天，其他数据集取周期内全部行，再按完整算法重算。均值、去重数和比率不把每日结果相加，详见[时间与快照](time-and-snapshots.md)。

汇总表直接登记为数据集；查询是否改用汇总表由 agent 决定，须保留算法、可用维度与时间口径。不同窗口的逐行比率可作为属性，不能据此推出总体比率。

## 5. 校验、依赖与转换

count 不填 measure。sum、avg、median 要求数值；min、max 允许数值、string、date、datetime，不允许 boolean。计数为 integer，sum/min/max 沿用列类型，avg/median、ratio 为 decimal；登记类型未知时待补全，不推断任意 SQL 类型。

between 两个值，in/not_in 至少一个，is_null/not_null 零个，其余比较一个；not_in 不含 null。比较按 SQL 三值逻辑；count_distinct 不计 null，SUM 空集为空，COUNT 空集为零。

ratio 两分量必须同一数据集，可以选不同业务时间。退款金额按退款时间、销售金额按下单时间时，2 月退款率就是 2 月退款除以 2 月销售。ratio 输入 time_field 或 dataset_id 时拒绝，改变时间口径应换分量。

表达式保存文本、AST 及 dataset id 与列名引用；改数据集名只更新引用显示，不替换字面量。引用列清单空时待补全，明确不存在的列必须修订。模型检查本数据集引用和表达式边界，执行函数与类型适配交给 agent；预览另经执行白名单。

删除数据集或列、调整来源位置与快照声明时，检查直接引用及 ratio 间接依赖，相关修订归同一依赖组，最终图合法后接受。范围保持的搬迁只更新 SQL 参考，不能确认等价则列潜在影响，不扫描数据库证明等价。对象、属性、关系及 derived_by 的变化不触发指标定义修订。

符合单数据集边界的 Ossie 指标与核心指标一一对应，计算定义按本数据集字段转换。固定聚合与条件结构化，其余保留 expression；比率只有可复用已登记同数据集 simple 分量时转 ratio，否则仍是一条 expression，不额外生成指标。COUNT 可空列和条件 COUNT 可空列保持 expression，不能误转行计数。行计数使用主设计 §5.6、§6.5 的带数据集列锚定且不依赖非空键的规范形式。

超出单数据集表达式边界的 OSI 指标按 RT-69 不承载，原文和来源保留转换报告并标待补全，用户可改写为单个数据集上的指标，不生成残缺核心指标。导入来源不明时保留原文、候选和定位待用户选择，不能根据对象映射推测。列引用未闭合时待补全，导出无法合法输出时报 error，保留核心定义；没有对象映射不是丢弃指标的理由。快照、time_field 等 OSI 没有同构字段的声明仍按 RT-60 报损失，完整备份使用原生格式。导入只新增和修改，不生成删除提案，详见[格式与转换](formats.md)。

### 新建与预览（原型阶段确认）

新建表单选择数据集，展示其“一行 = …”说明，再选择聚合、列、固定条件或表达式。simple 和 expression 只列所选数据集的列，ratio 选同数据集 simple。时间字段为日期类列，ratio 分别展示分量时间；维度不另存清单，查询分组由 agent 组织。

指标弹窗展示数据集、完整口径、时间与授权 SQL 参考，不返回或展示模型中的对象归属。对象弹窗或详情是否按绑定推导展示“相关指标”，留给工程实施和原型阶段决定，不存储这种关联。

平台按当前完整表单、ratio 分量和时间范围编译并展示参考 SQL，在数据集对应的已登记连接上只读执行总值，有时间字段时再执行月趋势。预览不经 DataAgent，不拉实例分页聚合；表单变化须重新执行。白名单失败、引擎不支持、列未补全、连接或权限缺失、查询失败时说明无法预览，不伪造数值。预览不写模型，MCP 仍只提供语义，实施见主设计 §8A、§9。

## 6. 与业界做法的对照

核查日期：2026-10-16。指标放在数据集上，与以下分层一致；产品能力和字段不因此完全相同。

| 产品 | 定义与展示 |
|---|---|
| [Ossie / OSI](https://github.com/apache/ossie/blob/main/core-spec/spec.yaml) | 指标在 semantic_model.metrics 中引用数据集字段，没有指向本体概念的关系；core-1 只承载符合单数据集边界的部分，例外见主设计 §7 |
| [Fabric IQ 操作页](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-metrics)与[定义协议](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition) | 定义为顶层 model.metrics[]。操作页说明 measure 按其定义所在表对应的实体展示；“显示在实体下”不能视为模型上的对象归属。explicit 有自身表达式，其他类型可引用源 measure |
| [Palantir 对象集合聚合](https://www.palantir.com/docs/foundry/api/ontology-resources/objects/aggregate) | 提供对象集合聚合和分组；本体没有与这里 Metric 对应的可复用指标定义，不能把一次聚合调用当作独立指标资源 |
| [dbt 语义模型](https://docs.getdbt.com/docs/build/semantic-models) | simple 指标写在一个表对应的语义模型上，使用该模型的列 |
| [Snowflake 语义视图](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view) | 可在一个逻辑表上对该表的列定义聚合指标；这里对照在单个数据集上聚合的用法 |
| [Looker measure](https://docs.cloud.google.com/looker/docs/reference/param-measure-types) | measure 写在视图中，聚合类型配合 SQL 表达式 |

core-1 保留 simple、ratio 便于编辑常见口径，expression 保留复杂算法；均只引用自己的 dataset_id 所指数据集的列。用户问题中的其他数据集条件由 agent 查询时沿本体关系筛选，不写入指标。对象详情是否按绑定展示相关指标由原型决定，不是持久化关联。
