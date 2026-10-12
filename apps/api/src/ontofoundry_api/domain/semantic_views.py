"""Pure query projections of the native semantic tree, never a second truth."""

import re
from dataclasses import dataclass
from uuid import UUID, uuid5

from .models import DataJoin, DataMapping, OntologyDraft

READONLY_REASONS = {
    "multiple_roots": "映射树包含多个根",
    "referent_mapping": "包含 referent 引用",
    "multiple_concept_mappings": "同一概念有多个映射",
    "multiple_datasets": "涉及多个数据集",
    "computed_object_expression": "对象标识是计算表达式",
    "composite_object_key": "对象主键有多列",
    "computed_mapping_expression": "映射含计算表达式",
    "computed_key_field": "标识字段是计算表达式",
    "nested_property_mapping": "属性映射含嵌套结构",
    "computed_or_duplicate_property": "属性映射为计算式或重复",
    "non_table_source": "数据来源不是简单表名",
    "cross_or_ambiguous_connection": "跨连接或连接别名不明确",
}

IDENT = r'(?:[A-Za-z_][\w]*|"(?:[^"]|"")+")'
COLUMN = re.compile(rf"^\s*(?:(?P<dataset>{IDENT})\.)?(?P<column>{IDENT})\s*$")


def identifier(value):
    return value[1:-1].replace('""', '"') if value.startswith('"') else value


def column_reference(text):
    match = COLUMN.fullmatch(text or "")
    return (
        (
            identifier(match["dataset"]) if match["dataset"] else None,
            identifier(match["column"]),
        )
        if match
        else None
    )


def connection_alias(model):
    import json

    aliases = []
    for extension in model.custom_extensions:
        if extension.vendor_name != "ONTOFOUNDRY":
            continue
        try:
            data = json.loads(extension.data)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            if data.get("legacy_connection_aliases"):
                return None
            if isinstance(data.get("connection_alias"), str):
                aliases.append(data["connection_alias"])
    if len(set(aliases)) > 1:
        return None
    # This is only a lookup view for standard files with no platform extension.
    # A writer always puts the actual alias in the vendor extension.
    return aliases[0] if aliases else model.map_name or model.name


@dataclass(frozen=True)
class MappingAnalysis:
    mapping: DataMapping | None
    reason: str | None = None
    concept_mapping_id: UUID | None = None
    dataset_id: UUID | None = None

    def public(self, type_id):
        return dict(
            type_id=str(type_id),
            state="queryable"
            if self.mapping
            else "readonly"
            if self.reason
            else "unmapped",
            reason=self.reason,
            message="复杂映射暂不支持实例查询（"
            + READONLY_REASONS.get(self.reason, self.reason)
            + "）"
            if self.reason
            else None,
            dataset_id=str(self.dataset_id) if self.dataset_id else None,
        )


@dataclass(frozen=True)
class CompositeJoin:
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]

    def model_dump(self, **kwargs):
        return dict(
            source_column=self.source_columns[0],
            target_column=self.target_columns[0],
            source_columns=list(self.source_columns),
            target_columns=list(self.target_columns),
        )


def join_columns(join):
    if isinstance(join, CompositeJoin):
        return join.source_columns, join.target_columns
    return (join.source_column,), (join.target_column,)


