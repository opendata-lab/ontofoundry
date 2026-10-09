"""Generate/recheck P0 matrix from pinned schemas and A/B fixture JSON.

Run: python3 scripts/ossie_coverage_matrix.py [--check]
No network, services, database or input fixture mutation.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "apps/api/src/ontofoundry_api/ossie/assets/vendor/apache-ossie"
FIXTURES = ROOT / "apps/api/tests/fixtures/ossie_real"
OUTPUT = ROOT / "docs/design/2026-10-08-ossie-coverage-matrix.md"
SCHEMAS = {"ontology": json.loads((VENDOR / "ontology/ontology.json").read_text()),
           "core": json.loads((VENDOR / "core-spec/osi-schema.json").read_text())}

# Every key is a schema definition (not an inferred JSON shape).
LANDINGS = {
    ("ontology", "$root"): {
        "version": "ossie_version", "name": "ossie_name", "description": "ossie_description",
        "ai_context": "ai_context", "requires": "ontology_requires",
        "ontology": "object_types + value_types（position 共同排序）", "ontology_mappings": "semantic_models（每个 OntologyMap 一项）",
    },
    ("ontology", "OntologyComponent"): {
        "concept": "object_types.concept / value_types.concept", "type": "object_types / value_types 集合归属",
        "description": "object_types.description / value_types.description", "extends": "object_types.extends / value_types.extends（有序 ConceptRef）",
        "identify_by": "object_types.identify_by / value_types.identify_by", "requires": "概念.requires → rules.expression（有序 ID）",
        "derived_by": "概念.derived_by → rules.expression（有序 ID）", "relationships": "properties + link_types（同 owner 下 position 共同排序）",
    },
    ("ontology", "Relationship"): {
        "name": "properties.technical_name / link_types.technical_name（原生关系名）",
        "description": "properties.description / link_types.description", "roles": "properties.roles / link_types.roles（有序附加角色）",
        "multiplicity": "properties.multiplicity / link_types.multiplicity", "requires": "关系.requires → rules.expression（有序 ID）",
        "derived_by": "关系.derived_by → rules.expression（有序 ID）", "verbalizes": "properties.verbalizes / link_types.verbalizes",
    },
    ("ontology", "Role"): {"concept": "roles.concept（ConceptRef）", "name": "roles.name"},
    ("ontology", "ConceptMapping"): {"concept": "concept_mappings.concept_id（ConceptRef）", "object_mappings": "mapping_nodes（slot=object_mappings）", "link_mappings": "mapping_nodes（slot=link_mappings）"},
    ("ontology", "ObjectMapping"): {"concept": "mapping_nodes.concept", "expression": "mapping_nodes.expression", "referent_mappings": "mapping_nodes（slot=referent_mappings）"},
    ("ontology", "LinkMapping"): {"relationship": "mapping_nodes.relationship", "object_mapping": "mapping_nodes（slot=object_mapping，恰一个 object 子节点）", "children": "mapping_nodes（slot=children）"},
    ("ontology", "ReferentMapping"): {"relationship": "mapping_nodes.relationship（必填）", "expression": "mapping_nodes.expression", "referent_mappings": "mapping_nodes（slot=referent_mappings，递归）"},
    ("ontology", "OntologyMap"): {"name": "semantic_models.map_name", "description": "semantic_models.map_description", "semantic_model": "semantic_models（native_presence 与 map_presence 分离）", "concept_mappings": "concept_mappings（父 semantic_model_id）"},
    ("core", "$root"): {"version": "core_version", "semantic_model": "semantic_models（独立 OSI 文档数组）"},
    ("core", "AIContext"): {"instructions": "各作用域 ai_context.instructions（原始 JSON）", "synonyms": "各作用域 ai_context.synonyms（原始 JSON）", "examples": "各作用域 ai_context.examples（原始 JSON）"},
    ("core", "CustomExtension"): {"vendor_name": "custom_extensions[].vendor_name", "data": "custom_extensions[].data（JSON 字符串原文）"},
    ("core", "DialectExpression"): {"dialect": "expression.dialects[].dialect", "expression": "expression.dialects[].expression"},
    ("core", "Expression"): {"dialects": "dataset_fields.expression / metrics.expression.dialects"},
    ("core", "Dimension"): {"is_time": "dataset_fields.dimension.is_time（缺省不推断）"},
}
for definition, collection, properties in [
    ("SemanticModel", "semantic_models", ["name", "description", "ai_context", "custom_extensions"]),
    ("Dataset", "datasets", ["name", "source", "primary_key", "unique_keys", "description", "ai_context", "custom_extensions"]),
    ("Field", "dataset_fields", ["name", "expression", "dimension", "label", "description", "datatype", "ai_context", "custom_extensions"]),
    ("Relationship", "dataset_relationships", ["name", "from", "to", "from_columns", "to_columns", "ai_context", "custom_extensions"]),
    ("Metric", "metrics", ["name", "expression", "description", "datatype", "ai_context", "custom_extensions"]),
]:
    LANDINGS["core", definition] = {field: f"{collection}.{field}" for field in properties}
LANDINGS["core", "SemanticModel"].update(datasets="datasets（父 semantic_model_id）", relationships="dataset_relationships（父 semantic_model_id）", metrics="metrics（父 semantic_model_id）")
LANDINGS["core", "Dataset"]["fields"] = "dataset_fields（父 dataset_id）"
SEMANTICS = {
    "version": "固定规范版本", "name": "原生名称，保留空字符串", "description": "原生描述文本",
    "ai_context": "字符串或开放对象的 AI 上下文", "requires": "约束表达式有序列表", "ontology": "实体和值概念定义",
    "ontology_mappings": "逻辑模型到本体的映射组", "concept": "概念名称或引用", "type": "EntityType / ValueType",
    "extends": "有序父概念引用", "identify_by": "首选标识关系名有序列表", "derived_by": "派生表达式有序列表",
    "relationships": "所属作用域的关系集合", "roles": "所属概念以外的有序角色，可为空", "multiplicity": "ManyToOne / OneToOne，允许缺省",
    "verbalizes": "原文读法，包括 {concept:role}", "object_mappings": "对象映射根数组", "link_mappings": "关系映射根数组",
    "relationship": "关系名引用", "expression": "表达式原文，不限制长度或改写", "referent_mappings": "递归引用映射数组",
    "object_mapping": "单个对象子映射", "children": "有序下一级关系映射", "semantic_model": "语义模型定义容器",
    "concept_mappings": "概念映射集合", "instructions": "AI 使用说明", "synonyms": "作用域内同义词原始列表",
    "examples": "AI 示例问题原始列表", "vendor_name": "扩展厂商名，任意字符串", "data": "厂商 JSON 数据字符串原文",
    "dialect": "规范表达式方言枚举", "dialects": "有序方言表达式数组，保留重复项", "is_time": "时间维度标记，缺省与 false 不等价",
    "dimension": "维度元数据", "label": "分类标签", "datatype": "规范逻辑数据类型，未知时缺省",
    "custom_extensions": "厂商扩展有序数组，不解析再序列化原文", "source": "物理表、视图或查询引用原文",
    "primary_key": "有序主键列数组", "unique_keys": "有序候选键数组及其有序列", "fields": "数据集字段定义",
    "from": "连接的多端 dataset 名", "to": "连接的一端 dataset 名", "from_columns": "有序外键列",
    "to_columns": "有序目标键列，与 from_columns 配对", "datasets": "逻辑数据集集合，可不绑定概念", "metrics": "模型级指标集合",
}


def properties(schema):
    result = dict(schema.get("properties", {}))
    for key in ("oneOf", "anyOf", "allOf"):
        for branch in schema.get(key, []):
            result.update(properties(branch))
    return result


def catalog():
    for source, schema in SCHEMAS.items():
        for definition, node in [("$root", schema), *schema["$defs"].items()]:
            props = properties(node)
            for field, spec in props.items():
                yield source, definition, field, spec
            if not props and definition != "$root":
                yield source, definition, "$value", node


def occurrences(document):
    counts = Counter()

    def walk(value, spec, source, definition=None):
        reference = spec.get("$ref")
        if reference:
            if not reference.startswith("#"):
                source = "core" if "osi-schema.json" in reference else "ontology"
            definition = reference.rsplit("/", 1)[-1]
            node = SCHEMAS[source]["$defs"][definition]
            if not properties(node):
                counts[source, definition, "$value"] += 1
            walk(value, node, source, definition)
            return
        for combinator in ("oneOf", "anyOf", "allOf"):
            for branch in spec.get(combinator, []):
                kind = branch.get("type")
                if kind == "object" and not isinstance(value, dict) or kind == "string" and not isinstance(value, str):
                    continue
                walk(value, branch, source, definition)
        if isinstance(value, dict):
            for field, child in spec.get("properties", {}).items():
                if field in value:
                    counts[source, definition or "$root", field] += 1
                    walk(value[field], child, source)
        elif isinstance(value, list):
            for item in value:
                walk(item, spec.get("items", {}), source)

    walk(document, SCHEMAS["ontology"], "ontology", "$root")
    return counts


SCALAR_LANDINGS = {
    ("ontology", "Expression"): "rules.expression / ontology_requires[] / mapping_nodes.expression",
    ("ontology", "ConceptType"): "object_types / value_types 集合归属",
    ("ontology", "Multiplicity"): "properties.multiplicity / link_types.multiplicity",
    ("core", "Dialect"): "expression.dialects[].dialect",
    ("core", "Vendor"): "custom_extensions[].vendor_name",
    ("core", "DataType"): "dataset_fields.datatype / metrics.datatype",
}


def render():
    counts = [occurrences(json.loads((FIXTURES / f"{name}.ossie.json").read_text())) for name in ("account-model-v2", "architecture-governance")]
    rows = list(catalog())
    property_count = sum(row[2] != "$value" for row in rows)
    lines = ["# Ossie v3 覆盖矩阵（P0 合同冻结）", "", "日期：2026-10-08。规范与范围以已评审方案第 1、3、5 节为准。", "",
             "由 `python3 scripts/ossie_coverage_matrix.py` 从仓库固定 schema 与真实样例生成；`--check` 校验字段集合、计数与文档一致。", "",
             "A = `account-model-v2.ossie.json`；B = `architecture-governance.ossie.json`。次数按 schema 引用作用域计数，统计字段是否出现，空字符串/空数组也算一次；递归映射按每个实例计数。", "",
             "路径为 schema JSON Pointer（ontology = ontology/ontology.json；core = core-spec/osi-schema.json）。根属性使用 `#/properties/...`。Core 顶层独立文档属性在 A/B 中为零，嵌入的 SemanticModel 不算独立文档。", "",
             f"统计：**原生属性 {property_count} 行，原生标量 $defs {len(rows) - property_count} 行，平台扩展 7 行，不支持 0 行**。两份 schema 全部 $defs 都有条目（无属性的标量另列）；开放 AIContext 附加键原样保留。", "",
             "这里的“原生”指 v3 合同有无损落点，不表示 P0 已替换 v2 导入器。A/B 的现有往返差异测试保留，接入分别在 P1/P2/P3；P0 不宣称已完成无损往返。所有 schema 原生构造可承载，无“不支持”理由需要例外。", "",
             "## 逐属性矩阵", "", "| Ossie 路径 | 语义 | v3 落点（字段/集合） | 原生/扩展/不支持 | A 出现次数 | B 出现次数 | 说明 |", "| --- | --- | --- | --- | ---: | ---: | --- |"]
    scalars = []
    for source, definition, field, spec in rows:
        if field == "$value":
            scalars.append((source, definition, field, spec))
            continue
        pointer = f"{source}#" + ("" if definition == "$root" else f"/$defs/{definition}") + f"/properties/{field}"
        if definition == "AIContext":
            pointer = f"{source}#/$defs/AIContext/oneOf/1/properties/{field}"
        landing = LANDINGS[source, definition][field]
        note = "字段出现状态独立记录；原生数组保持顺序及重复项"
        if field == "concept" or field == "extends":
            note += "；ConceptRef 支持实体、值、builtin、Any，导出还原名称"
        if definition == "Relationship" and source == "ontology" and field == "name":
            note += "；name 为平台显示名，technical_name 存原生名，均不清洗原文"
        if field == "ai_context" or field == "custom_extensions":
            note += "；原输入扩展独立保留，本次新增部分可逆撤销"
        if definition == "AIContext":
            note += "；同时支持字符串形及任意附加键，null 仅在原生 JSON 允许处保留"
        if definition in {"ObjectMapping", "LinkMapping", "ReferentMapping"}:
            note += "；parent_id + slot + position 恢复任意深度树及多根"
        if field == "multiplicity":
            note += "；不推断缺省，不补基数"
        lines.append(f"| `{pointer}` | {SEMANTICS[field]} | {landing} | 原生 | {counts[0][source,definition,field]} | {counts[1][source,definition,field]} | {note} |")
    lines += ["", "## 无属性 $defs 的值合同", "", "| Ossie 路径 | 语义 | v3 落点（字段/集合） | 原生/扩展/不支持 | A 出现次数 | B 出现次数 | 说明 |", "| --- | --- | --- | --- | ---: | ---: | --- |"]
    for source, definition, field, spec in scalars:
        lines.append(f"| `{source}#/$defs/{definition}` | {spec.get('description', definition)} | {SCALAR_LANDINGS[source,definition]} | 原生 | {counts[0][source,definition,field]} | {counts[1][source,definition,field]} | 无属性标量；保留原文/遵守固定枚举 |")
    lines += ["", "## 平台扩展合同", "", "下列是平台新增内容，不替代上表的原生字段；A/B 次数统计输入中已有的平台路径，不按未来导出量计数。", "", "| Ossie 路径 | 语义 | v3 落点（字段/集合） | 原生/扩展/不支持 | A 出现次数 | B 出现次数 | 说明 |", "| --- | --- | --- | --- | ---: | ---: | --- |",
              "| `ai_context.ontofoundry.ids` | 稳定 ID 注册表 | extension_v4.ids | 扩展 | 0 | 0 | version=4；作用域路径 → UUID，包括附加角色及隐含 owner 角色 |",
              "| `ai_context.ontofoundry`（显示信息） | 中文显示名、tags、required | extension_v4.display_names/tags/required_properties | 扩展 | 0 | 0 | 原生 name 不被显示名替换 |",
              "| `ai_context.ontofoundry.rule_metadata` | 规则 ID、名称 | extension_v4.rule_metadata | 扩展 | 0 | 0 | 原生约束/派生表达式保留原文、顺序、重复项 |",
              "| `ai_context.ontofoundry.actions` | Action 定义 | extension_v4.actions + actions | 扩展 | 0 | 0 | 平台定义，Ossie 无对应构造 |",
              "| `ai_context.ontofoundry.concept_context` | 非标准概念同义词、说明 | extension_v4.concept_context（稳定 ID 键） | 扩展 | 0 | 0 | 不挪用文档/语义模型同义词；输入同名键原文保留 |",
              "| `semantic_model.custom_extensions(ONTOFOUNDRY).connection_alias` | 连接别名 | semantic_models.custom_extensions[].data | 扩展 | 0 | 0 | JSON 字符串；凭据不入版本；迁移跨连接 join 保留 legacy_connection_aliases 且只读 |",
              "| `metrics.custom_extensions(ONTOFOUNDRY)`（执行配置） | 执行参数、默认过滤、可累加性 | metrics.custom_extensions[].data | 扩展 | 0 | 0 | 不改变原生指标表达式 |", ""]
    return "\n".join(lines) + CONTRACT


CONTRACT = '''## 表示与 canonical 合同

- 对外唯一 `domain.models.OntologyDraft`；schema_version=2 使用旧定义，model_json_schema 默认仍投影 v2（保留当前 API 结构校验），v3 schema 须显式 draft_version="3"；schema_version=3 必须显式带 `hash_algorithm="ontofoundry-domain-v3"`。models_v3 只定义元素，不提供第二个 draft，也不保存源文件作为第二真相。
- 文档 `native_presence` 记录原始顶层键；原生节点 `native_presence` 记录本节点原始键，语义模型的 `map_presence` 单独记录外层 OntologyMap 键；嵌套 AIContext、表达式、dimension、厂商 JSON 用对象键本身表示出现状态。未出现 ≠ 出现的空字符串/空数组 ≠ 原生开放 JSON 中的 null。缺省便利值不能据此判断是否曾出现。
- `origin=imported` 的节点必须有 position；position 是原始父容器、slot 的从零开始数组下标。object_types/value_types 共享 ontology 顺序；properties/link_types 共享 owner.relationships 顺序；扁平树按 parent_id、slot、position 恢复。显式空容器由父节点出现记录承载。角色数组本身有序，角色 position 与索引一致；隐含 owner 的稳定角色 ID 为 uuid5(link.id, "role:owner")。
- 概念和关系的 requires/derived_by 保存有序 Rule ID；rules.expression 保存表达式文本。重复表达式对应独立 ID（导入路径含数组下标）。关系 technical_name 存原生 name，平台显示 name 单独存扩展。所有原生文本不 trim、不 NFC、不截断，不补读法、不补基数。
- owner_ref 支持 EntityType/ValueType；roles 仅含附加角色。零个附加角色是一元，一个是二元，两个及以上是多元。仅两个实体端点的二元关系提供 source_type_id/target_type_id/target_role_name；一元、多元、值端点关系均为空。endpoint_direction/owner_role_name 只用于旧二元方向与角色名兼容，legacy_multiplicity 保留旧平台基数（包括 many_to_many），不伪造原生 multiplicity。 roles[].name 是原生可选字段，仅复制显式输入的角色名；提案、编辑、快照迁移与导出不得由概念显示名或 related/role_N 缺省推断。未命名角色读法用 {concept}，显式命名角色用 {concept:name}；自关系的歧义由语义校验要求用户显式命名。
- material_links.role_values 必须覆盖 owner 与全部附加角色，禁止重复 role_id，实体角色用 object_id，值角色用 value；检查概念引用、继承、值类型与显式基数；二元 source_id/target_id 必须与角色值一致。roles[].concept.ref 支持 {client_ref}，角色自身也可带 client_ref；client_ref 只允许存在于待解析提案，持久化 draft 必须已解析。角色内容与角色顺序分别三方合并，换序属于实质变化（P1 接入）。
- mapping_nodes.kind 为 object/link/referent；slot 区分五种原生位置。link 恰一个 object_mapping 子节点；referent 必填 relationship；父子属于同 concept_mapping，树无循环，slot 与 kind/父类型匹配，同 slot 的 position 不重复。内置概念在 ConceptRef 中保存原生名。concept_id 不要求必须实体，支持值概念与内置引用。
- 源 ai_context（含既有 ontofoundry 键）与 custom_extensions 数组原样保存；extension_v4 是平台本次新增/覆盖内容的合同，display_names/tags/required_properties/actions 是同一元素集合的导出投影，若填入则校验一致，不能作为第二真相编辑；concept_context 与身份/迁移元数据独立保存；export_edits 按 RFC 6901 路径记录 was_present/original/written，包含字符串上下文转对象及新建容器。逆转换仅在当前值等于 written 时撤销本次修改，冲突需显式报告，绝不剥离输入已有扩展。实例和证据只在平台，不能出现在扩展导出载荷。
- v3 canonical 按完整路径：顶层领域 ID 集合按 ID 排序；元素 evidence 按 ID 排序；平台 tags/native_presence/map_presence 为集合。原始位置独立进入哈希；roles、原生 extends/identify_by/requires/derived_by、verbalizes、primary_key/unique_keys、连接列、dialects、role_values 和所有原生 JSON 数组保留顺序及重复项。原生对象键只按 JCS 排序；保留 null，所有原生字符串及 JSON 键保留 Unicode 原文。厂商键即使名为 tags/extends/evidence 也不套用领域规则。
- 旧算法标识 `ontofoundry-domain-v2`（历史未写 hash_algorithm 时的默认），保留现有算法 B 字节：NFC、去 null、按旧字段名规范化。v1 仍按旧 v1→v2 归一化后校验；不能拿迁移出的 v3 哈希校验旧 manifest。新算法标识 `ontofoundry-domain-v3`，JCS 字节前加算法名与换行做域隔离；未知算法拒绝。v3 元素哈希必须带 collection 才可选择路径规则。外部 Ossie/version envelope 与原始 agent 字节哈希维持原合同。

## 不支持构造的导入合同

当前冻结表中不支持数量为 **0**，`ossie.coverage.UNSUPPORTED_OSSIE_PATHS` 为空。parse_ossie 入口检查该唯一注册表；未来若评审新增不支持行，必须同时注册 wildcard 路径和理由，遇到字段即抛出 OssieImportError，含 `$.ontology[0]...` 的具体 JSON 路径（数组下标不能用概念名替代）。这次不扩大到现有 v2 导入器的 skip/report，不因此拒绝 A/B；这些是尚待 P1–P3 接入的能力差距，不是 v3 不支持。schema 错误和语义 lint 维持现有边界。

## 迁移合同

1. **纯读与 opt-in**：read_snapshot/read_snapshot_json 默认 target_version="2"，保持现有 API/演示/MCP/导入导出行为。显式 target_version="3" 或 as_v3_dict 将 v1→v2→v3；不改输入、不触发数据库/服务、不修改历史行。输入 v3 校验后返回独立 JSON；相同输入输出确定，反复读取幂等。P1 切换业务读者；默认 v2 reader 明确拒绝 v3，禁止偷降级丢字段。
2. **转换内容**：旧元素 ID 保留；二元 link 的 owner_ref/roles 依据旧 compiler owner 方向生成，one_to_many 的 owner 是旧 target，通过 endpoint_direction=reverse 保留旧 source/target；不翻转事实。旧属性值概念显式生成 ValueType（非属性推断的原生导入仍在 P1）。生成角色 uuid5(link.id,"role:0") 和 owner uuid5(link.id,"role:owner")。
3. **旧映射**：按 connection_alias 生成语义模型，别名只入模型 ONTOFOUNDRY custom_extensions；每条 DataMapping 转 dataset+fields+concept_mapping+多层 mapping_nodes，每条 data_join 转 dataset_relationship 并保留 link mapping；不同 owner 的同名旧 link 生成模型作用域唯一的 join 名（重复项加确定性 UUID 后缀），不丢任何连接。新 ID 均 uuid5(workspace,"v3:"+作用域路径)，旧 mapping ID 只记录 legacy_mapping_ids→新 concept_mapping ID，不得复用为新 kind。旧 across-connection join 转独立只读桥接模型，记录 legacy_connection_aliases，不进入可查询 join_view。v3 的 mappings 必须为空，不存 data_join，派生视图及 apply_mapping_view 接入在 P3。
4. **无法恢复的历史信息**：v2 已丢失的原生 name/description/context/缺省/多元角色/复杂映射不能重建。ossie_name/ossie_description 缺省且 document_origin=migrated，不冒充原生保真文档；后续只对 origin=platform 新建文档回落工作空间信息。迁移 origin=migrated 的 presence 表示可确定重建的兼容结构，不宣称原输入出现过。旧 many_to_many 原生 multiplicity 缺省，legacy_multiplicity 保存平台语义；原已存在的字符串/JSON 不改写。
5. **会话生命周期（2026-10-09 M6 产品修订，替代旧会话切换合同）**：不兼容旧会话。Alembic 幂等删除所有 draft.schema_version 非字符串 "3" 的建模会话及其提案批次、项、依赖、决定请求/项和运行状态；撤除 migrate-v3、会话切换审计及逐项提案翻译。已经执行过旧 P1 审计表 revision 的数据库仍沿同一迁移链升级，最新 revision 删除废弃审计表。新会话直接从发布版本纯迁移出 v3；正常编辑、提案接受、发布继续使用原 revision CAS。
6. **保留范围**：已发布版本、历史快照与原哈希、材料/块、空间/成员、连接/元数据、服务令牌/作用域、元素身份登记全部保留，不改历史行。运行凭据是无独立存储的签名 grant，会话删除后校验失效；服务令牌不因会话清理被删除。快照/版本的 v1→v2→v3 纯函数与三方合并前统一迁移 base/latest/draft 保留。P1 的简单 DataMapping/data_join 适配继续服务新 v3 会话，不是旧会话翻译服务。
7. **回滚与验收**：清理是产品明确授权的数据删除，downgrade 不重建已删除会话，只恢复上一 revision 所需的空审计表结构。验证 PostgreSQL 与 SQLite 的依赖删除顺序、幂等性、保留数据和新会话提案/发布/实例查询。P1/P3 仍不得更换同一 schema_version=3 的字段形状、slot、引用类型、出现状态或 canonical 规则。

## 待后续阶段决定的实现细节

没有阻塞 P0 的数据形状未决点。P1/M6 按产品修订清理非 v3 会话，保留版本纯读迁移与新会话 revision CAS，落实角色顺序合并与端点只读保护；P2 落实扩展碰撞的 UI 提示；P3 实现 mapping_view/join_view、复杂映射只读交互与 schema 全构造无损往返。这些不能改变本文冻结的数据形状和哈希算法。
'''

if __name__ == "__main__":
    content = render()
    if "--check" in sys.argv:
        if OUTPUT.read_text() != content:
            raise SystemExit("覆盖矩阵与固定 schema/样例/冻结落点不同")
        print("coverage matrix matches pinned schemas and A/B fixtures")
    else:
        OUTPUT.write_text(content)
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
