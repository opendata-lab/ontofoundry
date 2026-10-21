# 继承

[概念概览](README.md) · [主设计文档 §3.2、§3.7、§5.5](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 1. 概述

VIP 客户仍然是客户，所以它沿用客户编号、名称和客户已有的关系，只补充自己的定义。继承表达这种实例包含关系；继承项保持原 id 和归属，界面只读展示来源。

只有每个子实例都属于父对象时才使用继承。先判断父表是否覆盖全部子实例：覆盖时共享父绑定并声明成员筛选；父对象没有自己的来源时，可作为具体子对象实例并集的虚拟父。两个对象只是都有“名称”字段，并不足以建立继承。core-1 只允许单父，不用多父继承表达多个独立分类。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `ObjectType.extends` | UUID 或 null | 使用继承时必须填写，不继承时为空。 | 此字段引用唯一父对象，只有实例确实包含于父对象范围时才使用继承。 |
| `ObjectType.derived_by` | DerivedBranch 数组 | 可省略，默认空数组。 | 本层成员条件，非空分支取并集，与成员扩展记录同时限定；具体形状见下文。 |
| `binding_mode` | 枚举 | 有绑定父对象的子绑定必须为 shared_parent；独立绑定用 independent。 | independent 表示独立来源，shared_parent 表示沿用有绑定父对象的来源。 |
| `membership_source_id` | 字符串 或 null | 以扩展记录定义成员时必须填写，否则为空。 | 此字段引用本层扩展来源，声明扩展记录存在是成为子对象成员的依据。 |
| `sources` | 数组 | 绑定中必须提供，可为空数组。 | 此数组按局部来源名引用数据集与有序键，共享父绑定仅列本地新增来源。 |
| `fields` | 映射 | 绑定中必须提供，可为空映射。 | 此映射按属性英文标识保存绑定；列绑定指定来源与列，计算绑定保存同行表达式。 |
| `inherited_link_bindings` | 映射 | 可省略，默认空映射。 | 此映射供虚拟父的具体子对象为继承关系配置本地绑定，关系定义仍沿用原 id。 |
| 继承的业务标识 | 解析所得 | 这是继承解析结果，不是另一个持久化字段。 | 父对象已有标识时，子对象沿用它，不能新增标识属性扩大元组。 |
| 继承的实例标题 | 解析所得 | 标题由对象的 title_property_id 选择。 | 子对象可以选择祖先定义的属性作为实例标题，不复制属性定义。 |


## 3. 例子

下例完整列出父、子对象与父属性、数据集、两份绑定。成员条件引用父属性 level 的 id，物理绑定单独指向 customer_level 列。

```json
{
  "object_types": [
    {
      "id": "00000000-0000-4000-8000-000000001001",
      "display_name": "客户",
      "name": "customer",
      "description": "与公司签约的企业客户",
      "synonyms": [
        "顾客",
        "买方"
      ],
      "tags": [
        "核心"
      ],
      "extends": null,
      "evidence": [],
      "title_property_id": null,
      "derived_by": []
    },
    {
      "id": "00000000-0000-4000-8000-000000009103",
      "display_name": "VIP客户",
      "name": "vip_customer",
      "description": "父客户范围内等级为 VIP 的成员。",
      "synonyms": [],
      "tags": [
        "核心"
      ],
      "extends": "00000000-0000-4000-8000-000000001001",
      "evidence": [],
      "title_property_id": null,
      "derived_by": [
        {
          "kind": "simple",
          "conditions": [
            {
              "path": {
                "links": [],
                "property_id": "00000000-0000-4000-8000-000000009102"
              },
              "operator": "eq",
              "values": [
                "VIP"
              ]
            }
          ]
        }
      ]
    }
  ],
  "properties": [
    {
      "id": "00000000-0000-4000-8000-000000002001",
      "owner_type_id": "00000000-0000-4000-8000-000000001001",
      "display_name": "客户编号",
      "name": "customer_no",
      "description": "",
      "value_kind": "string",
      "required": true,
      "identifier": true,
      "unique": true,
      "synonyms": [],
      "evidence": []
    },
    {
      "id": "00000000-0000-4000-8000-000000002002",
      "owner_type_id": "00000000-0000-4000-8000-000000001001",
      "display_name": "客户名称",
      "name": "name",
      "description": "",
      "value_kind": "string",
      "required": true,
      "identifier": false,
      "unique": false,
      "synonyms": [
        "客户名"
      ],
      "evidence": []
    },
    {
      "id": "00000000-0000-4000-8000-000000002003",
      "owner_type_id": "00000000-0000-4000-8000-000000001001",
      "display_name": "所在地区",
      "name": "region",
      "description": "华东 / 华北 / 华南 / 西部",
      "value_kind": "string",
      "required": false,
      "identifier": false,
      "unique": false,
      "synonyms": [],
      "evidence": []
    },
    {
      "id": "00000000-0000-4000-8000-000000002004",
      "owner_type_id": "00000000-0000-4000-8000-000000001001",
      "display_name": "签约日期",
      "name": "signed_on",
      "description": "",
      "value_kind": "date",
      "required": false,
      "identifier": false,
      "unique": false,
      "synonyms": [],
      "evidence": []
    },
    {
      "id": "00000000-0000-4000-8000-000000009102",
      "owner_type_id": "00000000-0000-4000-8000-000000001001",
      "display_name": "等级",
      "name": "level",
      "description": "客户当前业务等级。",
      "value_kind": "string",
      "required": false,
      "identifier": false,
      "unique": false,
      "synonyms": [],
      "evidence": []
    }
  ],
  "datasets": [
    {
      "id": "bf62129a-8cb8-569a-806b-c8ae68eef7a0",
      "name": "customers",
      "dialect": "mysql",
      "schema_name": "dw",
      "table_name": "customers",
      "description": "虚构示例数据集。",
      "snapshot_date_column": null
    }
  ],
  "mappings": [
    {
      "id": "00000000-0000-4000-8000-000000007001",
      "type_id": "00000000-0000-4000-8000-000000001001",
      "fields": {
        "customer_no": {
          "kind": "column",
          "source_id": "main",
          "column": "customer_id"
        },
        "name": {
          "kind": "column",
          "source_id": "main",
          "column": "name"
        },
        "region": {
          "kind": "column",
          "source_id": "main",
          "column": "region"
        },
        "signed_on": {
          "kind": "column",
          "source_id": "main",
          "column": "signed_on"
        },
        "level": {
          "kind": "column",
          "source_id": "main",
          "column": "customer_level"
        }
      },
      "binding_mode": "independent",
      "sources": [
        {
          "id": "main",
          "key_columns": [
            "customer_id"
          ],
          "dataset_id": "bf62129a-8cb8-569a-806b-c8ae68eef7a0"
        }
      ],
      "membership_source_id": null,
      "inherited_link_bindings": {}
    },
    {
      "id": "00000000-0000-4000-8000-000000009104",
      "type_id": "00000000-0000-4000-8000-000000009103",
      "binding_mode": "shared_parent",
      "sources": [],
      "fields": {},
      "membership_source_id": null,
      "inherited_link_bindings": {}
    }
  ]
}
```

查 VIP 客户由 agent 应用成员条件：

```sql
SELECT c.customer_id, c.name
FROM dw.customers AS c
WHERE c.customer_level = 'VIP';
```

查全部客户只查父表，不把子查询再 UNION 回父表。该例符合 RT-67 时可导出以下 Ossie 子概念片段，回读保持父属性 level 的 id 引用，不依赖物理列名；parent 概念及属性定义在同一 Ossie 文档中。

```json
{
  "concept": "vip_customer",
  "type": "EntityType",
  "extends": [
    "customer"
  ],
  "derived_by": [
    "customer.level == 'VIP'"
  ]
}
```

## 4. 建模建议

| 客户编号 | 等级 |
|---|---|
| C-1 | VIP |
| C-2 | 普通 |

正例：客户父表覆盖两人，VIP 子对象筛选等级，父范围两人、子范围一人。

反例：把父表没有的 C-3 只存到独立 VIP 表，却声明共享父绑定，会遗漏父查询中的 C-3。

| 业务事实 | 选择 | 反例 |
|---|---|---|
| 客户表已含全部普通与 VIP 客户 | 有绑定父对象，子对象用 ObjectType.derived_by。 | 另建一张父表中不存在的 VIP 表，却仍声明共享完整父范围。 |
| 客户表含全部客户，VIP 扩展表仅有会员信息 | shared_parent，以 membership_source_id 指向扩展表。 | 普通附表有记录就自动视为 VIP，未声明成员用途。 |
| 设备与车辆各自有表，统一称为资产 | 无绑定虚拟父对象，具体实例只属于一个具体子类型。 | 给资产再绑一张不完整的父表，误称它覆盖全部设备和车辆。 |
| 两种业务只是字段相似 | 两个独立对象。 | 因都含“名称”就建立继承。 |

虚拟父对象查询递归列出具体子对象实例，保留 type_id 与实例键；SQL 编排交给 agent。不同具体类型的同名键不自动合并。角色和多维分类优先用属性或角色对象，不堆多父继承。

## 5. 校验与限制

继承单父无环，不能复制、覆盖或遮蔽继承定义。有绑定父对象的继承属性和关系仍从父绑定取；成员扩展表只引用父实例，不能创造父范围之外的实例。子成员条件或成员扩展来源都缺失时绑定未完成，不能默认取父表全部行。

虚拟父对象自身没有 DataMapping，不接受直接文档事实；普通无绑定叶对象仍是待补全。实例覆盖与具体子类型互斥由建模者声明，平台不扫描数据库证明。

ObjectType.derived_by 默认空数组，派生数组非空时 extends 必须非空。每项是 `{kind: simple, conditions: [...]}` 或 `{kind: expression, expression: "..."}`，conditions 与 expression 互斥；simple 非空条件列表按 AND，条件采用本体成员专用 PathCondition：`{path: {links: [{link_type_id, direction}], property_id}, operator, values}`；links 为空表示上下文属性，方向为 forward 或 reverse，路径须为标量，运算符和值类型按[主设计 §3.2](../design/2026-10-14-core-model-and-format-adapters.md)校验，与指标列条件独立。多条分支取并集，需要同时成立写在同一分支。空数组仅表示本层无条件，不等于成员定义完整。

引用从直接父对象的有效属性和关系解析到 id，可引用祖先定义，保留原 id。表达式支持受限标量、比较、布尔组合、算术、CASE、受限标量函数，另支持 `EXISTS (person.earns)` 的显式关系存在性；每跳保存关系 id 与 forward 或 reverse 方向，文字反向写作 `REVERSE(关系英文标识)`。同类不同角色以关系 id 区分，自关联同样保留方向。找不到关联与存在关联但属性为空有区别；不扩展到任意 SQL 子查询、聚合、递归或未定义的变量量化。文本按 AST 和 id 依赖重新生成显示，改英文标识不替换字面量，物理列改名不改变条件。

文档事实查询按已接受的 UUID 返回，继承展开只对同一 UUID 去重；不同 UUID 不因业务标识相同而合并。业务实体数量另按业务标识统计。Ossie 子类自有首选标识不能改变已有父标识，按 RT-68 报告损失并保留原文，子类单编号仍可作为普通 unique 属性。

每层先限定在父对象有效成员内，再应用本层分支并集；同时有 membership_source_id 时还必须存在扩展记录，即取交集。多层不得漏祖先条件。语义引用不依赖父物理绑定已就绪，缺列只影响问数就绪；普通 derivation Rule 是说明，不自动决定成员，同一条件不重复存 Rule。

能完整解析并等价输出的 Ossie 成员定义按 RT-67 converted；不能闭合的整个成员定义保留原文、归属和定位，error 待补全，不取可解析片段或覆盖已有定义。成员扩展来源及额外继承绑定的外部往返限制仍按 RT-57、RT-65 报告。

例：P1 年龄20、P2 年龄17、P3 年龄30，P1、P2 在东区，P3 在西区。成年人派生条件年龄>=18，东区成年人再限定地区=东区，扩展表即使含 P1、P2 也只得到 P1。若另一子类有年龄<18、地区=西区两个分支，则并集为 P2、P3，不能误作 AND。只有 P1 有薪酬链接时，关系 EXISTS 只选 P1。

Ossie 多父仅保留文件顺序第一个父类，报告其余父类以及因此不能闭合的继承引用和派生条件，原文留材料。可建议改写成派生条件或关系，但这是需用户审阅的业务改写，不保证等价，不自动生成关系。第二父自身的对象与定义仍可正常导入。

删除数据集或列、调整来源位置和快照声明时，列出直接引用与 ratio 间接依赖的指标，相关修订归同一依赖组。范围保持的来源搬迁只更新 SQL 参考，不能确认等价则列潜在影响，不扫描数据证明等价。对象成员、继承、属性或关系定义的变化不触发指标定义修订。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir 的 [Interface](https://www.palantir.com/docs/foundry/interfaces/interface-overview)为抽象公共形状，可跨实现类型使用；它不等于 core-1 具体对象的单父继承。

Fabric 的 [Inheritance](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-inheritance)支持单父和父查询包含直接子类，但不继承普通关系与绑定；其属性元数据允许部分覆盖，core-1 保持继承定义只读。

Ossie [derived concept](https://github.com/apache/ossie/blob/main/ontology/ontology.md#derivation-expressions)用父范围和表达式定义成员，概念层面可承载筛选子类。core-1 以对象派生条件保存本体语义；完整转换者可等价输出，未支持表达式按例外表保留原文待补全。