class SemanticViews:
    def __init__(self, draft: OntologyDraft):
        self.draft = draft
        self.models = {m.id: m for m in draft.semantic_models}
        self.datasets = {d.id: d for d in draft.datasets}
        self.fields = {}
        self.nodes = {}
        self.children = {}
        self.mappings = {}
        self.cache = {}
        self.join_errors = {}
        for f in draft.dataset_fields:
            self.fields.setdefault(f.dataset_id, {})[f.name] = f
        for n in draft.mapping_nodes:
            self.nodes.setdefault(n.concept_mapping_id, []).append(n)
            self.children.setdefault(n.parent_id, []).append(n)
        for c in draft.concept_mappings:
            if c.concept_id.kind == "object_type":
                self.mappings.setdefault(c.concept_id.ref, []).append(c)

    def physical(self, dataset, text):
        reference = column_reference(text)
        if not reference or reference[0] not in (None, dataset.name):
            return None
        name = reference[1]
        field = self.fields.get(dataset.id, {}).get(name)
        if field is None:
            return name  # an explicit physical column, not a guessed expression
        expressions = [
            e.expression for e in field.expression.dialects if e.dialect == "ANSI_SQL"
        ]
        if len(expressions) != 1:
            return None
        physical = column_reference(expressions[0])
        return physical[1] if physical and physical[0] in (None, dataset.name) else None

    def relationship_column(self, dataset, name):
        # OSI relationship keys are field names, not raw SQL column references.
        field = self.fields.get(dataset.id, {}).get(name)
        if field is None:
            return None, f"数据集字段不存在：{dataset.name}.{name}"
        column = self.physical(dataset, '"' + name.replace('"', '""') + '"')
        if column is None:
            return None, f"复杂连接字段暂不支持实例查询（{dataset.name}.{name}）"
        return column, None

    def analyze(self, type_id):
        type_id = UUID(str(type_id))
        if type_id in self.cache:
            return self.cache[type_id]
        entries = self.mappings.get(type_id, [])
        if not entries:
            result = MappingAnalysis(None)
        elif len(entries) != 1:
            result = MappingAnalysis(None, "multiple_concept_mappings")
        else:
            result = self._analyze(entries[0], type_id)
        self.cache[type_id] = result
        return result

    def _analyze(self, cm, type_id):
        def readonly(reason):
            return MappingAnalysis(None, reason, cm.id)

        nodes = self.nodes.get(cm.id, [])
        roots = [n for n in nodes if n.parent_id is None and n.slot == "object_mappings"]
        link_roots = [n for n in nodes if n.parent_id is None and n.slot == "link_mappings"]
        if len(roots) != 1 or len(link_roots) > 1:
            return readonly("multiple_roots")
        if any(n.kind == "referent" for n in nodes):
            return readonly("referent_mapping")
        reference = column_reference(roots[0].expression)
        if not reference:
            return readonly("computed_object_expression")
        datasets = [
            d
            for d in self.draft.datasets
            if d.semantic_model_id == cm.semantic_model_id
            and (reference[0] == d.name or reference[0] is None)
        ]
        if len(datasets) != 1:
            return readonly("multiple_datasets")
        dataset = datasets[0]
        if len(dataset.primary_key) > 1:
            return readonly("composite_object_key")
        for node in nodes:
            if node.expression:
                ref = column_reference(node.expression)
                if not ref or ref[0] not in (None, dataset.name):
                    return readonly(
                        "multiple_datasets" if ref else "computed_mapping_expression"
                    )
        key = self.physical(dataset, roots[0].expression)
        if not key:
            return readonly("computed_key_field")
        # Only mapped properties and the object key affect instance queries.
        # Unused computed dataset fields, metrics and vendor JSON are ignored.
        properties = {p.technical_name for p in self.draft.effective_properties(type_id)}
        fields = {}
        for node in nodes:
            if node.kind != "link" or node.relationship not in properties:
                continue
            objects = [
                n for n in self.children.get(node.id, []) if n.slot == "object_mapping"
            ]
            if len(objects) != 1 or any(
                n.kind == "link" for n in self.children.get(objects[0].id, [])
            ):
                return readonly("nested_property_mapping")
            column = self.physical(dataset, objects[0].expression)
            if not column or node.relationship in fields:
                return readonly("computed_or_duplicate_property")
            fields[node.relationship] = column
        source = column_reference(dataset.source)
        if not source:
            return readonly("non_table_source")
        alias = connection_alias(self.models[cm.semantic_model_id])
        if not alias:
            return readonly("cross_or_ambiguous_connection")
        retired = [
            old
            for old, new in self.draft.extension_v4.legacy_mapping_ids.items()
            if new == cm.id
        ]
        concept = next(o.concept for o in self.draft.object_types if o.id == type_id)
        mapping = DataMapping(
            id=retired[0]
            if retired
            else uuid5(self.draft.workspace_id, f"mapping:{alias}.{concept}"),
            type_id=type_id,
            connection_alias=alias,
            table_name=source[1],
            schema_name=source[0],
            key_column=key,
            fields=fields,
        )
        return MappingAnalysis(mapping, concept_mapping_id=cm.id, dataset_id=dataset.id)

    def join(self, link_id):
        link = next(
            (
                relation
                for relation in self.draft.link_types
                if str(relation.id) == str(link_id)
            ),
            None,
        )
        if not link or link.source_type_id is None:
            return None
        source, target = (
            self.analyze(link.source_type_id),
            self.analyze(link.target_type_id),
        )
        if (
            not source.mapping
            or not target.mapping
            or source.mapping.connection_alias != target.mapping.connection_alias
        ):
            return None
        src, dst = self.datasets[source.dataset_id], self.datasets[target.dataset_id]
        if src.semantic_model_id != dst.semantic_model_id:
            return None
        cm = self.mappings[link.owner_type_id][0]
        expressions = [
            n
            for n in self.nodes.get(cm.id, [])
            if n.kind == "link" and n.relationship == link.technical_name
        ]
        candidates = []
        named_candidates = []
        errors, named_errors = [], []
        named_seen = False
        for r in self.draft.dataset_relationships:
            if r.semantic_model_id != src.semantic_model_id:
                continue
            forward = r.from_ == src.name and r.to == dst.name
            reverse = r.from_ == dst.name and r.to == src.name
            if not (forward or reverse):
                continue
            # Name matching covers migrated platform joins; native files may
            # name the dataset join differently and tie it through the tree.
            names = {
                link.technical_name,
                link.technical_name + "__" + link.id.hex,
                link.technical_name
                + "__"
                + uuid5(
                    self.draft.workspace_id,
                    f"v3:ontology_mappings/{self.models[r.semantic_model_id].map_name}/relationships/{link.id}",
                ).hex,
            }
            if r.name not in names and not expressions:
                continue
            a, b = (
                (r.from_columns, r.to_columns)
                if forward
                else (r.to_columns, r.from_columns)
            )
            named = r.name in names
            named_seen |= named
            resolved_a = [self.relationship_column(src, c) for c in a]
            resolved_b = [self.relationship_column(dst, c) for c in b]
            problems = [error for _, error in [*resolved_a, *resolved_b] if error]
            if problems:
                (named_errors if named else errors).extend(problems)
                continue
            a = tuple(column for column, _ in resolved_a)
            b = tuple(column for column, _ in resolved_b)
            if not a or len(a) != len(b):
                continue
            if r.name not in names:
                values = [
                    self.physical(
                        self.datasets[
                            source.dataset_id
                            if link.endpoint_direction == "forward"
                            else target.dataset_id
                        ],
                        o.expression,
                    )
                    for n in expressions
                    for o in self.children.get(n.id, [])
                    if o.slot == "object_mapping"
                ]
                owner_columns = a if link.endpoint_direction == "forward" else b
                if not any(v in owner_columns for v in values):
                    continue
            candidates.append((a, b))
            if r.name in names:
                named_candidates.append((a, b))
        candidates = named_candidates if named_seen else candidates
        if len(set(candidates)) != 1:
            problems = named_errors if named_seen else errors
            if problems:
                self.join_errors[str(link_id)] = "；".join(dict.fromkeys(problems))
            return None
        self.join_errors.pop(str(link_id), None)
        a, b = candidates[0]
        return (
            DataJoin(source_column=a[0], target_column=b[0])
            if len(a) == 1
            else CompositeJoin(a, b)
        )


