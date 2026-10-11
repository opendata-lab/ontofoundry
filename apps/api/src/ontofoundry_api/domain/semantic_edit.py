"""Simple table authoring writes native nodes, preserving unrelated trees/metadata."""

import json
from copy import deepcopy
from uuid import UUID, uuid5

from sqlalchemy.engine.default import DefaultDialect

from .models import DataMapping, OntologyDraft
from .models_v3 import (
    ConceptMapping,
    Dataset,
    DatasetField,
    DatasetRelationship,
    MappingNode,
    SemanticModel,
)
from .role_join import authoring_join, role_join_input
from .semantic_fields import ensure_column_field
from .semantic_views import SemanticViews, column_reference, connection_alias

quote_identifier = DefaultDialect().identifier_preparer.quote


def reference(dataset, column):
    return quote_identifier(dataset) + "." + quote_identifier(column)


def apply_semantic_form(snapshot, mappings, joins):
    draft = OntologyDraft.model_validate(snapshot)
    views = SemanticViews(draft)
    old = {str(t.id): a for t in draft.object_types if (a := views.analyze(t.id)).mapping}
    requested = [DataMapping.model_validate(m) for m in mappings]
    if len({m.type_id for m in requested}) != len(requested):
        raise ValueError("每个已存在的业务对象只允许一个数据映射")
    result = deepcopy(snapshot)

    def add(collection, cls, **values):
        values.setdefault(
            "position",
            max(
                (
                    i["position"]
                    for i in result[collection]
                    if i.get("position") is not None
                ),
                default=-1,
            )
            + 1,
        )
        parent = (
            values.get("parent_id")
            or values.get("concept_mapping_id")
            or values.get("dataset_id")
            or values.get("semantic_model_id")
            or draft.workspace_id
        )
        key = values.get("name") or (
            values.get("slot", "") + ":" + str(values.get("position"))
        )
        if collection == "concept_mappings":
            key = str(values["concept_id"]["ref"])
        elif values.get("relationship"):
            key += ":" + values["relationship"]
        values.setdefault(
            "id", uuid5(UUID(str(parent)), "semantic-form:" + collection + ":" + key)
        )
        # A renamed native node keeps its ID. Creating a new node at its old
        # name must use a distinct, reproducible identity (also during preview).
        occupied = {item["id"] for item in result[collection]}
        base_id, counter = values["id"], 0
        while str(values["id"]) in occupied:
            values["id"] = uuid5(
                base_id, "replacement:" + str(values["position"]) + ":" + str(counter)
            )
            counter += 1
        raw = cls(**values).model_dump(mode="json")
        result[collection].append(raw)
        return raw

    def mark(raw, *keys):
        if raw["origin"] == "imported":
            raw["native_presence"] = list(dict.fromkeys([*raw["native_presence"], *keys]))

    def remove_cm(cm_id):
        result["concept_mappings"] = [
            c for c in result["concept_mappings"] if c["id"] != cm_id
        ]
        result["mapping_nodes"] = [
            n for n in result["mapping_nodes"] if n["concept_mapping_id"] != cm_id
        ]
        result["extension_v4"]["legacy_mapping_ids"] = {
            old: new
            for old, new in result["extension_v4"]["legacy_mapping_ids"].items()
            if new != cm_id
        }

    for type_id, analysis in old.items():
        if not any(str(m.type_id) == type_id for m in requested):
            remove_cm(str(analysis.concept_mapping_id))

    for mapping in requested:
        concept = draft.type_by_id().get(mapping.type_id)
        if concept is None:
            raise ValueError("每个已存在的业务对象只允许一个数据映射")
        properties = {
            p.technical_name: p for p in draft.effective_properties(mapping.type_id)
        }
        if set(mapping.fields) - properties.keys() or "__key" in mapping.fields:
            raise ValueError("映射引用了未定义或保留的属性")
        analysis = views.analyze(mapping.type_id)
        if analysis.reason:
            raise ValueError("复杂映射：暂只读（" + analysis.reason + "）")
        if analysis.mapping and mapping == analysis.mapping:
            continue
        model = next(
            (
                m
                for m in result["semantic_models"]
                if connection_alias(SemanticModel.model_validate(m))
                == mapping.connection_alias
            ),
            None,
        )
        if model is None:
            model = add(
                "semantic_models",
                SemanticModel,
                name=mapping.connection_alias,
                map_name=mapping.connection_alias,
                custom_extensions=[
                    dict(
                        vendor_name="ONTOFOUNDRY",
                        data=json.dumps(
                            {"connection_alias": mapping.connection_alias},
                            ensure_ascii=False,
                        ),
                    )
                ],
            )
        # Explicit authoring of a connection always records its alias in the vendor extension.
        if not any(
            e["vendor_name"] == "ONTOFOUNDRY" and "connection_alias" in e["data"]
            for e in model["custom_extensions"]
        ):
            model["custom_extensions"].append(
                dict(
                    vendor_name="ONTOFOUNDRY",
                    data=json.dumps(
                        {"connection_alias": mapping.connection_alias}, ensure_ascii=False
                    ),
                )
            )
            mark(model, "custom_extensions")
        source = (
            quote_identifier(mapping.schema_name) + "." if mapping.schema_name else ""
        ) + quote_identifier(mapping.table_name)
        cm = next(
            (
                c
                for c in result["concept_mappings"]
                if c["id"] == str(analysis.concept_mapping_id)
            ),
            None,
        )
        dataset = next(
            (
                d
                for d in result["datasets"]
                if d["id"] == str(analysis.dataset_id)
                and d["semantic_model_id"] == model["id"]
            ),
            None,
        )
        if dataset and dataset["source"] != source:
            # A shared dataset's source must not be changed by editing one concept.
            shared = any(
                c["id"] != (cm or {}).get("id")
                and c["semantic_model_id"] == model["id"]
                and any(
                    n["concept_mapping_id"] == c["id"]
                    and n.get("expression", "")
                    and n["expression"].startswith(dataset["name"] + ".")
                    for n in result["mapping_nodes"]
                )
                for c in result["concept_mappings"]
            )
            if shared:
                dataset = None
        if dataset is None:
            name = concept.concept
            names = {
                d["name"]
                for d in result["datasets"]
                if d["semantic_model_id"] == model["id"]
            }
            if name in names:
                name += "_" + mapping.id.hex[:8]
            dataset = add(
                "datasets",
                Dataset,
                semantic_model_id=model["id"],
                name=name,
                source=source,
                primary_key=[mapping.key_column],
            )
        else:
            dataset["source"] = source
            # The concept key is the object root; do not overwrite a shared dataset's native primary key.
            mark(dataset, "source")
        if cm is None:
            cm = add(
                "concept_mappings",
                ConceptMapping,
                semantic_model_id=model["id"],
                concept_id=dict(kind="object_type", ref=concept.id),
            )
        else:
            cm["semantic_model_id"] = model["id"]
        result["extension_v4"]["legacy_mapping_ids"][str(mapping.id)] = cm["id"]
        nodes = [n for n in result["mapping_nodes"] if n["concept_mapping_id"] == cm["id"]]
        previous_dataset = views.datasets.get(analysis.dataset_id)
        if previous_dataset and previous_dataset.name != dataset["name"]:
            for node in nodes:
                if (old_ref := column_reference(node.get("expression"))) and old_ref[
                    0
                ] == previous_dataset.name:
                    node["expression"] = reference(dataset["name"], old_ref[1])
        root = next((n for n in nodes if n["slot"] == "object_mappings"), None)
        expr = reference(dataset["name"], mapping.key_column)
        if root is None:
            root = add(
                "mapping_nodes",
                MappingNode,
                concept_mapping_id=cm["id"],
                slot="object_mappings",
                kind="object",
                expression=expr,
                position=0,
            )
        else:
            root["expression"] = expr
            mark(root, "expression")
        link_root = next((n for n in nodes if n["slot"] == "link_mappings"), None)
        if link_root is None:
            link_root = add(
                "mapping_nodes",
                MappingNode,
                concept_mapping_id=cm["id"],
                slot="link_mappings",
                kind="link",
                position=0,
            )
            root_object = add(
                "mapping_nodes",
                MappingNode,
                concept_mapping_id=cm["id"],
                parent_id=link_root["id"],
                slot="object_mapping",
                kind="object",
                expression=expr,
                position=0,
            )
        else:
            root_object = next(
                n
                for n in nodes
                if n["parent_id"] == link_root["id"] and n["slot"] == "object_mapping"
            )
            root_object["expression"] = expr
            mark(root_object, "expression")
        for prop_name, prop in properties.items():
            child = next(
                (
                    n
                    for n in nodes
                    if n["kind"] == "link" and n["relationship"] == prop_name
                ),
                None,
            )
            if prop_name not in mapping.fields:
                if child:
                    ids = {
                        child["id"],
                        *[n["id"] for n in nodes if n["parent_id"] == child["id"]],
                    }
                    result["mapping_nodes"] = [
                        n for n in result["mapping_nodes"] if n["id"] not in ids
                    ]
                continue
            column = mapping.fields[prop_name]
            field = next(
                (
                    f
                    for f in result["dataset_fields"]
                    if f["dataset_id"] == dataset["id"] and f["name"] == prop_name
                ),
                None,
            )
            expression = dict(
                dialects=[dict(dialect="ANSI_SQL", expression=quote_identifier(column))]
            )
            if field is None:
                field = add(
                    "dataset_fields",
                    DatasetField,
                    dataset_id=dataset["id"],
                    name=prop_name,
                    expression=expression,
                )
            elif field["expression"] != expression:
                # Mapping expressions can refer to a physical column directly. Keep a native field shared by other trees intact.
                field = None
            value_expr = reference(dataset["name"], prop_name if field else column)
            if child is None:
                position = (
                    max(
                        (
                            n["position"]
                            for n in result["mapping_nodes"]
                            if n["parent_id"] == link_root["id"]
                            and n["slot"] == "children"
                            and n["position"] is not None
                        ),
                        default=-1,
                    )
                    + 1
                )
                child = add(
                    "mapping_nodes",
                    MappingNode,
                    concept_mapping_id=cm["id"],
                    parent_id=link_root["id"],
                    slot="children",
                    kind="link",
                    relationship=prop_name,
                    position=position,
                )
                add(
                    "mapping_nodes",
                    MappingNode,
                    concept_mapping_id=cm["id"],
                    parent_id=child["id"],
                    slot="object_mapping",
                    kind="object",
                    concept=prop.roles[0].concept,
                    expression=value_expr,
                    position=0,
                )
            else:
                obj = next(
                    n
                    for n in result["mapping_nodes"]
                    if n["parent_id"] == child["id"] and n["slot"] == "object_mapping"
                )
                obj["expression"] = value_expr
                mark(obj, "expression")

    updated = OntologyDraft.model_validate(result)
    updated_views = SemanticViews(updated)
    mapped = {
        str(t.id): a.mapping
        for t in updated.object_types
        if (a := updated_views.analyze(t.id)).mapping
    }
    for link_id, value in joins.items():
        link = next(
            (
                relation
                for relation in updated.link_types
                if str(relation.id) == link_id and relation.source_type_id is not None
            ),
            None,
        )
        if link is None:
            continue
        parsed_join = role_join_input(value)
        value = parsed_join.model_dump(mode="json") if parsed_join else None
        previous = authoring_join(views, link_id)
        current_join = authoring_join(updated_views, link_id)
        if value == (previous.model_dump(mode="json") if previous else None) and value == (
            current_join.model_dump(mode="json") if current_join else None
        ):
            continue
        source, target = (
            mapped.get(str(link.source_type_id)),
            mapped.get(str(link.target_type_id)),
        )
        if value and (not source or not target):
            raise ValueError("配置关系映射前，请先配置两端业务对象的数据映射")
        src_analysis, dst_analysis = (
            updated_views.analyze(link.source_type_id),
            updated_views.analyze(link.target_type_id),
        )
        src, dst = (
            updated_views.datasets.get(src_analysis.dataset_id),
            updated_views.datasets.get(dst_analysis.dataset_id),
        )
        # Cross-source joins are representable natively, but never executable.
        if value and source.connection_alias != target.connection_alias:
            bridge = next(
                (
                    m
                    for m in result["semantic_models"]
                    if m["name"] == "cross_connection_" + link.id.hex
                ),
                None,
            )
            if bridge is None:
                bridge = add(
                    "semantic_models",
                    SemanticModel,
                    name="cross_connection_" + link.id.hex,
                    map_name="cross_connection_" + link.id.hex,
                    custom_extensions=[
                        dict(
                            vendor_name="ONTOFOUNDRY",
                            data=json.dumps(
                                {
                                    "legacy_connection_aliases": {
                                        src.name: source.connection_alias,
                                        dst.name: target.connection_alias,
                                    },
                                    "read_only_reason": "cross_connection",
                                }
                            ),
                        )
                    ],
                )
            for d in (src, dst):
                if not any(
                    item["semantic_model_id"] == bridge["id"] and item["name"] == d.name
                    for item in result["datasets"]
                ):
                    add(
                        "datasets",
                        Dataset,
                        semantic_model_id=bridge["id"],
                        name=d.name,
                        source=d.source,
                    )
            model_id = bridge["id"]
        elif src and dst and src.semantic_model_id == dst.semantic_model_id:
            model_id = str(src.semantic_model_id)
        else:
            if value:
                raise ValueError("两端语义模型不同，关系暂只读")
            continue
        names = {
            link.technical_name,
            link.technical_name + "__" + link.id.hex,
            link.technical_name
            + "__"
            + uuid5(
                draft.workspace_id,
                f"v3:ontology_mappings/{updated_views.models[src.semantic_model_id].map_name}/relationships/{link.id}",
            ).hex,
        }
        candidates = [
            r
            for r in result["dataset_relationships"]
            if r["semantic_model_id"] == model_id
            and r["name"] in names
            and {r["from"], r["to"]} == {src.name, dst.name}
        ]
        relationship = candidates[0] if len(candidates) == 1 else None
        if value is None:
            if relationship:
                result["dataset_relationships"].remove(relationship)
            owner_cm = updated_views.analyze(link.owner_type_id).concept_mapping_id
            deleted = {
                n["id"]
                for n in result["mapping_nodes"]
                if n["concept_mapping_id"] == str(owner_cm)
                and n["kind"] == "link"
                and n["relationship"] == link.technical_name
            }
            while True:
                descendants = {
                    n["id"] for n in result["mapping_nodes"] if n["parent_id"] in deleted
                } - deleted
                if not descendants:
                    break
                deleted.update(descendants)
            result["mapping_nodes"] = [
                n for n in result["mapping_nodes"] if n["id"] not in deleted
            ]
            continue
        a, b = value["owner_columns"], value["role_columns"]
        if link.endpoint_direction == "reverse":
            a, b = b, a
        if (
            not a
            or len(a) != len(b)
            or any(not isinstance(c, str) or not c for c in [*a, *b])
        ):
            raise ValueError("连接列的数量不一致或为空")

        def ensure(dataset, column, model_id=model_id):
            raw_dataset = next(
                d
                for d in result["datasets"]
                if d["semantic_model_id"] == model_id and d["name"] == dataset.name
            )
            fields = [
                f for f in result["dataset_fields"] if f["dataset_id"] == raw_dataset["id"]
            ]
            return ensure_column_field(
                fields,
                dataset.name,
                column,
                lambda values: add(
                    "dataset_fields", DatasetField, dataset_id=raw_dataset["id"], **values
                ),
            )

        a = [ensure(src, c) for c in a]
        b = [ensure(dst, c) for c in b]
        if relationship:
            relationship.update(
                {"from": src.name, "to": dst.name, "from_columns": a, "to_columns": b}
            )
            mark(relationship, "from", "to", "from_columns", "to_columns")
        else:
            name = link.technical_name
            if any(
                r["semantic_model_id"] == model_id and r["name"] == name
                for r in result["dataset_relationships"]
            ):
                name += "__" + link.id.hex
            add(
                "dataset_relationships",
                DatasetRelationship,
                semantic_model_id=model_id,
                name=name,
                **{"from": src.name},
                to=dst.name,
                from_columns=a,
                to_columns=b,
            )
        # Bind the native join to the owner mapping tree; SQL orientation is a separate endpoint view.
        owner_analysis = updated_views.analyze(link.owner_type_id)
        root = next(
            (
                n
                for n in result["mapping_nodes"]
                if n["concept_mapping_id"] == str(owner_analysis.concept_mapping_id)
                and n["slot"] == "link_mappings"
            ),
            None,
        )
        if root and source.connection_alias == target.connection_alias:
            child = next(
                (
                    n
                    for n in result["mapping_nodes"]
                    if n["parent_id"] == root["id"]
                    and n["relationship"] == link.technical_name
                ),
                None,
            )
            if not child:
                position = (
                    max(
                        (
                            n["position"]
                            for n in result["mapping_nodes"]
                            if n["parent_id"] == root["id"]
                            and n["slot"] == "children"
                            and n["position"] is not None
                        ),
                        default=-1,
                    )
                    + 1
                )
                child = add(
                    "mapping_nodes",
                    MappingNode,
                    concept_mapping_id=root["concept_mapping_id"],
                    parent_id=root["id"],
                    slot="children",
                    kind="link",
                    relationship=link.technical_name,
                    position=position,
                )
                add(
                    "mapping_nodes",
                    MappingNode,
                    concept_mapping_id=root["concept_mapping_id"],
                    parent_id=child["id"],
                    slot="object_mapping",
                    kind="object",
                    concept=link.roles[0].concept,
                    expression=reference(src.name, a[0])
                    if link.endpoint_direction == "forward"
                    else reference(dst.name, b[0]),
                    position=0,
                )
            else:
                obj = next(
                    n
                    for n in result["mapping_nodes"]
                    if n["parent_id"] == child["id"] and n["slot"] == "object_mapping"
                )
                obj["expression"] = (
                    reference(src.name, a[0])
                    if link.endpoint_direction == "forward"
                    else reference(dst.name, b[0])
                )
                mark(obj, "expression")
    return OntologyDraft.model_validate(result).model_dump(mode="json")
