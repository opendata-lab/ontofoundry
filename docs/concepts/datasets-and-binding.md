# 数据集与绑定

[概念概览](README.md) · [主设计文档 §3.7、§14.3](../design/2026-10-14-core-model-and-format-adapters.md) · [数据集两种来源设计](../design/2026-10-20-dataset-sources.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 1. 概述

客户名称在 customers 表，信用额度在 customer_credit 表。数据集登记分别说明两张表在哪里；绑定再说明客户的名称取哪列、额度取哪列，并按客户键横向补齐。这让业务定义不必重复保存物理表位置。

数据管理里有两种底层数据：数据表（表和视图，经全量同步或指定表同步后才算登记）和文档（材料）。平台只使用已登记的数据表。数据集是建立在已登记数据表上的本体元素，有两种来源：

| 来源方式 | 定义 | 例子（虚构） |
|---|---|---|
| 基于表 | 选择一张已登记的表或视图 | 订单 → `retail.orders` |
| 基于表达式 | 一条只读 SELECT，允许 CTE、JOIN、UNION（不支持递归 CTE），只能引用同一连接中已登记的表或视图；保存时探测输出列 | 销售与退款事件 → `orders` 中已完成订单与 `refunds` 用 UNION ALL 合并，各带业务日期 |

数据集直接记住所属连接（`connection_id`），与表位置或 SQL 一起保存。导出文件不带连接 id，只在扩展文件里带连接名称作为提示；导入到其他环境时按名称唯一匹配本地连接，匹配不到时为“未绑定连接”，审阅时选择。

建模会话可以关联已登记的数据表（构建页“选择数据表”）。建模助手只看到关联表的目录，按需读取列，并在这些表上提议数据集；材料提到但尚未同步的表也可提议，审阅时显示“表未同步”，需先同步或修改连接和表才能接受。

数据集是登记单位，背后可以是表、视图或只读查询；指标只引用单个数据集的列，不关心其物理形态。分子分母来自不同表的口径（例如退款率）先建基于表达式的数据集，再在其上建单数据集指标，不在指标里连接多张表。要读取已知表或视图时登记 Dataset，再用 DataMapping 将属性与列连接。同一数据集可被多个对象、关系或数据集指标复用，列清单是元数据副本，不会自动成为属性。两张表各存一半客户时不能当作主表和附表拼接；本期主表决定实例集合，普通纵向合并不在范围内。所有指标均直接引用登记数据集列，无须对象绑定。simple、ratio、expression 均只引用自己的 dataset_id 所指数据集的列；模型没有数据集之间的关系，指标不依赖本体。

新建指标只在所选数据集的列中选择，包括表达式和时间字段。用户问题涉及其他数据集条件时，由 agent 查询时沿本体关系筛选，不写入指标定义。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `Dataset.id` | UUID | 必须提供。 | 这是数据集登记的稳定身份，所有来源引用使用此 id。 |
| `Dataset.name` | 字符串 | 必须提供，ASCII 英文标识。 | 这是模型内唯一的数据集英文标识，界面称“英文标识”。 |
| `display_name` | 字符串 或 null | 可以为空。 | 中文名称，界面称“名称”，为空时显示英文标识。 |
| `connection_id` | 字符串 或 null | 接受和保存时必须指向本空间的数据连接；待审阅提案中可以为空。 | 数据集所属连接。导出时去掉，只保留连接名称提示。 |
| `source_kind` | `table` 或 `query` | 默认 table。 | 来源方式：基于表或基于表达式。 |
| `dialect` | 字符串 或 null | 引擎不明时可以为空，并标为待补全。 | 此字段说明数据库引擎，例如 mysql、doris 或 postgresql，须与所属连接一致；不能从 ANSI_SQL 推断引擎。 |
| `schema_name` | 字符串 或 null | 基于表时可以为空，基于表达式时必须为空。 | 来源命名空间，留空时使用连接的默认库或 Schema。 |
| `table_name` | 字符串 或 null | 基于表时必须提供，基于表达式时必须为空。 | 已登记的表名或视图名。 |
| `query_sql` | 字符串 或 null | 基于表达式时必须提供（不超过 64 KiB），基于表时必须为空。 | 一条只读 SELECT，只能引用已登记的表或视图。平台不判断连接后是否重复计算，审阅时人工核对连接粒度。 |
| `description` | 字符串 | 可以省略。 | 此字段解释业务含义、范围和必要上下文。 |
| `snapshot_date_column` | 字符串 或 null | 只给每日全量快照表填写（每行是某天的状态，常见后缀 `_df`）；增量分区表和事件表留空。 | 此字段指定快照日期列。填写后，每周期按该数据集最后有数据的日期选行，实例浏览默认只取最新一天。见[时间与快照](time-and-snapshots.md)。 |
| `columns` | 数组 或 null | 可以为空或省略；用于列指标但清单为空时标为待补全。 | 此数组保存列的元数据副本，每项分别说明列名、物理类型与注释：基于表的来自同步登记，基于表达式的来自保存时的探测；空清单不证明未知列存在。 |

### 对象绑定

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `DataMapping.id` | UUID | 必须提供。 | 这是该对象绑定的稳定身份。 |
| `DataMapping.type_id` | UUID | 必须提供。 | 此字段引用绑定所属的业务对象。 |
| `binding_mode` | 枚举 | 有绑定父对象的子绑定必须为 shared_parent；独立绑定用 independent。 | independent 表示独立来源，shared_parent 表示沿用有绑定父对象的来源。 |
| `sources` | 数组 | 必须提供。 | 此数组按局部来源名引用数据集与有序键，共享父绑定仅列本地新增来源。 |
| `fields` | 属性英文标识到绑定的映射 | 必须提供。 | 此映射按属性英文标识保存绑定；列绑定指定来源与列，计算绑定保存同行表达式。 |
| `membership_source_id` | 字符串 或 null | 以扩展记录定义成员时必须填写，否则为空。 | 此字段引用本层扩展来源，声明扩展记录存在是成为子对象成员的依据。 |
| `inherited_link_bindings` | 关系 id 到 DataJoin 的映射 | 可省略，默认空映射。 | 此映射供虚拟父的具体子对象为继承关系配置本地绑定，关系定义仍沿用原 id。 |


## 3. 例子

以下片段为订单登记两张表，并把金额绑定到拼接后的同行计算。订单类型及属性沿用[概览模型](README.md)；假设 orders 中有 quantity 列、order_prices 中有 unit_price 列，且两表每个 order_id 各一行。

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
      "snapshot_date_column": null
    },
    {
      "id": "00000000-0000-4000-8000-000000009101",
      "name": "order_prices",
      "dialect": "mysql",
      "schema_name": "dw",
      "table_name": "order_prices",
      "description": "每个订单一行的成交单价补充表。",
      "snapshot_date_column": null
    }
  ],
  "mappings": [
    {
      "id": "00000000-0000-4000-8000-000000007002",
      "type_id": "00000000-0000-4000-8000-000000001002",
      "fields": {
        "order_no": {
          "kind": "column",
          "source_id": "main",
          "column": "order_id"
        },
        "amount": {
          "kind": "expression",
          "expression": "main.quantity * prices.unit_price"
        },
        "status": {
          "kind": "column",
          "source_id": "main",
          "column": "status"
        },
        "ordered_at": {
          "kind": "column",
          "source_id": "main",
          "column": "created_at"
        }
      },
      "binding_mode": "independent",
      "sources": [
        {
          "id": "main",
          "key_columns": [
            "order_id"
          ],
          "dataset_id": "b7cc4307-1928-522c-a58b-921b2b697d75"
        },
        {
          "id": "prices",
          "dataset_id": "00000000-0000-4000-8000-000000009101",
          "key_columns": [
            "order_id"
          ]
        }
      ],
      "membership_source_id": null,
      "inherited_link_bindings": {}
    }
  ]
}
```

agent 可将金额属性读取为：

```sql
SELECT o.order_id, o.quantity * p.unit_price AS amount
FROM dw.orders AS o
LEFT JOIN dw.order_prices AS p ON o.order_id = p.order_id;
```

附表缺行时订单仍存在，amount 可能为空；附表独有的订单号不会创建新订单。数据映射页的数据集登记和本体映射总览均引用这份结构。

后续功能（原型阶段确认）：数据集页面分开显示“被 N 个对象、K 个关系、M 个指标引用”，三类可分别展开查看引用者。N 从 DataMapping 的主来源、附表、成员扩展来源推导，按对象 type_id 去重；同一对象通过多个来源引用同一数据集时只计一次。K 从关系绑定的映射表数据集推导（含继承关系的本地绑定），按关系 id 去重，不计入 N；同一关系在多个本地绑定中引用同一数据集时只计一次。M 从指标 dataset_id 推导，ratio 从两个 simple 分量解析数据集，按指标 id 去重，ratio 自身也计一个指标。数量与列表按现有权限展示并实时推导，不新增字段，不在三部分交付内，详见主设计 §8A、§9。

## 4. 建模建议

| 来源 | 客户编号 | 值 |
|---|---|---|
| customers | C-1 | 姓名：小林 |
| customers | C-2 | 姓名：小周 |
| customer_credit | C-1 | 额度：100 |

正例：以 customers 为主表，信用表补属性，得到 C-1 额度 100、C-2 额度为空，仍有两个客户。

反例：把仅在信用表中的 C-3 当作主表客户，查询不会自动得到第三个实例；需要重新说明来源范围。

正例：客户主表保存全部客户，信用补充表只提供额度；用同一客户键横向拼接。反例：把两张各存一半客户的表配置成主表和附表，附表独有实例会消失。普通纵向合并不在本期绑定范围。

一个对象可以有二十多张不同窗口或快照来源，不人为限制为很少几张；每个属性只能有一个绑定，不能让多个来源争用同一个属性。汇总表可以登记成独立数据集，直接在其上建数据集指标；查询时用不用汇总表由 agent 决定。

先明确数据集，再绑定业务属性。数据目录里出现一列不等于应自动创建同名属性。dialect 不明时留空并补全，不能从 ANSI_SQL 推断为 mysql。

独立绑定固定以 main 为主来源，不能取 sources 的首项；shared_parent 沿用父主来源。派生条件放在对象定义上，不引用物理列；同时有成员扩展来源时二者共同限定成员。

删除数据集或列、调整来源位置和快照声明时，列出直接引用与 ratio 间接依赖的指标，相关修订归同一依赖组。范围保持的来源搬迁只更新 SQL 参考，不能确认等价则列潜在影响，不扫描数据证明等价。对象成员、继承、属性或关系定义的变化不触发指标定义修订。

Ossie Dataset 临时 id 使用 uuid5(workspace_id, "ossie:" + 键)，键为 `dataset:{外部OntologyMap作用域}:{原dataset名}`；作用域优先唯一声明名，重复或缺失时用源定位或序号消歧并报告，不依赖临时名称后缀。映射在对象 id 重写后按 type_id 一对一匹配，尊重 UUID 首轮锁定，避免一对象多映射。

## 5. 校验与限制

数据集名称和 id 唯一，所有 dataset_id 引用存在。来源局部 id 不重复，新增子来源不能遮蔽有效祖先来源。主附来源在同一连接，非空键的列数与顺序一致；平台校验声明，不扫描唯一性或实例覆盖。

空键可保存为未完成绑定，但不得生成 JOIN 参考。缺少列清单不等于表没有列，未知列应标为待核对。元数据采集 id 和时间由服务端投影附带，不写成用户自己伪造的采集事实。

同行表达式不引用其他对象、不含聚合/窗口/子查询、不依赖另一个计算属性。跨连接联邦和普通纵向映射继续延期。连接凭据与连接登记留在平台配置中，不进入 Dataset 或 MCP 合同。

数据集、表、列、数量与说明都受 can_read_mappings 控制；来源解析歧义是错误，不能向 agent 增加 connection_alias 绕过。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir [创建对象](https://www.palantir.com/docs/foundry/object-link-types/create-object-type)选择 backing datasource；[多数据源对象 MDO（Multi-Datasource Objects，用于按列组合来源）](https://www.palantir.com/docs/foundry/object-permissioning/multi-datasource-objects)支持按列补充的多来源，当前不提供 row-wise MDO。本平台主表决定范围是自己的明确约定，不假定缺失键行为完全相同。

Fabric [Data binding](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-bind-data)连接业务定义和来源。该操作页的 primary/secondary 与单 static 限制表述并存，完整可用组合未核实，不承诺与本平台同构。

Ossie [本体映射](https://github.com/apache/ossie/blob/main/ontology/ontology.md#ontology-mappings)引用语义模型字段。适配器保留数据集一一对应，折叠可识别绑定；任意来源查询无法登记为表位置时 RT-63 报 error，不把查询伪装成 table_name。