def mapping_view(draft, type_id):
    return SemanticViews(draft).analyze(type_id).mapping


def join_view(draft, link_id):
    return SemanticViews(draft).join(link_id)


def semantic_catalog(draft):
    """Clean native structure, with metric attribution as a derived view."""
    from ontofoundry_api.services.public_projection import public_projection

    views = SemanticViews(draft)
    concepts = {c.id: c for c in [*draft.object_types, *draft.value_types]}
    from ontofoundry_api.domain.semantic_authoring import identifier_edits
    from ontofoundry_api.services.errors import ServiceError

    def uses_dataset(text, name, dialect=""):
        try:
            return identifier_edits(text, dataset=name, replacement=name, dialect=dialect)[1]
        except ServiceError:
            # Catalogs also carry non-SQL expressions; do not reject native
            # models merely because a dialect has no SQL tokenizer.
            return bool(re.search(r"(?<!\w)[`\"]?" + re.escape(name) + r"[`\"]?\s*\.", text))

    models = []
    def display(node):
        return draft.extension_v4.display_names.get(node.id, node.name)
    for model in draft.semantic_models:
        datasets = [d for d in draft.datasets if d.semantic_model_id == model.id]
        dataset_concepts = {}
        metric_concepts = {}
        for cm in draft.concept_mappings:
            if cm.semantic_model_id != model.id:
                continue
            for node in views.nodes.get(cm.id, []):
                if not node.expression:
                    continue
                for dataset in datasets:
                    if uses_dataset(node.expression, dataset.name):
                        dataset_concepts.setdefault(dataset.name, set()).add(
                            cm.concept_id.ref
                        )
                for metric in draft.metrics:
                    if metric.semantic_model_id == model.id and re.search(
                        r"(?<!\w)" + re.escape(metric.name) + r"(?!\w)", node.expression
                    ):
                        metric_concepts.setdefault(metric.id, set()).add(cm.concept_id.ref)
        metrics = []
        for metric in draft.metrics:
            if metric.semantic_model_id != model.id:
                continue
            ids = set(metric_concepts.get(metric.id, set()))
            for name, concept_ids in dataset_concepts.items():
                if any(uses_dataset(e.expression, name, e.dialect) for e in metric.expression.dialects):
                    ids.update(concept_ids)
            metrics.append(
                {
                    **metric.model_dump(mode="json"),
                    "display_name": display(metric),
                    "ambiguous": len(ids) > 1,
                    "concepts": [
                        dict(id=str(c.id), kind="object_type" if c in draft.object_types else "value_type", name=c.name, technical_name=c.technical_name)
                        for c in concepts.values()
                        if c.id in ids
                    ],
                }
            )
        models.append(
            {
                **model.model_dump(mode="json"),
                "display_name": display(model),
                "concept_mappings": [{**cm.model_dump(mode="json"), "concept": {"id": str(concepts[cm.concept_id.ref].id), "kind": cm.concept_id.kind, "name": concepts[cm.concept_id.ref].name, "technical_name": concepts[cm.concept_id.ref].concept}, "nodes": [n.model_dump(mode="json") for n in sorted(views.nodes.get(cm.id, []), key=lambda n: (str(n.parent_id or ""), n.slot, n.position if n.position is not None else 0))]} for cm in draft.concept_mappings if cm.semantic_model_id == model.id and cm.concept_id.ref in concepts],
                "connection_alias": connection_alias(model),
                "datasets": [
                    {
                        **d.model_dump(mode="json"),
                        "display_name": display(d),
                        "concepts": [dict(id=str(c.id), kind="object_type" if c in draft.object_types else "value_type", name=c.name, technical_name=c.concept) for c in concepts.values() if c.id in dataset_concepts.get(d.name, set())],
                        "metrics": [str(m.id) for m in draft.metrics if m.semantic_model_id == model.id and any(uses_dataset(e.expression, d.name, e.dialect) for e in m.expression.dialects)],
                        "fields": [
                            {**f.model_dump(mode="json"), "display_name": display(f)}
                            for f in draft.dataset_fields
                            if f.dataset_id == d.id
                        ],
                    }
                    for d in datasets
                ],
                "relationships": [
                    r.model_dump(mode="json", by_alias=True)
                    for r in draft.dataset_relationships
                    if r.semantic_model_id == model.id
                ],
                "metrics": metrics,
            }
        )
    return public_projection(
        {
            "items": models,
            "concepts": [dict(id=str(c.id), kind="object_type" if c in draft.object_types else "value_type", name=c.name, technical_name=c.concept) for c in concepts.values()],
            "mapping_status": {
                str(c.id): views.analyze(c.id).public(c.id) for c in draft.object_types
            },
        }
    )
