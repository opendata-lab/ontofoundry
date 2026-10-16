# 查询语义

[概念概览](README.md) · [主设计文档 §14](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 1. 概述

用户问“本月销售额最高的客户”，agent 先读取销售额口径、订单到客户的关系和授权来源，再让数据库按客户聚合。MCP 提供这些定义与来源信息，结构化指标可带基础 SQL 参考，完整查询由 agent 组织。

新建指标表单的数值预览由平台编译当前完整定义，经白名单检查后在已登记连接上只读执行，不经过 DataAgent；这是界面自查能力，不改变 MCP 只提供语义的分工。

需要查业务库时使用授权绑定和 agent 的数据库工具；需要找材料里记录的退货单时使用文档事实工具。不能用文档事实翻页代替数据库聚合，也不能从被裁剪的表达式旁路获取表名。版本由服务端解析：建模固定版本，问数取当前发布版本；agent 不传 version_id 自选版本。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `search_ontology.query` | 字符串 | 检索时必须提供。 | 此字段按名称与同义词搜索本体元素和指标。 |
| `search_ontology.kinds` | 种类数组 | 可以省略。 | 此字段将候选限定到指定元素种类。 |
| `get_ontology.ids` | UUID 数组 | 可以省略，不能传空数组。 | 省略时返回轻量目录和数量，非空数组用于批量读取指定定义。 |
| `get_ontology.kinds` | 种类数组 | 可以省略。 | 此字段限定返回的元素种类。 |
| `get_ontology.include` | 投影数组 | 可以省略，默认 semantic。 | 此字段选择 semantic、physical、rules 或 adjacency，返回内容仍受权限裁剪。 |
| `search_objects.type_id` | UUID | 可以省略。 | 此字段指定要检索的文档事实类型，父对象范围按继承规则展开。 |
| `search_objects.q` | 字符串 | 可以省略。 | 此字段提供文档事实检索词，不查询业务数据库。 |
| `get_object.id` | UUID | 必须提供。 | 此字段按 UUID 引用要读取的已接受文档对象事实，不按业务标识合并。 |
| `get_object.include` | 投影数组 | 可以省略。 | 此字段选择文档事实的属性、证据或直接邻接内容，仍受实例权限约束。 |
| `cursor` | 字符串 | 四工具均可省略；翻页时使用上次响应值。 | 此字段携带签名分页位置，失效时须重新读取，不混用模型版本。 |
| `limit` | 整数 | 四工具均可省略，默认 20，最大 100。 | 此字段控制一页数量，响应仍受内容预算限制。 |
| `workspace_id` | UUID | 响应由服务端提供。 | 此字段说明当前授权工作空间。 |
| `version_id` | UUID | 响应由服务端提供。 | 此字段记录服务端解析的模型版本，agent 不可用它指定请求版本。 |
| 物理投影 `dialect` | 字符串 | 授权且来源可定位时返回。 | 此字段说明数据库引擎方言，供 agent 选择查询工具。 |
| 物理投影 `database` | 字符串 | 授权且来源可定位时返回。 | 此字段给出服务端解析出的数据库名称。 |
| 物理投影 `schema` | 字符串 | 授权且来源可定位时返回。 | 此字段给出来源所在的命名空间。 |
| 物理投影 `table` | 字符串 | 授权且来源可定位时返回。 | 此字段给出登记的物理表名。 |
| `binding_status` | 状态 | 属性或关系的物理投影中返回。 | 此字段说明绑定是否就绪，以及缺键、跨连接、元数据过期或无权限等原因。 |
| `data.status` | 状态 | 对象的物理投影中返回。 | 此字段说明对象来源是否就绪，未绑定或无权限时返回对应状态。 |
| `sql_reference` | 参考对象 | 结构化指标来源与引用就绪且获授权时可返回，否则省略并解释原因。 | 此对象给出就绪结构化指标的参考 SQL、字面量参数、方言、数据库和说明。 |
| `next_cursor` | 字符串 或 null | 响应由服务端提供。 | 此字段保存签名分页位置，绑定版本、筛选和权限上下文；没有后页时为空。 |


search_objects 按已接受事实的 UUID 返回，保留实际 type_id；父类型范围按继承展开，仅对同一 UUID 去重。不同 UUID 的同业务标识事实分别返回，分页和数量按事实条目计算。get_object 只返回指定 UUID 的属性、证据与直接邻接。需要业务实体数量时另按完整业务标识统计去重，并说明缺标识事实如何处理；提案审阅的重复提示与人工选择见[证据与实例](evidence-and-instances.md)。

## 3. 例子

下面是按主设计 §14.3 给出的授权物理投影示意，省略的其他对象和属性应通过后续分页读取；该片段本身是完整 JSON，不是新的持久化格式或所有响应字段的封闭 schema。

```json
{
  "workspace_id": "11111111-1111-4111-8111-111111111111",
  "version_id": "22222222-2222-4222-8222-222222222222",
  "elements": [
    {
      "kind": "object_type",
      "id": "00000000-0000-4000-8000-000000001002",
      "technical_name": "sales_order",
      "description": "订单按既定指标口径统计。",
      "extends": null,
      "child_types": [],
      "title_property_id": "00000000-0000-4000-8000-000000002011",
      "data": {
        "status": "bound",
        "dialect": "mysql",
        "database": "dw",
        "sources": [
          {
            "id": "main",
            "dataset_id": "b7cc4307-1928-522c-a58b-921b2b697d75",
            "key_columns": [
              "order_id"
            ],
            "dataset": {
              "id": "b7cc4307-1928-522c-a58b-921b2b697d75",
              "name": "orders",
              "dialect": "mysql",
              "database": "dw",
              "schema": "dw",
              "table": "orders",
              "snapshot_date_column": null
            }
          }
        ]
      },
      "properties": [
        {
          "id": "00000000-0000-4000-8000-000000002012",
          "technical_name": "amount",
          "value_kind": "decimal",
          "binding": {
            "kind": "column",
            "source_id": "main",
            "column": "amount"
          },
          "physical_type": "decimal(12,2)",
          "binding_status": "bound"
        }
      ],
      "links": []
    }
  ]
}
```

用户问“订单总金额”，agent 先找到订单金额指标并读取授权绑定，确认固定聚合为 sum、没有固定过滤，然后选择 mysql.query，传入 database=dw 和下列 SQL：

```sql
SELECT SUM(o.amount) AS order_amount FROM dw.orders AS o;
```

如果用户问“销售额最高的客户”，agent 再读取订单到客户的关系，按客户分组并让数据库排序与限制返回行数。仅有本体目录还不足以生成物理 SQL，绑定受限或未完成时须说明缺少什么。

## 4. 建模建议

| 订单号 | 客户编号 | 金额 |
|---|---|---|
| O-1 | C-1 | 100 |
| O-2 | C-1 | 50 |
| O-3 | C-2 | 80 |

正例：读取指标与授权绑定，让数据库聚合得到 C-1=150、C-2=80，最高者为 C-1。

反例：只用文档事实工具发现 O-3，就回答 C-2 最高，会漏掉业务库订单；检索范围不能代替统计范围。

1. 搜索对象、关系与指标，读取所需定义及授权物理投影；记录 version_id，不能混用不同发布版本。
2. 有已定义指标时保持其固定算法与条件。ratio 分子分母分别按各自 time_field 归周期并过滤，总计重新相除，ratio 自身不存时间字段；expression 保留算法、字面量和 NULL 行为。
3. 理解实例范围。有绑定父对象查完整父范围，子对象逐级应用父范围和本层派生条件，并与成员扩展来源取交集；虚拟父递归展开具体实例来源，不虚构父表。
4. 按[时间与快照](time-and-snapshots.md)的计算规则处理：快照数据集每周期取最后有数据的一天，其他数据集取周期内全部行，再按指标算法整体重算；普通主表和快照附表的列各按所在表声明处理；查询快照对象的实例明细时默认只取最新一天。每个快照数据集独立选日，同一数据集不按地区或实例另取最近记录；日期不齐与空周期由 agent 处理并说明。
5. 所有指标只用自己的数据集列，不返回对象归属。用户问“华东区订单金额”时，读取 orders 上的订单金额，agent 查询时沿订单到客户的本体关系筛选客户地区；这是查询行为，不是指标定义。查询连接有歧义时处理或澄清，并注意重复行放大聚合，不能为此在指标中保存连接。
6. 根据 dialect 选择现有查询工具，聚合留在数据库。mysql 与 doris 分别使用 mysql.query、doris.query；其他引擎只有 agent 配备相应工具才可执行。

正例：先读取指标，再根据问题增加月份范围或地区分组。反例：为让 SQL 看似可运行，删除指标中无法理解的条件，或从无物理权限的 expression 原文读取表名绕过权限。

文档事实读取时依次用有效标题属性值、完整业务标识元组、可见非空材料 quote 的前 80 个字符、事实 UUID 推导 display_text。null 和空字符串无显示值，0 和 false 有值；标识按属性 UUID 顺序，缺任一项就跳过整组；多个 quote 按证据 UUID 顺序取首项，截断只影响显示。只有人工 note 或无可见引文时继续回退 UUID。UI 与 MCP 的 display_text 只读，不写入核心；搜索覆盖推导显示文本和属性值。数据库实例仍按标题、完整标识、物理键回退。

MCP 返回 simple、ratio 的只读推导 value_kind，ratio 的 dataset_id 从同数据集分量解析；这些不是原生输入字段。指标只带数据集，不带对象归属。对象语义独立返回 derived_by 及其 id 依赖。

删除数据集或列、调整来源位置和快照声明时，列出直接引用与 ratio 间接依赖的指标，相关修订归同一依赖组。范围保持的来源搬迁只更新 SQL 参考，不能确认等价则列潜在影响，不扫描数据证明等价。对象成员、继承、属性或关系定义的变化不触发指标定义修订。

单个数据集上的指标导出与 OSI 一一对应，只转换本数据集的已解析列，保留算法、字面量和 NULL 行为；无法合法输出时本项 error，不能静默改写。超出单数据集表达式边界的 OSI 指标首版不承载，按 RT-69 原文留转换报告并标待补全，用户可改写为单个数据集上的指标。

## 5. 校验与限制

四工具均无 version_id 入参。ids=[] 报 invalid_arguments；limit 默认 20、最大 100，批量 ids 最多 100。嵌套属性、规则和邻接也分页；响应预算 256 KiB，超限在元素边界分页，单项过大提供可分段字段，不能无标识截断。

问数期间发布变化使旧 cursor 报 cursor_invalid，须重新读取当前版本依赖；建模固定版本不随发布变化。版本被清理报 version_unavailable。分页绑定权限上下文，权限变化不能沿用旧授权数据或缓存。

无 can_read_mappings 时，不返回 Dataset 名称、说明、列清单、数量、位置、JOIN 或 SQL 参考，物理投影标为 forbidden；含来源 SQL 的表达式也裁剪。无 can_read_instances 不检索事实和证据。

Dataset 的 schema_name 为空时由服务端解析默认值，无法唯一定位则未完成；同方言同 database 指向多集群的歧义由来源配置收敛，不返回 connection_alias。平台不校验真实运行基数或物理类型转换，参考 SQL 不等于完整查询编译器。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir [对象聚合 API](https://www.palantir.com/docs/foundry/api/ontology-resources/objects/aggregate)可直接执行对象集合聚合；本平台 MCP 只提供语义，执行由 agent 的独立查询工具完成，不宣称合同等价。

Fabric [Data Agent 来源文档](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-add-datasources)描述以业务上下文及来源组织查询，方向相近；其工具、权限和版本合同与 core-1 的四工具逐项对应未核实。

Ossie [本体与映射](https://github.com/apache/ossie/blob/main/ontology/ontology.md)是可交换的语义描述，不定义本平台四个 MCP 工具的授权、分页或版本机制；同构服务端 API 未核实。
