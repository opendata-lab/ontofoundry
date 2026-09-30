# `ontofoundry.proposals/v1` 结果合同（T1 评审交付物）

**日期：** 2026-09-30  
**状态：** 已实现；第一轮评审的 5 个 Critical 已修复，待复审  
**上位文档：** [Proposal-first 本体生命周期实施设计](./2026-09-26-proposal-first-ontology-lifecycle-implementation-design.md) §7、§T1

本文是 T1 评审门要求定稿的内容。权威来源是代码，本文只做说明：

| 内容 | 位置 |
|---|---|
| v2 元素模型 | `apps/api/src/ontofoundry_api/domain/models.py` |
| 结果解析与校验 | `apps/api/src/ontofoundry_api/contracts/proposals.py` |
| 生成的 JSON Schema（Draft 2020-12） | `apps/api/src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json` |
| 重新生成 Schema | `uv run python -m ontofoundry_api.contracts.export_schema` |
| 正例、反例与测试向量 | `apps/api/tests/test_t1_proposal_contract.py` |

Schema 由元素模型自动生成，测试 `test_checked_in_schema_matches_the_models` 保证检入的文件与模型一致。

## 1. 结果头部

```json
{
  "schema_version": "ontofoundry.proposals/v1",
  "run_token": "…",
  "workspace_id": "…",
  "session_id": "…",
  "base_version_id": "… | null",
  "base_version_sha256": "64 hex",
  "source_session_revision": 12,
  "source_draft_sha256": "64 hex",
  "items": []
}
```

头部七个字段必须与本次运行固定的上下文完全一致，否则整份拒收（`RESULT_CONTEXT_MISMATCH`）。`items` 最多 500 条。不允许任何额外字段。

## 2. 提案条目

| 字段 | 说明 |
|---|---|
| `client_ref` | 批次内唯一；create 必填，其他操作可选（用于被 `depends_on` 引用） |
| `operation` | `create` / `update` / `delete` |
| `target_kind` | `object_type` `property` `link_type` `rule` `action` `material_object` `material_link` `mapping` |
| `target_id` | create 为 `null`；update/delete 为固定草稿中已有元素的 id，且类型一致 |
| `expected_target_hash` | update/delete 必填，等于固定草稿中目标的 `element_sha256` |
| `before` | create 为 `null`；update/delete 为目标在固定草稿中的完整元素，必须逐字段一致 |
| `after` | delete 为 `null`；create/update 为该类型元素（见 §3） |
| `field_changes` | 仅展示用；应用和冲突判断只看 `before`/`after` |
| `evidence` | 条目级材料证据（例如删除理由的出处） |
| `depends_on` | 其他条目的 `client_ref` |
| `reason` | 给用户看的简短理由 |

同一批次内两个条目不能作用于同一目标（`TARGET_DUPLICATE`），也不能完全相同（`ITEM_DUPLICATE`）。

## 3. `after` 的结构

`after` 是对应 v2 元素去掉 `id` 后的结构（Schema 中的 `<kind>_after`），包括嵌套结构在内全部 `additionalProperties: false`。可省略的字段按元素模型的默认值补全：服务端对解析后的 `after` 执行模型校验，并以模型输出（`model_dump`）作为**唯一规范形态**存储和计算指纹，因此省略默认字段与显式写出默认值是同一个提案。update 的 `after` 是修改后的完整元素，可带 `id`，但必须等于 `target_id`。

**引用字段**可以写成固定草稿中已有元素的 UUID，或 `{"client_ref": "…"}` 指向本批次的一个 create 条目：

| 类型 | 引用字段 |
|---|---|
| object_type | `extends[]` |
| property | `owner_type_id` |
| link_type | `source_type_id`、`target_type_id` |
| rule | `owner_id` |
| action | `input_type_id`、`precondition_rule_ids[]`、`effects[].property_id`、`effects[].link_type_id` |
| material_object | `type_id` |
| material_link | `type_id`、`source_id`、`target_id` |
| mapping | `type_id` |

`client_ref` 引用会自动加入 `depends_on`。引用不存在的 client_ref（`CLIENT_REF_UNKNOWN`）、不存在的 UUID（`REFERENCE_UNKNOWN`）、依赖成环（`DEPENDENCY_CYCLE`）都整份拒收。跨元素的完整校验（名称唯一、继承环、映射字段、Action 表达式引用等）在接受时对应用后的完整草稿执行。

## 4. 服务端分配的标识

全部确定性，重试得到相同结果：

| 标识 | 算法 |
|---|---|
| 批次 id | `UUIDv5(session_id, "proposal-batch:" + run_token)` |
| create 目标 id | `UUIDv5(batch_id, "create:" + client_ref)` |
| 条目 id | `UUIDv5(batch_id, "item:" + ordinal)` |
| Action 参数、效果 id（未给出时） | `UUIDv5(target_id, "parameter:" / "effect:" + 位置)` |
| 材料证据 id（未给出时） | `UUIDv5(target_id, "evidence:" + 证据其余字段的规范化文本)` |

create 的目标 id 在接受前不写入身份登记表。

## 5. 证据

