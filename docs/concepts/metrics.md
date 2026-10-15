# 指标

[概念概览](README.md) · [主设计文档 §3.6、§3.9、§6.5](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 1. 概述

“订单总金额”需要把多张订单的金额相加；“提交数”可能来自已经汇总好的“代码行日统计”表，对 commit_count 求和即可。指标保存这样的固定业务口径，让不同问题复用同一计算。

先选择统计对象：可以是业务对象，也可以是登记数据集。对象指标可沿允许的关系方向引用属性；数据集指标直接引用列，不通过绑定反查对象。常见聚合用 simple，比率用 ratio，复杂算法用 expression。单张订单金额或单行覆盖率属于属性；只有要计算一批记录时才需要指标。指标与本体并列，只在语义视图筛选查看。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `id` | UUID | 必须提供。 | 这是指标的稳定身份，改名后不变。 |
| `name` | 字符串 | 必须提供。 | 这是向用户显示的指标名称。 |
| `technical_name` | 字符串 | 必须提供。 | 这是工作空间内独立引用指标的技术名。 |
| `description` | 字符串 | 可省略，默认空字符串。 | 此字段解释指标口径、单位约定与适用范围。 |
| `synonyms` | 字符串数组 | 可省略，默认空数组。 | 这些别名用于搜索和问答理解。 |
| `evidence` | Evidence 数组 | 可省略，默认空数组。 | 这些证据说明指标定义的依据。 |
| `kind` | 枚举 | 必须提供。 | simple 保存简单聚合，ratio 保存比率，expression 保存 SQL 聚合表达式。 |
| `value_kind` | 语义类型或 null | simple、ratio 仅在读取时推导，原生输入不得填写；expression 声明类型，外部缺失时待补全。 | 此字段说明计算结果类型，不要求平台推断任意 SQL 的类型；登记列类型无法确定时也标为待补全。 |
| `base_type_id` | UUID 或 null | simple、expression 与 base_dataset_id 二选一；ratio 不保存。 | 此字段显式引用业务对象，界面称“统计对象”。 |
| `base_dataset_id` | UUID 或 null | simple、expression 与 base_type_id 二选一；ratio 不保存。 | 此字段显式引用登记数据集，不根据对象绑定反查业务对象。 |
| `aggregation` | 枚举 | simple 必须填写。 | 此字段选择 sum、avg、median、min、max、count 或 count_distinct。 |
| `measure` | Path、ColumnReference 或 null | simple 的 count 为空，其他聚合必须填写。 | 对象指标引用属性路径；数据集指标只引用本数据集的列，count 分别数对象实例或数据集行。 |
| `filters` | Condition 数组 | simple 可省略，默认空数组。 | 这些固定条件必须同时满足；对象用路径，数据集用列。 |
| `numerator_id` | UUID | ratio 必须填写。 | 此字段引用数值型 simple 分子，与分母必须同统计对象，ratio 从分量推导。 |
| `denominator_id` | UUID | ratio 必须填写。 | 此字段引用数值型 simple 分母，必须与分子引用同一对象或同一数据集。 |
| `expression` | 字符串 | expression 必须填写。 | 此字段保存一条 SQL 聚合算法；对象使用本体引用，数据集直接使用列，不沿关系导航。 |
| `time_field` | 属性路径或列引用，可以为空 | 仅 simple、expression 可填，ratio 不保存。 | 决定按哪个时间把数据归到周期，例如订单金额按下单时间还是支付时间。统计对象是业务对象时引用日期类属性，是数据集时引用日期类列，快照日期列也可以选。详见[时间与快照](time-and-snapshots.md)。 |
| `Path.links` | 数组 | 对象属性路径必须提供，可为空数组。 | 每跳保存关系 id 和 forward 或 reverse 方向；空数组表示统计对象自身属性。 |
| `Path.property_id` | UUID | 对象属性路径必须提供。 | 此字段引用路径最终到达的属性。 |
| `ColumnReference.dataset_id` | UUID | 列引用必须提供。 | 此字段引用指标的显式 base_dataset_id，不代表对象。 |
| `ColumnReference.column` | 字符串 | 列引用必须提供。 | 此字段必须出现在登记的列清单中；清单为空时待补全，不臆造列。 |
| `Condition.path` | Path | 对象粒度条件必须填写，不能与 column 同填。 | 此字段指定参与比较的属性路径。 |
| `Condition.column` | ColumnReference | 数据集粒度条件必须填写，不能与 path 同填。 | 此字段指定参与比较的本数据集列，不含关系路径。 |
| `Condition.operator` | 枚举 | 每个条件必须提供。 | 此字段选择 eq、ne、gt、ge、lt、le、in、not_in、between、is_null 或 not_null。 |
| `Condition.values` | 数组 | 每个条件必须提供，可依运算符为空数组。 | 此字段保存比较值，数量和类型必须符合运算符及属性或列。 |

## 3. 例子

以下片段完整定义全部订单数、已完成订单数、完成率和一个含 OR 的表达式指标。对象、属性依赖来自[概览](README.md)及[基础销售完整样例](../design/core-1-examples/01-basic-sales.json)。

```json
{
  "metrics": [
    {
      "id": "00000000-0000-4000-8000-000000006002",
      "name": "订单数",
      "technical_name": "order_count",
      "description": "",
      "synonyms": [],
      "kind": "simple",
      "base_type_id": "00000000-0000-4000-8000-000000001002",
      "aggregation": "count",
      "measure": null,
      "filters": [],
      "evidence": []
    },
    {
      "id": "00000000-0000-4000-8000-000000006003",
      "name": "已完成订单数",
      "technical_name": "completed_order_count",
      "description": "",
      "synonyms": [],
      "kind": "simple",
      "base_type_id": "00000000-0000-4000-8000-000000001002",
      "aggregation": "count",
      "measure": null,
      "filters": [
        {
          "path": {
            "links": [],
            "property_id": "00000000-0000-4000-8000-000000002013"
          },
          "operator": "eq",
          "values": [
            "已完成"
          ]
        }
      ],
      "evidence": []
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
      "base_type_id": "00000000-0000-4000-8000-000000001002",
      "kind": "expression",
      "expression": "SUM(CASE WHEN sales_order.status = '已完成' OR sales_order.status = '已发货' THEN sales_order.amount ELSE 0 END)",
      "value_kind": "decimal",
      "evidence": []
    }
  ]
}
```

完成率的 SQL 示意按分量保留各自过滤；这里只用 1.0 示意小数除法，实际类型和精度由 agent 按引擎处理，不作为语义合同：

```sql
WITH numerator AS (
  SELECT COUNT(*) AS n FROM dw.orders WHERE status = '已完成'
), denominator AS (
  SELECT COUNT(*) AS n FROM dw.orders
)
SELECT 1.0 * n.n / NULLIF(d.n, 0) AS completion_rate
FROM numerator AS n CROSS JOIN denominator AS d;
```

此例假设 orders 在所查范围每个订单一行；存在历史快照或增行连接时须先处理相应范围。一个已完成、一单取消，结果为 0.5；分母为零时为空。表达式指标按其完整公式交给 agent，不把 OR 改成 simple 的 AND 条件。

指标弹窗直接展示描述、同义词、完整口径、simple、expression 的时间字段、ratio 两个分量各自的时间口径和有权限的 SQL 参考。指标只在语义视图筛选查看，对象弹窗没有指标入口。指标弹窗只显示显式统计对象，或路径及引用属性所属对象；没有这些本体引用就省略该项，不显示“未关联本体”，也不依据数据集绑定反查对象。ratio 汇总分量的显式本体引用。

### 直接在汇总表上定义指标

输入数据如下：

| 仓库 | 日期 | commit_count |
|---|---|---|
| core | 10-01 | 3 |
| core | 10-02 | 5 |
| web | 10-02 | 2 |


以下片段来自[完整示例 13](../design/core-1-examples/13-dataset-metrics.json)。数据集名称 code_lines_daily 表示“代码行日统计”，没有业务对象或对象绑定也能定义指标。measure 与条件使用列结构，expression 直接写列；ratio 读取时从分量推导相同统计数据集，时间字段由分量提供。

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
      "base_dataset_id": "00000000-0000-4000-8000-000000013001",
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
      }
    },
    {
      "id": "00000000-0000-4000-8000-000000013102",
      "name": "核心仓库提交数",
      "technical_name": "core_commit_count",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "simple",
      "base_dataset_id": "00000000-0000-4000-8000-000000013001",
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
      }
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
      "id": "00000000-0000-4000-8000-000000013105",
      "name": "有效提交数表达式",
      "technical_name": "eligible_commit_count",
      "description": "直接使用数据集列；不反查对象。",
      "synonyms": [],
      "kind": "expression",
      "value_kind": "integer",
      "base_dataset_id": "00000000-0000-4000-8000-000000013001",
      "evidence": [],
      "expression": "SUM(CASE WHEN code_lines_daily.repo = 'core' OR code_lines_daily.repo = 'web' THEN code_lines_daily.commit_count ELSE 0 END)",
      "time_field": {
        "dataset_id": "00000000-0000-4000-8000-000000013001",
        "column": "stat_date"
      }
    }
  ]
}
```

```sql
SELECT SUM(commit_count) AS commit_count
FROM dev_demo.code_lines_daily;
```

上文数据得到提交数 10、核心仓库提交数 8、核心仓库提交占比 0.8。指标弹窗省略关联本体项。若未来要改挂“提交”对象，必须确认它与明细提交记录同口径，并以提案改成属性路径，不能仅改 base 字段。汇总表仍可登记成独立数据集，直接在其上建数据集指标。

## 4. 建模建议

正例：在代码行日统计数据集上对 commit_count 求和，提交数为 10；固定条件仓库=core 时为 8。有提交仓库数按 repo 去重，10-01 为 1、10-02 为 2，全周期仍为 2，不能把日结果相加为 3。

反例：COUNT(*) 得到 3，只是统计行数，不能当成提交数；也不能根据该表绑定过“组件”就自动把统计对象改成组件。

正例：客户数以客户为粒度使用 count；下单客户数以订单为粒度，沿多对一客户关系对客户编号 count_distinct。反例：把订单数当成客户数，会让多次下单的客户重复出现。

快照数据集（声明了 snapshot_date_column）每个周期取最后一个有数据的日期，其他数据集取周期内全部行；然后按指标自身算法在整个范围上重新计算，去重、均值、比率等不把每日结果相加。

总体完成率按分子、分母重新计算；不能相加各地区比率，也不能把分子过滤移到公共 WHERE。逐行百分比是属性，不自动推出总体指标。

median 可直接使用结构化聚合声明，agent 按引擎实现；复杂函数、OR 或特殊拼接去重用 expression。不要把 `COUNT(DISTINCT a || '::' || b)` 改成对象计数或元组去重，分隔符、NULL 和字符串算法都是口径的一部分。

汇总表登记成数据集，直接在其上建数据集指标；查询时用不用汇总表由 agent 决定，须保留固定算法、可用维度和时间口径。只有每日去重客户数不能直接相加为月去重客户数；只有地区总额不能回答按客户的排名。

## 5. 校验与限制

simple、expression 显式保存 base_type_id 或 base_dataset_id，恰好一项非空。ratio 不保存 base 字段，只从两个同统计对象的数值型 simple 分量推导，缺分量或不一致报依赖未闭合。只读 MCP 可以返回推导的统计对象；表单预览按当前未保存的分量解析。对象 simple 的路径从统计对象出发，只允许正向多对一、一对一、反向一对一；数据集 simple 的度量与条件只用本数据集列，不沿关系走。数据集 expression 也直接写列，平台对照 Dataset.columns 检查存在性；清单为空时待补全，不生成假列或属性。登记中出现明确不存在的列时必须修订引用。

count 不填 measure；sum、avg、median 需要数值，min、max 允许数值、string、date、datetime，不允许 boolean。计数结果为 integer，sum/min/max 沿用度量值类型，avg/median 与 ratio 为 decimal；列类型无法确定则待补全。ratio 分量必须是数值型 simple，彼此引用同一对象或同一数据集。ratio 不存 time_field，保存时拒绝该字段；分子、分母各按自己的时间字段归周期，允许不同。退款率 = 退款金额（按退款时间）÷ 销售金额（按下单时间）时，2 月结果为 2 月退款除以 2 月销售；想要其他口径就换相应分量。分量时间字段变更时，依赖的 ratio 展示各自新口径，不自动改写另一个分量。小数除法分母为零时结果为空，总计按分量重新计算。

条件 values 的数量必须匹配运算符：between 两个，in/not_in 至少一个，is_null/not_null 零个，其余比较一个；not_in 不含 null。SQL 三值逻辑适用，is_null 不等同关系不存在。count_distinct 精确去重且不计 null，SUM 空集为空、COUNT 空集为零。

expression 保留算法，不套用 simple 的 AND 或对象路径基数限制。模型校验只检查引用，不推断 SQL 类型或执行函数；界面预览另须通过执行白名单。指标单向用 id 引用本体；对象、属性或关系改名不影响口径，表达式显示按 id 重新生成，不替换字面量。删除被引用对象、属性或关系，或改关系基数导致路径不合法时，校验列出受影响指标及 ratio 依赖，并把修订提案放入同一依赖组，最终图合法才能接受。提案区分语义和范围保持的物理换绑，与可能改变属性、关系含义或成员、实例、时间范围的修改。派生条件、成员扩展来源、主来源和快照声明等后者，须沿引用、继承、成员派生及 ratio 分量列出受影响指标和原因。不能确认等价的换绑列潜在影响，不扫描数据库证明等价。删除数据集同样检查挂在其上的指标和表达式列引用，不留下悬空依赖。

Ossie 指标一律导入为数据集指标，不要求数据集已映射对象。固定聚合和条件按列结构化，其余保留 expression。COUNT DISTINCT 保持列去重，不能根据对象键改成对象 count。未声明统计来源且不能唯一确定数据集时，原文保留为阻断待补全条目，等待用户选择数据集或点击 AI 补全后再形成指标提案，对应已有定义保持不动。平台导入只新增和修改，从不生成 delete 提案；要删除就在会话里手动操作，或让 agent 提删除提案并走正常审阅。导入后用户或 AI 可提案改挂对象，同时把列引用替换成属性路径。不保存通过数据集反查属性的 reference_bindings。

所有对象指标导出的共同前提是完整对象范围可表达：主来源决定的集合、祖先及本层派生条件、成员扩展来源、关系路径到达的子类范围均须保留。按属性与计算绑定解析后的实际来源判断主来源锚点，不能看空路径就认为来自主表；仅输出子概念声明也不限定 dataset 聚合。能等价写入聚合表达式时保留完整范围，否则 RT-61：simple、ratio 本项 dropped，expression 本项 error；ratio 两个分量都要满足。示例 11 金额来自附表，主表为 A1、A2，附表为 (A1,100)、(A3,900)，正确结果100，不能直接对附表求和得到1000，本例按 dropped 处理。

固定 CASE 只将 SUM、AVG、MEDIAN、MIN、MAX 识别为 measure 加 filters，COUNT DISTINCT 独立处理。COUNT(可空列) 及其 CASE 形式保留 expression；两行都满足条件、列值为 NULL 与10时，COUNT 列是1，行计数是2，不能互换。

表达式导出同样检查角色、方向和统计范围。交易金额100，买方在华东、卖方在华南，条件“买方华东且卖方华南”应得100；若两路径都变成 companies.region，则错误结果为0。本项须 error，核心指标保留，整份文件若要求该指标则不能交付缺项文件。重复引用同一角色不应误报，能证明目标保留角色时正常转换。

### 新建指标（原型阶段确认）

**统计对象与算法。** 在语义视图筛选到“指标”后使用“新建指标”。表单包含名称、同义词、统计对象、计算方式、字段、条件、SQL 参考和数值预览。统计对象下拉分“业务对象”“数据集”两组，选后展示“一行 = 一张订单”或“一行 = 一个代码仓库一天的统计”等说明；界面不使用“粒度”。计算方式提供计数、求和、平均、最大、最小、去重计数、中位数、比率、写表达式。对象字段从统计对象出发，只展开允许的正向多对一、一对一及反向一对一方向；数据集只列登记列。比率选择两个同统计对象的简单指标。

**时间。** simple 和 expression 的“时间字段”下拉只列日期类属性或列，包含快照日期列，可以不选。ratio 不显示时间选择框，分别展示分子和分母的时间口径；要改变口径就换相应分量。快照选行由各数据集自身声明决定。

**维度。** 指标不另存一份可切分维度清单。对象指标沿允许方向可达的属性可用于分组和筛选，数据集指标使用本数据集登记列。

**预览。** 平台自己执行，不经过 DataAgent。使用当前表单的完整定义、ratio 分量定义、授权来源和预览时间范围，编译成表单中展示的参考 SQL，用统计对象所绑定的已登记连接只读执行一次并显示结果；数据集指标直接使用 base_dataset_id 对应的登记连接，无需对象绑定。有时间字段时，按月再执行一次小趋势；ratio 按分子、分母各自时间字段归月后相除。预览只用于界面自查，不写入模型。改表单后须基于新定义重新预览，不能把已保存旧定义的结果当成当前值。

预览复用现有指标编译、sqlglot 白名单检查和只读执行，以及实例查询所用的连接与权限路径；不使用实例分页明细。表达式未通过白名单、引擎不支持、缺绑定或已登记连接、列清单待补全、权限不足或查询失败时显示“无法预览”及原因，不伪造数值。MCP 只提供语义，agent 答题时自己写 SQL，平台界面自查预览独立执行，实施落点见[主设计 §8A、§9](../design/2026-10-14-core-model-and-format-adapters.md)。也可在本体构建中让 AI 生成同样提案。

## 6. 与业界做法的对照

核查日期：2026-10-15。各产品定义指标的方式：

| 产品 | 指标挂在什么上面 | 怎么取到别的表的字段 | 时间 | 能按什么切分 |
|---|---|---|---|---|
| [Databricks 指标视图](https://docs.databricks.com/aws/en/metric-views) | 一个源表或一段 SQL | 在指标视图里声明 join | 时间是普通维度；measure 的 window 可声明 [`semiadditive: first/last`](https://docs.databricks.com/aws/en/uc-semantics/metric-views/advanced-techniques)，未按 order 分组时取首值或末值 | 显式列出维度 |
| [Snowflake 语义视图](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view) | 逻辑表（带主键） | 声明表间关系 | 时间是普通维度；`NON ADDITIVE BY` 声明不可相加 | 显式列出维度 |
| [dbt 语义层](https://docs.getdbt.com/docs/build/semantic-models) | 语义模型（一张表一个） | 靠实体键自动连接 | `agg_time_dimension` 为模型默认时间，新版 simple metric 可覆盖；旧 [measure](https://docs.getdbt.com/docs/build/measures) 和新 [simple metric](https://docs.getdbt.com/docs/build/simple) 都有 non_additive_dimension | 先在语义模型声明维度，再沿实体键使用可达的已声明维度 |
| [Tableau Pulse](https://trailhead.salesforce.com/content/learn/modules/tableau-pulse-fundamentals/create-metric-definitions) | 一个数据源 | 数据源本身已连好表 | 必须选时间字段；累计设置只影响图上各点显示，顶部当前值仍为周期累计，此来源未证明等价的期末快照规则 | 固定筛选与看的人可以改的筛选 |
| core-1 | 业务对象或数据集，二选一 | 对象沿关系路径，数据集直接使用列 | simple、expression 可选时间字段，ratio 用分量时间；只在数据集声明快照 | 对象由允许方向可达属性推出，数据集使用登记列 |

我们的统计对象覆盖数据集与业务对象两种建法。维度如何声明与已声明维度是否沿关系可达是两件事：core-1 对象指标直接使用可达属性，Snowflake 须先在 DIMENSIONS 中显式声明，dbt 也须先声明语义模型维度；Snowflake 和 dbt 可在有效连接路径上使用已声明维度，不代表所有可达物理列自动成为维度。

我们的 time_field 与 dbt 的 agg_time_dimension 在归周期的用途上相近，core-1 允许不填，dbt 对定义指标的模型要求时间维度和默认时间轴。我们只在数据集上声明快照，不在指标上声明；dbt 在旧 measure 或新 simple metric 上、Snowflake 在 metric 上、Databricks 在 measure 的窗口中声明相应时间聚合规则。core-1 的数据集声明也供实例浏览使用，混入快照表的事件列应拆到每日增量表。


以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir [对象集合聚合 API](https://www.palantir.com/docs/foundry/api/ontology-resources/objects/aggregate)支持聚合与分组；与 core-1 同构的独立指标资源未核实，不能把 API 调用当作本平台 Metric 的字段映射。

Fabric [操作文档](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-metrics)展示源 DAX（Data Analysis Expressions，用于分析计算的数据分析表达式）measure 的代理；[定义协议](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition)还提供 explicit Metric 自有 expression，支持 SQL、KQL（Kusto Query Language，用于日志和分析查询的 Kusto 查询语言）等方言。不能概括为只能引用源 DAX，也不能据此推导其有 core-1 的 simple/ratio 字段。

Ossie [开放语义交换规范 OSI（Open Semantic Interchange）中的指标 Metric，用于交换计算定义](https://github.com/apache/ossie/blob/main/core-spec/spec.yaml)以表达式保存。适配器识别固定聚合、CASE 与 CAST/NULLIF 比率，其余保留 expression；只转换已解析引用，保持常量、分隔符、NULL 和业务算法。
