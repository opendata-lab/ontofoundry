# 业务动作

[概念概览](README.md) · [业务动作定义设计](../design/2026-11-27-action-types.md)

本文说明 core-1 中的业务动作（`Action`）定义与边界。JSON 示例中的业务均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。

## 1. 概述

对象、属性和关系描述“业务里有什么”，规则描述“对象始终须满足什么约束”，而操作手册里还有另一类常见知识：“对工单能做哪些操作、要填哪些输入、满足什么前提、做完后哪些属性或关系会变”。业务动作把这类操作语义结构化地存进核心模型，供人和外部 Agent 查阅。

**首版只保存定义，不执行动作，也不绑定外部接口或 MCP 写工具。** 动作与其他核心元素一样经提案审阅、接受、按版本发布，并通过只读接口和 MCP 供下游消费。界面在动作旁固定标注“仅定义”。

动作分为两类：

- **实例动作**（`target_type_id` 指向某个对象类型）：作用于该类型的一个已有实例，例如对「工单」执行「派单」。挂在父对象上的动作沿单父继承链自动适用于子对象（例如「巡检工单」继承「工单」的「派单」），读取时推导，不重复存储。
- **全局 / 新建动作**（`target_type_id` 为 `null`）：不针对某个已有实例，例如「新建巡检工单」或全局通知类操作。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `id` | UUID | 必须提供。 | 稳定元素身份，改名不会改变它。 |
| `name` | 字符串 | 必须提供。 | 英文标识（`^[A-Za-z_][A-Za-z0-9_]*$`），工作空间内忽略大小写唯一。 |
| `display_name` | 字符串 / null | 可选。 | 中文名称；为空时界面显示 `name`。 |
| `description` | 字符串 | 可省略，默认空串。 | 业务说明、前提条件与影响范围。前提条件直接写在此处，不引用 `Rule`。 |
| `synonyms` | 字符串数组 | 可省略，默认空数组。 | 同义词，最多 50 项，供检索召回。 |
| `tags` | 字符串数组 | 可省略，默认空数组。 | 业务标签，最多 50 项。 |
| `target_type_id` | UUID / null | 可省略，默认 `null`。 | 指向目标对象类型；`null` 表示全局或新建动作。 |
| `parameters` | ActionParameter 数组 | 可省略，默认空数组。 | 调用时额外提供的标量输入，最多 50 项，保持声明顺序。 |
| `effects` | ActionEffect 数组 | 可省略，默认空数组。 | 声明受影响的属性、关系或对象类型，最多 50 项，保持声明顺序。 |
| `evidence` | Evidence 数组 | 可省略，默认空数组。 | 支撑该动作定义的材料或人工证据；无实例读取权限时读取投影会清空。 |

### 参数（`ActionParameter`）

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `name` | 字符串 | 必须提供。 | 英文标识，同一动作内忽略大小写唯一。 |
| `display_name` | 字符串 / null | 可选。 | 参数中文名。 |
| `description` | 字符串 | 可省略，默认空串。 | 参数说明，最多 200 字。 |
| `value_kind` | 枚举 | 必须提供。 | 沿用 core-1 七种标量基础类型；若指定 `value_type_id`，须与值类型基础类型一致。 |
| `value_type_id` | UUID / null | 可省略，默认 `null`。 | 可选引用共享[值类型](value-types.md)。值类型修改基础类型时，引用它的动作参数同步更新。 |
| `required` | 布尔 | 可省略，默认 `false`。 | 执行该动作时调用方是否必须提供此参数。 |

### 效果（`ActionEffect`）

效果按 `kind` 分为四种判别分支，只声明结构化引用和不超过 200 字的自然语言 `description`，不写公式或赋值表达式：

| `kind` | 引用字段 | 引用目标种类 | 说明 |
|---|---|---|---|
| `set_property` | `property_id` | `property` | 修改某属性（不限定属于目标对象，可跨关联对象）。 |
| `add_link` | `link_type_id` | `link_type` | 建立某二元关系。 |
| `remove_link` | `link_type_id` | `link_type` | 解除某二元关系。 |
| `create_object` | `object_type_id` | `object_type` | 新建某对象类型的实例。 |

## 3. 例子

以下示例展示一个实例动作（派单，含跨对象效果）和一个全局新建动作（新建巡检工单）：