- 智能体只能产生 `kind=material` 证据。条目级 `evidence` 只接受材料证据（Schema 层拒绝人工证据），并经模型校验。同一元素内证据 id 必须唯一。
- 材料检查函数是解析的必填参数，解析时一定执行。
- `material_id` 必须属于本空间，`material_sha256` 必须与不可变材料一致，行号不能越界，`quote` 规范化空白后必须出现在对应行中；否则 `EVIDENCE_INVALID`。
- **人工证据回显规则**：update 的 `after` 可以、也必须原样带上 `before` 中已有的全部 `kind=manual` 证据。新增、修改或删除任何人工证据都整份拒收（`MANUAL_EVIDENCE_FORBIDDEN`）；create 不能带人工证据。
- **保存草稿同样执行这些规则**（`domain/evidence.reconcile_draft_evidence`）：新的或内容有变化的材料证据必须带正确的 `material_sha256` 并通过材料检查（`EVIDENCE_INVALID`）；新的人工证据由服务端写入录入人和时间，覆盖请求中的值；已保存的人工证据不能修改，他人录入的不能从仍存在的元素上删除（`MANUAL_EVIDENCE_IMMUTABLE`）。历史 v1 证据 `material_sha256` 为 `null`，只要原样保留就不受影响。

## 6. 提案指纹

```text
fingerprint = SHA-256( 算法B规范化 { "operation", "target_kind", "target_id", "after" } )
```

`after` 按单个元素规范化（集合字段去重排序、id 集合按 id 排序、`null` 省略键），为 `null` 时保留 `null`。测试 `test_fingerprint_and_domain_hash_vectors_never_change` 固定了三组向量（一个 create、一个 delete、空快照的 `normalized_snapshot_sha256`），任何规范化改动都会使它失败。

## 7. Action 表达式语言

- `effects[].expression` 是 ANSI SQL 文本，与 Ossie 的 `requires`/`derived_by` 同一语言，平台只保存、展示和做引用检查，**从不执行**。
- 可引用：输入对象类型的属性（`<input_type>.<property>`，含继承）和 Action 参数（`:参数技术名`）。
- 校验（均忽略单引号字符串内容与 `::` 类型转换）：每个 `:name` 必须是已声明的参数（元素级，解析时即检查）；每个 `a.b` 必须是输入对象类型的技术名加其属性技术名（需要草稿上下文，在草稿完整校验时检查，因此提案在接受时检查）。
- `set_property` 必须且只能给 `property_id`（且必须是输入对象类型含继承的属性）；`create_link` / `delete_link` 必须且只能给 `link_type_id`。前置条件用 `precondition_rule_ids` 引用 Rule 元素。

## 8. 错误码

整份结果拒收时的 `code`：`RESULT_NOT_JSON`、`RESULT_SCHEMA_INVALID`、`RESULT_CONTEXT_MISMATCH`、`CLIENT_REF_DUPLICATE`、`CREATE_WITHOUT_CLIENT_REF`、`OPERATION_SHAPE`、`TARGET_NOT_FOUND`、`TARGET_KIND_MISMATCH`、`BEFORE_MISMATCH`、`TARGET_HASH_MISMATCH`、`CLIENT_REF_UNKNOWN`、`REFERENCE_UNKNOWN`、`DEPENDENCY_UNKNOWN`、`DEPENDENCY_CYCLE`、`MANUAL_EVIDENCE_FORBIDDEN`、`EVIDENCE_INVALID`、`ELEMENT_INVALID`、`TARGET_DUPLICATE`、`ITEM_DUPLICATE`。

## 9. 与上位设计的差异（实施中定稿）

- **Ossie 扩展 v3 只新增 `rules` 与 `actions`**：`rules` 按 Ossie 路径（`concept` 或 `concept.relationship`）记录每条规则的 id、名称、技术名；`actions` 用概念名引用对象、属性、关系和规则技术名。编译器本来就不把材料实例写进 Ossie，因此 Material Object/Link 与证据**不进入任何 Ossie 导出**，公开/完整投影只需继续裁剪 `ontology_mappings`；实施设计 §12 的越权风险由此从源头消除。
- **v1 本体级 `requires`** 在 v2 中保存为顶层字段 `ontology_requires`，不是 Rule 元素、不是提案目标、合并时整体比较。这符合“首期不设计 Workspace Rule”。
- **标识算法带用途前缀**：批次 id 为 `UUIDv5(session_id, "proposal-batch:" + run_token)`，create 目标 id 为 `UUIDv5(batch_id, "create:" + client_ref)`，而不是上位设计中的无前缀写法；前缀避免同一命名空间下不同用途的 id 碰撞。其他语言实现必须使用本文 §4 的算法。
- **Action 前置条件按规则 id 引用**，并附带归属路径与技术名（`{"id", "owner", "technical_name"}`）；文件没有 id 时按“归属路径 + 技术名”解析，从不单凭技术名匹配（规则技术名只在同一归属内唯一）。合并导入中规则沿用本地 id 时，Action 的前置条件随之改写。
- **快照版本严格识别**：`schema_version` 为 `1`（或缺省）按 v1 规范化，为 `2` 原样读取，其他值拒绝；传入空间 id 时核对快照所属空间。
- **读取已发布版本只规范化不重新校验**（版本在发布时已经校验过）；会话草稿编辑期间允许暂时不合法，读取同样只规范化。
- **材料证据的 `material_sha256`** 对从 v1 规范化而来的历史证据为 `null`；新证据在提案解析和草稿保存时必须给出。
