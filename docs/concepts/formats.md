# 格式与转换

[概念概览](README.md) · [主设计文档 §4–7、§13.4](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 2026-10-20 命名与交换约定

对象、属性、关系、规则和指标统一使用必填 `name`（英文标识，`^[A-Za-z_][A-Za-z0-9_]*$`）和可选 `display_name`（中文名称）。名称为空时界面显示 name，名称可重复；英文标识沿用原命名空间与引用规则。Dataset 不变。关系的完整含义及角色名不变。旧数据库内容清理，不转换；旧外部文件由导入适配器转换并报告。

Ossie 导出为 ZIP：纯 Ossie 文件与 `ontofoundry-extension.json`。显示名仅在扩展 `display_names`；同义词在支持的位置用 `ai_context.synonyms`，概念和本体关系使用扩展 synonyms。单个 Ossie 文件导入显示名为空；旧版扩展块仅导入兼容。详见[命名统一设计](../design/2026-10-20-display-name-unification.md)。

## 1. 概述

把工作空间搬到另一个环境，需要连同证据材料一起保存，应选原生完整包。把业务结构交给使用 Ossie 的系统，则通过适配器导出，并查看哪些内容发生变化。这是备份与交换两种用途。

完整包承担平台定义与被引用材料的无损保存；单文件只带模型，缺材料可能丢证据。外部格式只交换可表达部分，不能代替完整备份。每项转换、损失和错误都出现在转换报告里；导入生成提案，经审阅和发布生效。Ossie 的本体、数据集和指标概念可采用，其交换文件结构不直接成为平台内部模型。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| 原生 `format` | 字符串 | 必须提供。 | 此字段固定为 ontofoundry，表示平台原生格式。 |
| `schema_version` | 字符串 | 必须提供。 | 此字段固定为 core-1，表示本文定义的模型版本。 |
| `exported_at` | 时间字符串 | 必须提供。 | 此字段记录导出的时间。 |
| 单文件 `draft` | 核心草稿对象 | 必须提供。 | 此对象保存全部核心集合与元素 UUID。 |
| 完整包 manifest 的 `materials` | 数组 | 必须提供。 | 此数组列出打包的被引用材料，每项分别记录身份、名称、哈希、字节数和包内路径。 |
| 报告 `id` | UUID | 必须提供。 | 这是本次转换报告的身份。 |
| 报告 `content_sha256` | 字符串 | 必须提供。 | 此字段标识预览产物内容，确认时必须使用同一内容。 |
| 报告 `direction` | 枚举 | 必须提供。 | 此字段说明转换方向为导入还是导出。 |
| 报告 `adapter` | 字符串 | 必须提供。 | 此字段标识执行转换的格式适配器。 |
| 报告 `counts` | 映射 | 必须提供。 | 此字段汇总各类转换结果的数量。 |
| 报告 `issues` | 数组 | 必须提供，可为空数组。 | 此字段列出每个需要说明的转换条目。 |
| 问题 `outcome` | 枚举 | 必须提供。 | 此字段记录 converted、dropped 或 error。 |
| 问题 `severity` | 枚举 | 必须提供。 | 此字段独立记录 info、warning 或 error 的严重度。 |
| 问题 `construct` | 字符串 | 必须提供。 | 此字段说明发生转换的源构造种类。 |
| 问题 `id` | UUID | 必须提供。 | 这是该问题的稳定身份。 |
| 问题 `rule_id` | 字符串或 null | Ossie 语义差异须有 RT 编号；通用解析、版本和原生证据错误可空。 | 为空时由适配器及 message 说明原因。 |
| 问题 `source_path` | 字符串 | 必须提供。 | 此字段定位源文件中的构造路径。 |
| 问题 `source_locator` | 对象 | 必须提供。 | 此字段保存材料身份、哈希、JSON pointer 和原文行号。 |
| 问题 `original` | 字符串 或 null | 没有可显示的原文时可以为空。 | 此字段保存供用户理解和补全的源内容。 |
| 问题 `target_path` | 字符串 或 null | 没有目标结构时可以为空。 | 此字段定位转换后的核心字段。 |
| 问题 `target_element_ids` | UUID 数组 | 必须提供。 | 此数组列出该问题涉及的核心元素 id。 |
| 问题 `completion_status` | 枚举 | 必须提供。 | not_needed 表示无需补全，available 表示有可补全事项；当前是否阻断从候选图与实际依赖实时推导，不持久化 blocked。 |
| 问题 `message` | 字符串 | 必须提供。 | 此字段用中文解释转换结果、风险或待补全内容。 |


## 3. 例子

单文件原生格式的完整包装可写为下例。空核心草稿在原生格式可表达；同一空草稿导出 Ossie 会报 error，因为没有业务对象。

```json
{
  "format": "ontofoundry",
  "schema_version": "core-1",
  "exported_at": "2026-10-15T08:00:00Z",
  "draft": {
    "schema_version": "core-1",
    "workspace_id": "11111111-1111-4111-8111-111111111111",
    "object_types": [],
    "properties": [],
    "link_types": [],
    "rules": [],
    "metrics": [],
    "datasets": [],
    "mappings": [],
    "material_objects": [],
    "material_links": []
  }
}
```

下面是一条 RT-67 转换问题示意，前提是父属性语义引用满足[继承页](inheritance.md)的全部条件。示意哈希用于说明形状，实际报告定位真实保存的导入材料。

```json
{
  "outcome": "converted",
  "construct": "Concept.derived_by",
  "id": "00000000-0000-4000-8000-000000009201",
  "rule_id": "RT-67",
  "severity": "info",
  "source_path": "/ontology/1/derived_by/0",
  "source_locator": {
    "material_id": "example_import",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "json_pointer": "/ontology/1/derived_by/0",
    "line_start": 20,
    "line_end": 20
  },
  "original": "customer.level == 'VIP'",
  "target_element_ids": [
    "00000000-0000-4000-8000-000000009103",
    "00000000-0000-4000-8000-000000009104"
  ],
  "completion_status": "not_needed",
  "target_path": "/object_types/1/derived_by",
  "message": "完整派生条件转换为父属性 level 的 id 引用；不依赖物理列名，未重复创建 Rule。"
}
```

导入弹窗按 outcome 分组并显示严重度。确认后进入会话，逐条或全部接受提案，再按正常发布流程处理冲突。导入只有一种方式：只新增和修改，文件中没有的已有元素保持不动，平台导入从不生成 delete 提案。要删除就在会话里手动操作，或让 agent 提删除提案并走正常审阅。转换不出来的条目保留原文、材料定位与待补全原因，等待用户选择或点击 AI 补全，满足核心校验后再形成新增或修改提案；对应已有定义保持不动。

## 4. 建模建议

| 待保存内容 | 所在位置 |
|---|---|
| 订单定义 | 模型草稿 |
| 定义依据 | 被证据引用的材料 |

正例：跨环境搬迁选完整包，带上模型和被引用材料，校验哈希后重建材料引用。

反例：只传单文件且目标没有相同哈希材料，定义可保留但相应材料证据会丢失，不能称无损备份。

需要备份或跨环境搬迁时选默认完整包 `*.ontofoundry.zip`，包含 manifest.json、draft.json 与所有被证据引用材料的原字节；未引用材料不打包。仅查看或同环境复制时可用 `*.ontofoundry.json`，但它不携带材料原文件。

完整包导入先校验材料哈希，按内容复用或重建材料，重写 material_id；人工证据保留原作者 id。单文件缺失材料时在目标按哈希寻找，找不到则丢对应证据并逐项报告，不能称无损。

Ossie 导入按英文标识匹配；原生导入先全量按 UUID 与种类锁定，再对未锁定双方按英文标识匹配，重写所有依赖。对象 id 重写后，未锁定映射按 type_id 一对一匹配，不能覆盖 UUID 锁定或产生一对象多映射；文档事实、链接与证据只按 UUID 匹配，不按业务号、名称或 quote 合并。

候选最终图统一校验，名字互换形成原子组。冲突及无法独立成立的反向依赖阻断，避免生成悬空提案。

正例：看到无法改写的值类型约束条目后，参考导入材料提出属性规则补全提案。反例：为了让报告没有 dropped，把不支持内容塞进 description 后宣称已恢复结构；说明可保留上下文，不能替代结构化字段。

## 5. 校验与限制

### 原生格式与报告

完整包才承担平台无损备份承诺；单文件不含材料，可能损失证据。哈希不一致整包拒绝。预览与确认引用同一 content_sha256，报告行号针对保存后的确定性格式化材料，不冒充上传字节的原行号。

outcome 为 converted、dropped、error；severity 为 info、warning、error。结构保留但有执行风险可为 converted + warning。目标必填信息不能推导时本项 error，不生成伪有效对象。输出须过官方 schema 与语义校验，但校验不证明执行等价。

通用错误如原生缺材料时 rule_id=null、outcome=dropped；JSON 无法解析或版本不支持时 rule_id=null、outcome=error，target_element_ids=[]，source_locator 只记录实际可取得的文件及行列，不伪造 JSON pointer。历史报告不随补齐依赖改写，AI 补全仍可发起；预览与确认使用同一产物与哈希。

以下两条是报告条目的完整形状，分别说明原生缺材料与文件解析错误：

```json
[
  {
    "outcome": "dropped",
    "construct": "Evidence.material",
    "id": "00000000-0000-4000-8000-000000009202",
    "rule_id": null,
    "severity": "warning",
    "source_path": "/draft/material_objects/0/evidence/0",
    "source_locator": {
      "filename": "example.ontofoundry.json",
      "json_pointer": "/draft/material_objects/0/evidence/0"
    },
    "original": "material_sha256: 3f1c…",
    "target_element_ids": [],
    "completion_status": "available",
    "target_path": null,
    "message": "原生单文件的材料在目标环境按哈希找不到，本条证据未导入；对象事实继续保留。"
  },
  {
    "outcome": "error",
    "construct": "JSON.parse",
    "id": "00000000-0000-4000-8000-000000009203",
    "rule_id": null,
    "severity": "error",
    "source_path": "invalid.json",
    "source_locator": {
      "filename": "invalid.json",
      "line": 1,
      "column": 2
    },
    "original": null,
    "target_element_ids": [],
    "completion_status": "not_needed",
    "target_path": null,
    "message": "JSON 解析失败，没有可用的元素路径；未生成核心提案。"
  }
]
```

### Ossie 的本期范围

| 构造 | 处理与边界 |
|---|---|
| 入口 | 现有 ontology.json 中 version=0.2.0.dev0 的内嵌 ontology_mappings；其他版本 error。新独立 mapping documents 不在本期范围。 |
| 实体、属性与二元关系 | 转核心定义；多父按文件顺序只留首个，值概念折叠；一元转布尔属性，多元转中间对象。 |
| identify_by | 全为属性且不改变已有父标识才整组转换；含关系或缺失引用则整组放弃并待补全；子类不同的首选标识按 RT-68 报损失、保留原文，单编号保留普通 unique 属性，不能拼接父身份。 |
| 非法输入 | 多元关系 OneToOne、实体继承值类型报输入 error，保留定位，不转换、不设计补全，不列作未承载的合法 Ossie 能力。 |
| 规则 | 可解析项转具体元素规则；角色语法不支持时保留原文报告。规则命名等不靠 Ossie 无损保存。 |
| Dataset | 所有条目一一登记，包括未引用者；导出每项一份，不按对象复制。任意 source query 不能表示表位置时报 RT-63 error。 |
| 绑定 | 识别单主身份、一层属性映射、可确认的星形多来源和同行表达式；深树、嵌套 referent 与歧义绑定逐项报告。 |
| 子类成员 | ObjectType.derived_by 完整解析并等价输出者 RT-67 converted，支持分支并集、逐层限定和关系 EXISTS；不能闭合整项 error 待补全。成员扩展及额外继承绑定仍 RT-57。 |
| Metric | 符合单数据集表达式边界的 OSI 指标与核心指标一一对应，只用本数据集字段；固定聚合与条件结构化，其余本数据集算法用 expression。ratio 仅复用已登记同数据集 simple，否则保留单条 expression；COUNT 可空列不转行计数，来源不明待选择。超出边界者按 RT-69 本项 error，原文及来源留转换报告并标待补全，不生成核心指标；用户可改写为单个数据集上的指标。 |
| 指标导出 | 单个数据集上的指标一一导出；simple 按本数据集列聚合，ratio 展开同数据集分量，expression 保持本数据集算法、字面量及 NULL 行为；来源、列未闭合或违反单数据集边界时报 RT-61 error，不因对象映射缺失丢指标。比率执行约定按 RT-58 报告。 |
| 快照、指标时间字段、方言与元数据 | 无同构字段时写说明并按 RT-60、RT-66 报结构损失，不从说明自动回读。键冲突或快照唯一性边界另按 RT-64。 |
| 文档事实与证据 | 不输出，逐项报告，使用完整原生包保存。 |
| 无可导出本体元素 | 空模型或只有数据集指标的模型均不满足当前 Ossie 的 ontology 最小项数，导出 error，不交付文件，不伪造对象；原生格式可保存。 |

导入指标只在登记数据集上使用列，不生成反查属性的 reference_bindings。逻辑字段只有定位到物理登记列才可按列结构化；计算字段不得伪装为列，原文及字段定义保留供补全。指标始终引用数据集列，不建立本体归属。未解析或超出单数据集边界的表达式原文保留报告待补全，不直接生成 expression 指标；新建规则引用不能解析则拒绝。AI 补全须由用户点击发起，在原会话生成提案，经审阅后接受；它不是导入时的隐式猜测。

首版未承载能力集中见[主设计 §7 例外表](../design/2026-10-14-core-model-and-format-adapters.md#首版不承载的-ossie-能力)，值类型独立域、多父、关系标识、读法、元组重化结构、映射和时间边界不能因原文留材料而称无损。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir [Export, edit, and import an Ontology](https://www.palantir.com/docs/foundry/ontology-manager/export-import)提供自己的导出编辑导入流程；本期尚无 Foundry 适配器，与本平台包格式的互读未核实。

Fabric [Ontology item definition](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition)使用自己的定义部件与 TMDL（Tabular Model Definition Language，用于描述表格语义模型的定义语言）等格式；本期尚无 Fabric 适配器，不宣称原生包兼容它。

Ossie [现行规范](https://github.com/apache/ossie/blob/main/ontology/ontology.md#mapping-documents)已将内嵌 ontology_mappings 标为弃用但继续接受，推荐独立 mapping documents。本平台本期只支持旧内嵌入口，版本号相同也不表示支持上游所有入口。