```json
{
  "actions": [
    {
      "id": "10000000-0000-4000-8000-000000000021",
      "name": "dispatch_work_order",
      "display_name": "派单",
      "description": "只有待派单的工单可以派单，派单时必须指定受理班组。派单后工单由该班组受理，状态变为已派单，受理班组待办数加 1。",
      "synonyms": ["分派工单"],
      "tags": ["工单流转"],
      "target_type_id": "10000000-0000-4000-8000-000000000001",
      "parameters": [
        {
          "name": "team_code",
          "display_name": "受理班组编码",
          "description": "接收工单的运维班组编码",
          "value_kind": "string",
          "value_type_id": null,
          "required": true
        }
      ],
      "effects": [
        {
          "kind": "set_property",
          "property_id": "10000000-0000-4000-8000-000000000011",
          "description": "工单状态由待派单变为已派单"
        },
        {
          "kind": "add_link",
          "link_type_id": "10000000-0000-4000-8000-000000000015",
          "description": "建立工单与受理班组的受理关系"
        },
        {
          "kind": "set_property",
          "property_id": "10000000-0000-4000-8000-000000000012",
          "description": "受理班组待办工单数加 1"
        }
      ],
      "evidence": []
    },
    {
      "id": "10000000-0000-4000-8000-000000000022",
      "name": "create_inspection_order",
      "display_name": "新建巡检工单",
      "description": "在指定站点创建一张初始状态为待派单的巡检工单。",
      "synonyms": ["发起巡检"],
      "tags": ["工单流转"],
      "target_type_id": null,
      "parameters": [
        {
          "name": "site_code",
          "display_name": "站点编码",
          "description": "巡检目标站点编码",
          "value_kind": "string",
          "value_type_id": null,
          "required": true
        }
      ],
      "effects": [
        {
          "kind": "create_object",
          "object_type_id": "10000000-0000-4000-8000-000000000001",
          "description": "新建一张类型为巡检、状态为待派单的工单"
        }
      ],
      "evidence": []
    }
  ]
}
```

## 4. 建模建议

- **只从明确的操作制度建动作**：制度或操作手册明确写出操作名称、作用对象和结果时才建立动作；不要因为表里有 `status` 列就反推动作。
- **前提不写成对象规则**：对象规则（`Rule`）是实例始终满足的不变式；“仅待派单工单可派单”只适用于执行前瞬间，应写在动作的 `description` 中。
- **保留对象归属**：实例动作顺带修改关联对象（如派单同时更新班组待办数）时，仍应把 `target_type_id` 设为工单，并在 `effects` 中直接引用班组属性。
- **同关系先删后建合法**：“转派班组”可以对同一关系同时声明 `remove_link` 和 `add_link`，但不能声明两条完全相同的 `(kind, 引用 id)`。

## 5. 校验与限制

- 动作英文标识在工作空间内忽略大小写唯一；参数英文标识在同一动作内忽略大小写唯一。
- 所有引用（`target_type_id`、参数 `value_type_id`、效果引用 id）须指向存在且种类匹配的元素；删除仍被动作引用的元素会被拒绝，除非同批一起改绑或删除该动作。
- 首版动作只经提案增删改；审阅时 `parameters` 和 `effects` 与其他引用字段一样锁定，动作差异由服务端基于规范化前后的定义计算。
- Ossie 规范目前没有标准动作构造：导出 Ossie ZIP 时动作以自包含形式写入 `ontofoundry-extension.json` 的 `actions` 并逐条报告 `converted` + `warning`（单取纯 `.ossie.json` 会丢失）；仅含全局动作、没有对象类型的模型须用原生完整包往返。

## 6. 与同类产品的对照

| core-1 | Palantir Foundry | Microsoft Fabric IQ | Apache Ossie |
|---|---|---|---|
| 业务动作（仅定义，含标量参数与四种结构化效果） | [Action Type](https://www.palantir.com/docs/foundry/action-types/overview) 含参数、提交条件、效果规则并由写入引擎/Function/Webhook 执行。 | 本体中无动作概念，执行放在外部 Activator / Power Automate。 | 规范尚无动作；上游 [#106](https://github.com/apache/ossie/issues/106)（open）提议声明式 `actions` 与 `effects`，平台通过扩展文件承载。 |
