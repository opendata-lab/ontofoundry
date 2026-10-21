"""Flatten declared datasets and uniquely proven joins, never infer physical keys."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import (
    ColumnBinding,
    DataMapping,
    Dataset,
    DatasetColumn,
    DirectJoin,
    ExpressionBinding,
    LinkType,
    MappingKey,
    MappingSource,
    MappingTableJoin,
    PropertiesKey,
    Property,
)
from ontofoundry_api.domain.expressions import resolve_field_expression
from ontofoundry_api.domain.graph import DraftIndex

from .extension import metadata_key
from .ids import identifier_name


def parse_expression(value, dialect=None):
    if isinstance(value, str):
        statements = sqlglot.parse(value)
        if len(statements) != 1 or statements[0] is None:
            raise ValueError("只接受单个表达式")
        return statements[0]
    if not isinstance(value, dict):
        raise ValueError("缺少可解析的表达式或引用")
    variants = value.get("dialects", [])
    from ontofoundry_api.services.dataset_sql import dialect_for
    chosen = next((d for d in variants if dialect and dialect_for(d["dialect"].lower()) == dialect_for(dialect)), None)
    chosen = chosen or next((d for d in variants if d["dialect"] == "ANSI_SQL"), None)
    if not chosen:
        raise ValueError("缺少可解析的 ANSI_SQL 表达式")
    statements = sqlglot.parse(chosen["expression"], read=dialect_for(dialect))
    if len(statements) != 1 or statements[0] is None:
        raise ValueError("只接受单个表达式")
    return statements[0]


@dataclass
class DatasetInfo:
    raw: dict
    path: str
    model: Dataset
    fields: dict[str, exp.Expression]
    keys: list[list[str]]

    def direct(self, name):
        ast = self.fields.get(name)
        return ast.name if isinstance(ast, exp.Column) else None

    def columns(self, names):
        result = [self.direct(n) for n in names]
        return (
            result
            if result and None not in result and len(set(result)) == len(result)
            else None
        )


@dataclass
class Scope:
    key: str
    path: str
    raw: dict
    datasets: dict[str, DatasetInfo] = field(default_factory=dict)
    bindings: dict = field(default_factory=dict)
    relationships: list = field(default_factory=list)

    def reference(self, value):
        ast = parse_expression(value)
        if not isinstance(ast, exp.Column) or ast.db or not ast.table:
            raise ValueError("映射身份必须是明确的数据集字段")
        info = self.datasets.get(ast.table)
        if not info or ast.name not in info.fields:
            raise ValueError("数据集字段不存在或未转换")
        return info, info.fields[ast.name].copy()


def source_table(source):
    tokens = sqlglot.Tokenizer().tokenize(source)
    ast = sqlglot.parse_one(source, into=exp.Table)
    if (
        len(tokens) != len(ast.parts) * 2 - 1
        or any(tokens[i].text != "." for i in range(1, len(tokens), 2))
        or any(t.comments for t in tokens)
    ):
        raise ValueError("source 必须是完整表位置，不能包含查询或额外语句")
    if (
        not isinstance(ast, exp.Table)
        or ast.args.get("alias")
        or not isinstance(ast.this, exp.Identifier)
    ):
        raise ValueError("source 不能是查询、函数或带别名表")
    if any(not isinstance(p, exp.Identifier) for p in ast.parts):
        raise ValueError("source 只能是表位置")
    return ".".join(p.name for p in ast.parts[:-1]) or None, ast.name


def import_datasets(importer, scope, used):
    t = importer.t
    source_names = Counter(
        d.get("name")
        for d in scope.raw["semantic_model"]["datasets"]
        if isinstance(d, dict)
    )
    for i, raw in enumerate(scope.raw["semantic_model"]["datasets"]):
        path = scope.path + f"/semantic_model/datasets/{i}"
        if not t.valid(path):
            continue
        if source_names[raw["name"]] > 1:
            t.issue(
                path, "error", "Dataset", None, "同一作用域数据集名重复，引用无法唯一解析"
            )
            continue
        try:
            metadata = importer.extension.data.get("dataset_metadata", {}).get(metadata_key(scope.raw["name"], raw["name"]), {})
            context = getattr(t, "import_context", None)
            matches = [c for c in (context.connections if context else ()) if c["name"] == metadata.get("connection_name")]
            connection = matches[0] if len(matches) == 1 else None
            engine = connection["kind"] if connection else None
            source_kind, query_sql = "table", None
            try:
                schema, table = source_table(raw["source"])
            except (ValueError, SqlglotError):
                from ontofoundry_api.services.dataset_sql import parse_query
                from ontofoundry_api.services.errors import ServiceError

                try:
                    parse_query(raw["source"], engine)
                except ServiceError as error:
                    # Rejected SQL (e.g. a hidden second statement) is reported as RT-63.
                    raise ValueError(error.message) from error
                schema, table, source_kind, query_sql = None, None, "query", raw["source"]
            fields = {}
            columns = {}
            for j, f in enumerate(raw.get("fields", [])):
                fp = path + f"/fields/{j}"
                if not t.valid(fp):
                    continue
                if f["name"] in fields:
                    raise ValueError("逻辑字段名重复")
                try:
                    ast = parse_expression(f["expression"], engine)
                    if any(
                        isinstance(
                            n,
                            (
                                exp.Query,
                                exp.Window,
                                exp.AggFunc,
                                exp.Command,
                                exp.DDL,
                                exp.DML,
                                exp.Table,
                            ),
                        )
                        for n in ast.walk()
                    ):
                        raise ValueError("字段必须是同行标量表达式")
                    for c in ast.find_all(exp.Column):
                        if c.db or c.table not in ("", raw["name"], table):
                            raise ValueError("字段引用了另一个数据集")
                        columns.setdefault(c.name, DatasetColumn(name=c.name))
                        c.set("table", None)
                    fields[f["name"]] = ast
                    for loss in (
                        "label",
                        "ai_context",
                        "custom_extensions",
                        "datatype",
                        "dimension",
                    ):
                        if loss == "ai_context" and isinstance(f.get(loss), dict):
                            remaining = set(f[loss]) - {"synonyms"}
                            if not remaining:
                                continue
                        if loss in f:
                            # Declared types are not compared with registered columns;
                            # the reviewer reads the location and decides.
                            t.issue(
                                fp + "/" + loss,
                                "dropped",
                                "FieldMetadata",
                                "RT-46",
                                "字段类型和时间用途声明不保存，以登记列类型和指标时间字段为准"
                                if loss in ("datatype", "dimension")
                                else "逻辑字段元数据不作为物理元数据保存",
                            )
                except (ValueError, SqlglotError) as error:
                    t.issue(
                        fp,
                        "dropped",
                        "Field",
                        "RT-43",
                        f"字段不能机械解析：{error}",
                        completion=True,
                    )
            label = identifier_name(raw["name"], used)
            model = Dataset(
                id=t.id("dataset:" + scope.key + ":" + raw["name"]),
                name=label,
                display_name=importer.extension.name("dataset:" + metadata_key(scope.raw["name"], raw["name"])),
                source_kind=source_kind,
                query_sql=query_sql,
                connection_id=connection["id"] if connection else None,
                dialect=engine,
                snapshot_date_column=metadata.get("snapshot_date_column"),
                schema_name=schema,
                table_name=table,
                description=raw.get("description", ""),
                columns=list(columns.values()) or None,
            )
            info = DatasetInfo(raw, path, model, fields, [])
            for key in [raw.get("primary_key", []), *raw.get("unique_keys", [])]:
                if not key:
                    continue
                resolved = info.columns(key)
                if resolved:
                    info.keys.append(resolved)
                else:
                    t.issue(
                        path,
                        "dropped",
                        "DatasetKey",
                        "RT-64",
                        "键无法完整解析为不重复物理列，未作为来源键或连接依据",
                        completion=True,
                    )
            if t.accept("datasets", model, path, rule="RT-62"):
                scope.datasets[raw["name"]] = info
                if label != raw["name"]:
                    t.issue(
                        path + "/name",
                        "converted",
                        "DatasetName",
                        "RT-62",
                        "跨作用域同名数据集各自登记并确定性消歧",
                        targets=[model.id],
                    )
                t.issue(
                    path,
                    "converted",
                    "DatasetMetadata",
                    "RT-66",
                    "仅登记表达式已引用的物理列；来源引擎及列物理类型未知，未从 ANSI_SQL 推断",
                    targets=[model.id],
                    completion=True,
                    severity="warning",
                )
                for key in ("ai_context", "custom_extensions"):
                    if raw.get(key):
                        t.issue(
                            path + "/" + key,
                            "dropped",
                            "DatasetMetadata",
                            "RT-48",
                            "未承载的上下文与扩展保留原文；不从描述恢复快照或引擎",
                            completion=True,
                        )
        except (ValueError, SqlglotError) as error:
            t.issue(
                path,
                "error",
                "Dataset",
                "RT-63",
                f"数据集来源不支持：{error}",
                completion=True,
            )
    for i, raw in enumerate(scope.raw["semantic_model"].get("relationships", [])):
        path = scope.path + f"/semantic_model/relationships/{i}"
        if not t.valid(path):
            continue
        source = scope.datasets.get(raw["from"])
        target = scope.datasets.get(raw["to"])
        left = source.columns(raw["from_columns"]) if source else None
        right = target.columns(raw["to_columns"]) if target else None
        if (
            not source
            or not target
            or not left
            or not right
            or len(left) != len(right)
            or not any(set(k) == set(right) for k in target.keys)
        ):
            t.issue(
                path,
                "dropped",
                "PhysicalRelationship",
                "RT-53",
                "物理连接的完整列组或目标唯一键未证明，不猜测连接",
                completion=True,
            )
        else:
            scope.relationships.append((source, target, left, right, path))


def property_for(importer, owner, name):
    t = importer.t
    obj = t.objects[owner]
    for oid in DraftIndex(t.model).lineage(obj.id):
        original = next(n for n, o in t.objects.items() if o.id == oid)
        prop = t.members.get((original, name))
        if prop:
            return prop
    return None


def identity(importer, scope, owner, raw):
    refs = raw.get("referent_mappings", [])
    obj = importer.t.objects[owner]
    identifiers = DraftIndex(importer.t.model).identifier(obj.id)
    fields = {}
    info = None
    if refs:
        for ref in refs:
            if ref.get("referent_mappings"):
                raise ValueError("嵌套 referent_mappings 未承载")
            prop = property_for(importer, owner, ref["relationship"])
            if not isinstance(prop, Property):
                raise ValueError("身份成员不是已转换属性")
            dataset, ast = scope.reference(ref["expression"])
            if not isinstance(ast, exp.Column):
                raise ValueError("身份字段不能是计算表达式")
            if info and info is not dataset:
                raise ValueError("一个对象身份跨多个数据集")
            info = dataset
            fields[prop.name] = ColumnBinding(
                kind="column", source_id="main", column=ast.name
            )
        if {p.name for p in identifiers} != set(fields):
            raise ValueError("referent_mappings 必须对应完整有效标识")
    elif raw.get("expression"):
        info, ast = scope.reference(raw["expression"])
        if not isinstance(ast, exp.Column):
            raise ValueError("身份字段不能是计算表达式")
        if len(identifiers) == 1:
            fields[identifiers[0].name] = ColumnBinding(
                kind="column", source_id="main", column=ast.name
            )
    else:
        raise ValueError("对象映射没有可确定的主身份")
    primary = info.columns(info.raw.get("primary_key", []))
    if not primary and identifiers and all(p.name in fields for p in identifiers):
        candidate = [fields[p.name].column for p in identifiers]
        # Ontology identity is a semantic uniqueness declaration, not evidence
        # that another arbitrary field is a database key.
        if len(candidate) == len(set(candidate)):
            primary = candidate
    return info, fields, primary or []


def side_source(scope, main, main_keys, side):
    if not main_keys:
        return None
    candidates = []
    for left, right, lcols, rcols, _ in scope.relationships:
        if left is side and right is main:
            sidecols, maincols = lcols, rcols
        elif left is main and right is side:
            sidecols, maincols = rcols, lcols
        else:
            continue
        if set(maincols) != set(main_keys) or not any(
            set(k) == set(sidecols) for k in side.keys
        ):
            continue
        pairs = dict(zip(maincols, sidecols, strict=True))
        candidates.append([pairs[k] for k in main_keys])
    unique = {tuple(c) for c in candidates}
    return list(next(iter(unique))) if len(unique) == 1 else None


def import_object_mapping(importer, scope, owner, raw, path):
    t = importer.t
    obj = t.objects[owner]
    if resolve_binding(t.model, obj.id).mappings:
        t.issue(
            path,
            "dropped",
            "ObjectMapping",
            "RT-65",
            "对象或祖先已有绑定；不覆盖父绑定、不猜纵向合并",
            completion=True,
        )
        return
    try:
        identities = [
            identity(importer, scope, owner, m) for m in raw.get("object_mappings", [])
        ]
        if not identities:
            raise ValueError("没有可确定的对象主来源")
        main, fields, keys = identities[0]

        def signature(x):
            return (
                x[0].model.id,
                {n: b.model_dump() for n, b in x[1].items()},
                x[2],
            )

        if any(signature(i) != signature(identities[0]) for i in identities[1:]):
            raise ValueError("多个对象身份不等价，不能任取第一项")
        sources = [MappingSource(id="main", dataset_id=main.model.id, key_columns=keys)]
        source_names = {main.model.id: "main"}
        mapping = DataMapping(
            id=t.id("mapping:" + owner),
            type_id=obj.id,
            binding_mode="independent",
            sources=sources,
            fields=fields,
        )
        for i, root in enumerate(raw.get("link_mappings", [])):
            rp = path + f"/link_mappings/{i}"
            if root.get("relationship"):
                t.issue(
                    rp,
                    "dropped",
                    "LinkMapping",
                    "RT-43",
                    "只支持主对象身份下的平铺属性及业务关系 children",
                    completion=True,
                )
                continue
            try:
                root_identity = identity(importer, scope, owner, root["object_mapping"])
                if signature(root_identity) != signature(identities[0]):
                    # A relationship-table root is considered separately below.
                    if any(
                        isinstance(
                            property_for(importer, owner, c.get("relationship", "")),
                            Property,
                        )
                        for c in root.get("children", [])
                    ):
                        raise ValueError("属性映射根与主对象身份不一致")
                    continue
            except (ValueError, SqlglotError) as error:
                t.issue(rp, "dropped", "LinkMapping", "RT-43", str(error), completion=True)
                continue
            for j, child in enumerate(root.get("children", [])):
                cp = rp + f"/children/{j}"
                prop = property_for(importer, owner, child.get("relationship", ""))
                if isinstance(prop, LinkType):
                    continue
                try:
                    if child.get("children"):
                        raise ValueError("多层 children 未承载")
                    if not isinstance(prop, Property):
                        raise ValueError("属性不存在或未转换")
                    dataset, ast = scope.reference(child["object_mapping"]["expression"])
                    next_sources = list(mapping.sources)
                    source_name = source_names.get(dataset.model.id)
                    if source_name is None:
                        columns = side_source(scope, main, keys, dataset)
                        if not columns:
                            raise ValueError("附表没有唯一声明的同键宽星形连接")
                        source_name = "side_" + str(len(mapping.sources))
                        next_sources.append(
                            MappingSource(
                                id=source_name,
                                dataset_id=dataset.model.id,
                                key_columns=columns,
                            )
                        )
                    if isinstance(ast, exp.Column):
                        binding = ColumnBinding(
                            kind="column", source_id=source_name, column=ast.name
                        )
                    else:
                        for column in ast.find_all(exp.Column):
                            column.set("table", exp.to_identifier(source_name))
                        binding = ExpressionBinding(kind="expression", expression=ast.sql())
                        resolve_field_expression(
                            t.model,
                            mapping.model_copy(update={"sources": next_sources}),
                            binding.expression,
                        )
                    if prop.name in mapping.fields and mapping.fields[prop.name] != binding:
                        raise ValueError("同一属性有不等价的重复绑定")
                    mapping.sources = next_sources
                    mapping.fields[prop.name] = binding
                    logical = child["object_mapping"]["expression"]
                    try:
                        logical_column = parse_expression(logical)
                    except (ValueError, SqlglotError):
                        logical_column = None
                    if isinstance(logical_column, exp.Column):
                        raw_field = next(
                            (
                                f
                                for f in dataset.raw.get("fields", [])
                                if f["name"] == logical_column.name
                            ),
                            {},
                        )
                        context = raw_field.get("ai_context")
                        if isinstance(context, dict) and context.get("synonyms"):
                            t.used_field_synonyms.add(
                                (dataset.model.id, logical_column.name)
                            )
                            t.replace(
                                "properties",
                                prop.model_copy(
                                    update={
                                        "synonyms": list(
                                            dict.fromkeys(
                                                prop.synonyms + context["synonyms"]
                                            )
                                        )
                                    }
                                ),
                                cp,
                                message="逻辑字段同义词并入已映射属性",
                            )
                    source_names[dataset.model.id] = source_name
                    t.issue(
                        cp,
                        "converted",
                        "FieldBinding",
                        "RT-52" if source_name != "main" else None,
                        "属性字段已解析为主/附来源的同行绑定",
                        targets=[mapping.id],
                    )
                except (ValueError, SqlglotError) as error:
                    t.issue(
                        cp,
                        "dropped",
                        "FieldBinding",
                        "RT-43",
                        f"本属性绑定未转换：{error}",
                        completion=True,
                    )
        if t.accept("mappings", mapping, path, rule="RT-52"):
            scope.bindings[obj.id] = (main, mapping)
            if not keys:
                t.issue(
                    path,
                    "converted",
                    "MappingKey",
                    "RT-64",
                    "来源逻辑键尚未确定；保留绑定但不伪造键",
                    targets=[mapping.id],
                    completion=True,
                    severity="warning",
                )
            context = main.raw.get("ai_context")
            if isinstance(context, dict) and isinstance(context.get("instructions"), str):
                owners = set()
                for cm in scope.raw.get("concept_mappings", []):
                    if cm["concept"] not in t.objects:
                        continue
                    for om in cm.get("object_mappings", []):
                        try:
                            if identity(importer, scope, cm["concept"], om)[0] is main:
                                owners.add(cm["concept"])
                        except (ValueError, SqlglotError):
                            continue
                if len(owners) == 1:
                    text = "\n\n".join(
                        filter(None, [obj.description, context["instructions"]])
                    )
                    t.replace(
                        "object_types",
                        obj.model_copy(update={"description": text}),
                        main.path + "/ai_context/instructions",
                        rule="RT-59",
                        message="唯一可归属对象的说明并入 description",
                    )
    except (ValueError, SqlglotError) as error:
        t.issue(
            path,
            "dropped",
            "ObjectMapping",
            "RT-43",
            f"不能确定对象身份映射：{error}",
            completion=True,
        )


def bound_properties(t, type_id, columns):
    binding = resolve_binding(t.model, type_id)
    index = DraftIndex(t.model)
    result = []
    for column in columns:
        matches = [
            p
            for p in index.effective_properties(type_id)
            if isinstance(binding.fields.get(p.name), ColumnBinding)
            and binding.fields[p.name].source_id == "main"
            and binding.fields[p.name].column == column
        ]
        if len(matches) != 1:
            return None
        result.append(matches[0])
    return result


def aligned_key(info, columns, from_columns):
    keys = [k for k in info.keys if set(k) == set(columns)]
    if not keys:
        return None
    key = keys[0]
    pairs = dict(zip(columns, from_columns, strict=True))
    return key, [pairs[k] for k in key]


def restore_declared_uniqueness(importer, scopes):
    t = importer.t
    infos = {info.model.id: info for scope in scopes for info in scope.datasets.values()}
    for obj in t.model.object_types:
        binding = resolve_binding(t.model, obj.id)
        for prop in DraftIndex(t.model).effective_properties(obj.id):
            field = binding.fields.get(prop.name)
            if prop.unique or not isinstance(field, ColumnBinding):
                continue
            source = binding.sources.get(field.source_id)
            info = infos.get(source.dataset_id) if source else None
            if info is None or [field.column] not in info.keys:
                continue
            path = (
                info.path + "/unique_keys"
                if "unique_keys" in info.raw
                else info.path + "/primary_key"
            )
            t.replace(
                "properties",
                prop.model_copy(update={"unique": True}),
                path,
                message="由已声明且直接绑定的单列唯一键恢复属性唯一性；不把复合键拆成多个唯一属性",
            )


def bind_relationship(importer, scope, owner, root, child, path):
    t = importer.t
    link = property_for(importer, owner, child.get("relationship", ""))
    if not isinstance(link, LinkType):
        return
    if link.data_join is not None:
        t.issue(
            path,
            "dropped",
            "RelationshipBinding",
            "RT-53",
            "同一业务关系已有绑定，不覆盖既有定义",
            completion=True,
        )
        return
    source_binding = scope.bindings.get(link.source_type_id)
    target_binding = scope.bindings.get(link.target_type_id)
    if not source_binding or not target_binding:
        t.issue(
            path,
            "dropped",
            "RelationshipBinding",
            "RT-53",
            "关系端点缺少本作用域主身份映射",
            completion=True,
        )
        return
    source, sm = source_binding
    target, tm = target_binding
    try:
        if child.get("children"):
            raise ValueError("多层关系 children 未承载")
        target_name = child["object_mapping"].get("concept")
        if target_name and t.objects.get(target_name) is not t.objects.get(
            next((n for n, o in t.objects.items() if o.id == link.target_type_id), "")
        ):
            raise ValueError("业务关系目标概念与映射不一致")
        referenced = child["object_mapping"]
        if referenced.get("referent_mappings"):
            target_owner = next(
                n for n, o in t.objects.items() if o.id == link.target_type_id
            )
            ref, ref_fields, _ = identity(importer, scope, target_owner, referenced)
            requested = [b.column for b in ref_fields.values()]
        else:
            ref, ast = scope.reference(referenced["expression"])
            if not isinstance(ast, exp.Column):
                raise ValueError("关系端点引用必须为直接字段")
            requested = [ast.name]

        rootref, rootast = (
            scope.reference(root["object_mapping"]["expression"])
            if root["object_mapping"].get("expression")
            else (source, None)
        )
        candidates = []
        for left, right, lcols, rcols, _rp in scope.relationships:
            if left is source and right is target:
                if ref is source and set(requested) != set(lcols):
                    continue
                if ref is target and set(requested) != set(rcols):
                    continue
                if ref not in (source, target):
                    continue
                aligned = aligned_key(target, rcols, lcols)
                if not aligned:
                    continue
                target_cols, source_cols = aligned
                tp = bound_properties(t, link.target_type_id, target_cols)
                sp = bound_properties(t, link.source_type_id, source_cols)
                if link.multiplicity != "many_to_many" and tp and sp:
                    candidates.append(
                        DirectJoin(
                            kind="direct",
                            source_property_ids=[p.id for p in sp],
                            target_property_ids=[p.id for p in tp],
                        )
                    )
                elif sm.sources[0].key_columns:
                    targetkey = (
                        PropertiesKey(kind="properties", property_ids=[p.id for p in tp])
                        if tp
                        else MappingKey(kind="mapping_key")
                    )
                    if not tp and target_cols != tm.sources[0].key_columns:
                        continue
                    candidates.append(
                        MappingTableJoin(
                            kind="mapping_table",
                            dataset_id=source.model.id,
                            source_columns=sm.sources[0].key_columns,
                            target_columns=source_cols,
                            source_key=MappingKey(kind="mapping_key"),
                            target_key=targetkey,
                        )
                    )
        # Independent relation tables require two complete endpoint joins and
        # business identity references that identify exactly that bridge.
        if (
            rootref not in (source, target)
            and isinstance(rootast, exp.Column)
            and ref is rootref
        ):
            bridge = rootref
            lefts = [
                r
                for r in scope.relationships
                if r[0] is bridge and r[1] is source and rootast.name in r[2]
            ]
            rights = [
                r
                for r in scope.relationships
                if r[0] is bridge and r[1] is target and set(requested) == set(r[2])
            ]
            for a in lefts:
                for b in rights:
                    if a is b:
                        continue
                    sa = aligned_key(source, a[3], a[2])
                    ta = aligned_key(target, b[3], b[2])
                    if not sa or not ta:
                        continue
                    if (
                        sa[0] != sm.sources[0].key_columns
                        or ta[0] != tm.sources[0].key_columns
                    ):
                        continue
                    candidates.append(
                        MappingTableJoin(
                            kind="mapping_table",
                            dataset_id=bridge.model.id,
                            source_columns=sa[1],
                            target_columns=ta[1],
                            source_key=MappingKey(kind="mapping_key"),
                            target_key=MappingKey(kind="mapping_key"),
                        )
                    )
        unique = {c.model_dump_json(): c for c in candidates}
        if len(unique) != 1:
            if len(unique) > 1:
                t.ambiguous_links.add(link.id)
            raise ValueError("业务关系、完整身份字段与物理连接不能唯一匹配")
        chosen = next(iter(unique.values()))
        t.relationship_candidates.setdefault(link.id, []).append((chosen, path))
    except (ValueError, SqlglotError) as error:
        t.issue(
            path, "dropped", "RelationshipBinding", "RT-53", str(error), completion=True
        )


def import_mappings(importer):
    t = importer.t
    maps = importer.document.get("ontology_mappings", [])
    counts = Counter(
        m.get("name") for i, m in enumerate(maps) if t.valid(f"/ontology_mappings/{i}")
    )
    used = set()
    scopes = []
    for i, raw in enumerate(maps):
        path = f"/ontology_mappings/{i}"
        if not t.valid(path):
            continue
        name = raw.get("name")
        key = name if name and counts[name] == 1 else path
        if name is None or counts[name] > 1:
            t.issue(
                path,
                "converted",
                "OntologyMap",
                "RT-41",
                "缺失或重复作用域名，使用稳定源定位消歧",
            )
        scope = Scope(key, path, raw)
        import_datasets(importer, scope, used)
        scopes.append(scope)
        t.issue(
            path,
            "converted",
            "OntologyMap",
            "RT-41",
            "分组仅用于解析引用，不生成核心语义模型树",
        )
    # Populate parent mappings before child mappings irrespective of file order.
    entries = []
    for scope in scopes:
        for i, raw in enumerate(scope.raw.get("concept_mappings", [])):
            path = scope.path + f"/concept_mappings/{i}"
            if not t.valid(path):
                continue
            owner = raw["concept"]
            if owner not in t.objects:
                t.issue(
                    path,
                    "dropped",
                    "ConceptMapping",
                    "RT-43",
                    "对象不存在或未承载，不导入映射",
                    completion=True,
                )
                continue
            entries.append((scope, owner, raw, path))
    entries.sort(
        key=lambda entry: len(DraftIndex(t.model).ancestors(t.objects[entry[1]].id))
    )
    grouped = {}
    for entry in entries:
        grouped.setdefault(entry[1], []).append(entry)
    conflicting = set()
    for owner, items in grouped.items():
        identities = {(item[0].key, str(item[2].get("object_mappings"))) for item in items}
        if len(identities) > 1:
            conflicting.add(owner)
            for _scope, _owner, _raw, path in items:
                t.issue(
                    path,
                    "dropped",
                    "ObjectMapping",
                    "RT-43",
                    "同一对象有不等价的多个主身份映射，不能按文件顺序任取第一项",
                    completion=True,
                )
    for scope, owner, raw, path in entries:
        if owner not in conflicting:
            import_object_mapping(importer, scope, owner, raw, path)
    restore_declared_uniqueness(importer, scopes)
    for scope, owner, raw, path in entries:
        for i, root in enumerate(raw.get("link_mappings", [])):
            for j, child in enumerate(root.get("children", [])):
                bind_relationship(
                    importer,
                    scope,
                    owner,
                    root,
                    child,
                    path + f"/link_mappings/{i}/children/{j}",
                )
    for link_id, choices in t.relationship_candidates.items():
        unique = {join.model_dump_json(): join for join, _path in choices}
        if len(unique) != 1 or link_id in t.ambiguous_links:
            for _join, path in choices:
                t.issue(
                    path,
                    "dropped",
                    "RelationshipBinding",
                    "RT-53",
                    "同一业务关系存在不同物理绑定，全部保留报告，不任取先后项",
                    completion=True,
                )
            continue
        link = next(link for link in t.model.link_types if link.id == link_id)
        join = next(iter(unique.values()))
        t.replace(
            "link_types",
            link.model_copy(update={"data_join": join}),
            choices[0][1],
            rule="RT-53",
            message="全部声明汇总后唯一匹配物理完整列组，已按目标键次序对齐",
        )
    for scope in scopes:
        for dataset in scope.datasets.values():
            for i, raw_field in enumerate(dataset.raw.get("fields", [])):
                if not t.valid(dataset.path + f"/fields/{i}") or not isinstance(
                    raw_field, dict
                ):
                    continue
                context = raw_field.get("ai_context", {})
                if (
                    isinstance(context, dict)
                    and context.get("synonyms")
                    and (dataset.model.id, raw_field["name"]) not in t.used_field_synonyms
                ):
                    t.issue(
                        dataset.path + f"/fields/{i}/ai_context",
                        "dropped",
                        "FieldMetadata",
                        "RT-46",
                        "逻辑字段同义词没有已映射属性承接，保留源文件与报告",
                    )
    return scopes
