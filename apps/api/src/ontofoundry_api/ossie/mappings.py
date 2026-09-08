"""Translate between internal data mappings and Ossie `ontology_mappings`.

Both sides answer the same question — which table and column populate a concept
and its relationships — in different shapes. Ossie declares a logical
`semantic_model` and maps concepts onto it with expressions; the internal model
names a data source, a table, a key column and a column per attribute. The
translation only handles the plain `dataset.column` expressions this writes;
anything more (computed SQL, referent chains) is reported rather than half-read,
because guessing a column out of arbitrary SQL would silently produce a wrong
mapping.

Link mappings are trees, and the spec ties a node's level to the arity of the
relationship it names: a top-level node names a unary relationship, its children
name binary ones, and so on. So the concept's own objects are mapped once at the
root and every attribute hangs under it as a child.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid5

from ontofoundry_api.domain.models import (
    DataJoin,
    DataMapping,
    LinkTypeDefinition,
    ObjectTypeDefinition,
)

COLUMN_RE = re.compile(
    r"^\s*(?:(?P<dataset>[A-Za-z_][\w]*)\.)?(?P<column>[A-Za-z_][\w]*)\s*$"
)


def _source(mapping: DataMapping) -> str:
    return (
        f"{mapping.schema_name}.{mapping.table_name}"
        if mapping.schema_name
        else mapping.table_name
    )


def compile_mappings(
    mappings: list[DataMapping],
    objects: list[ObjectTypeDefinition],
    links: list[LinkTypeDefinition],
) -> list[dict[str, Any]]:
    """One `OntologyMap` per data source, in a deterministic order."""
    by_type = {item.id: item for item in objects}
    grouped: dict[str, list[DataMapping]] = {}
    for mapping in mappings:
        if mapping.type_id in by_type:
            grouped.setdefault(mapping.connection_alias, []).append(mapping)

    documents: list[dict[str, Any]] = []
    for alias in sorted(grouped):
        entries = sorted(
            grouped[alias], key=lambda item: by_type[item.type_id].technical_name
        )
        datasets: list[dict[str, Any]] = []
        concept_mappings: list[dict[str, Any]] = []
        dataset_by_type: dict[UUID, str] = {}
        for mapping in entries:
            object_type = by_type[mapping.type_id]
            dataset = object_type.technical_name
            dataset_by_type[mapping.type_id] = dataset
            datasets.append(
                {
                    "name": dataset,
                    "source": _source(mapping),
                    "primary_key": [mapping.key_column],
                    "description": object_type.description or object_type.name,
                    # Inside a semantic model an expression is dialect-tagged;
                    # on the ontology side it is a plain string.
                    "fields": [
                        {
                            "name": name,
                            "expression": {
                                "dialects": [{"dialect": "ANSI_SQL", "expression": column}]
                            },
                        }
                        for name, column in sorted(mapping.fields.items())
                    ],
                }
            )
            # The root node maps this concept's own objects; every binary
            # relationship read from the same table is a child of it, which is
            # what the spec's level-equals-arity rule requires.
            concept_mappings.append(
                {
                    "concept": dataset,
                    "object_mappings": [{"expression": f"{dataset}.{mapping.key_column}"}],
                    "link_mappings": [
                        {
                            "object_mapping": {
                                "expression": f"{dataset}.{mapping.key_column}"
                            },
                            "children": [
                                {
                                    "relationship": name,
                                    "object_mapping": {
                                        "expression": f"{dataset}.{column}"
                                    },
                                }
                                for name, column in sorted(mapping.fields.items())
                            ],
                        }
                    ],
                }
            )

        relationships: list[dict[str, Any]] = []
        for link in sorted(links, key=lambda item: item.technical_name):
            join = link.data_join
            source = dataset_by_type.get(link.source_type_id)
            target = dataset_by_type.get(link.target_type_id)
            if not join or not source or not target:
                continue
            relationships.append(
                {
                    "name": link.technical_name,
                    "from": source,
                    "to": target,
                    "from_columns": [join.source_column],
                    "to_columns": [join.target_column],
                }
            )
            owner = dataset_by_type.get(link.owner_type_id)
            entry = next(
                (item for item in concept_mappings if item["concept"] == owner), None
            )
            if entry is not None:
                entry["link_mappings"][0]["children"].append(
                    {
                        "relationship": link.technical_name,
                        "object_mapping": {
                            "concept": target if owner == source else source,
                            "expression": f"{owner}.{join.source_column if owner == source else join.target_column}",
                        },
                    }
                )

        for entry in concept_mappings:
            # A root that maps nothing further is noise; the object mapping
            # above already says how the concept's objects are found.
            if not entry["link_mappings"][0]["children"]:
                del entry["link_mappings"]

        semantic_model: dict[str, Any] = {"name": alias, "datasets": datasets}
        if relationships:
            semantic_model["relationships"] = relationships
        documents.append(
            {
                "name": alias,
                "description": f"{alias} 的数据映射",
                "semantic_model": semantic_model,
                "concept_mappings": concept_mappings,
            }
        )
    return documents


def _column(expression: Any, dataset: str, fields: dict[str, str] | None = None) -> str | None:
    match = COLUMN_RE.match(str(expression or ""))
    if not match:
        return None
    if match.group("dataset") and match.group("dataset") != dataset:
        return None
    name = match.group("column")
    # A dataset may declare logical fields over its own columns, in which case
    # the mapping names the field and the column is one level down.
    return (fields or {}).get(name, name)


def _dataset_fields(dataset: dict[str, Any]) -> dict[str, str]:
    """Logical field name to physical column, for the plain single-column ones."""
    resolved: dict[str, str] = {}
    for field in dataset.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        dialects = (field.get("expression") or {}).get("dialects") or []
        text = next(
            (
                str(item.get("expression"))
                for item in dialects
                if isinstance(item, dict) and item.get("dialect") == "ANSI_SQL"
            ),
            None,
        )
        match = COLUMN_RE.match(text or "")
        if name and match and match.group("column") != name:
            resolved[name] = match.group("column")
    return resolved


def _link_nodes(
    nodes: Any, depth: int = 1
) -> list[tuple[int, dict[str, Any]]]:
    """Every link mapping with the arity its level implies.

    A root without children is read as arity two: that is the flat shape older
    OntoFoundry exports wrote, and reading it keeps those files importable.
    """
    found: list[tuple[int, dict[str, Any]]] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        children = [item for item in node.get("children") or [] if isinstance(item, dict)]
        found.append((2 if depth == 1 and not children else depth, node))
        found.extend(_link_nodes(children, depth + 1))
    return found


def parse_mappings(
    document: dict[str, Any],
    objects: list[ObjectTypeDefinition],
    workspace_id: str,
    skip,
) -> list[DataMapping]:
    """Read the mappings back; report anything that is not a plain column."""
    maps = document.get("ontology_mappings") or []
    by_concept = {item.technical_name: item for item in objects}
    results: list[DataMapping] = []
    for index, entry in enumerate(maps):
        if not isinstance(entry, dict):
            continue
        model = entry.get("semantic_model") or {}
        alias = str(entry.get("name") or model.get("name") or "imported")
        datasets = {
            str(item.get("name")): item
            for item in model.get("datasets") or []
            if isinstance(item, dict)
        }
        if model.get("custom_extensions") or any(
            item.get("custom_extensions") for item in datasets.values()
        ):
            skip(
                f"ontology_mappings[{index}].custom_extensions",
                "厂商扩展（custom_extensions）没有对应位置，未导入",
            )
        for concept_mapping in entry.get("concept_mappings") or []:
            if not isinstance(concept_mapping, dict):
                continue
            concept = str(concept_mapping.get("concept") or "")
            path = f"ontology_mappings[{index}].{concept}"
            object_type = by_concept.get(concept)
            if object_type is None:
                skip(path, "映射指向的概念没有导入为业务对象")
                continue
            object_mappings = concept_mapping.get("object_mappings") or []
            expression = next(
                (
                    item.get("expression")
                    for item in object_mappings
                    if isinstance(item, dict) and item.get("expression")
                ),
                None,
            )
            if any(
                isinstance(item, dict) and item.get("referent_mappings")
                for item in object_mappings
            ):
                skip(path, "referent_mappings（按引用关系定位对象）暂不支持")

            nodes = _link_nodes(concept_mapping.get("link_mappings"))
            # The root of the tree maps the concept's own objects, so it names
            # the same column `object_mappings` does — either one identifies the
            # dataset and the key column.
            root = next((node for arity, node in nodes if arity == 1), None)
            root_expression = (
                (root.get("object_mapping") or {}).get("expression") if root else None
            )
            dataset_name = next(
                (
                    name
                    for name in datasets
                    for text in (str(expression or ""), str(root_expression or ""))
                    if text.startswith(f"{name}.")
                ),
                concept if concept in datasets else None,
            )
            dataset = datasets.get(dataset_name or "")
            if dataset is None:
                skip(path, "找不到这个概念对应的 dataset")
                continue
            if dataset.get("unique_keys"):
                skip(f"{path}.unique_keys", "dataset 的唯一键在内置模型里没有位置，未导入")
            columns = _dataset_fields(dataset)

            key_column = _column(expression, dataset_name or "", columns) or _column(
                root_expression, dataset_name or "", columns
            )
            if not key_column:
                keys = dataset.get("primary_key") or []
                key_column = str(keys[0]) if keys else None
            if not key_column:
                skip(path, "对象映射不是单列表达式，也没有 primary_key，无法确定键列")
                continue

            attributes = {item.technical_name for item in object_type.attributes}
            fields: dict[str, str] = {}
            for arity, link_mapping in nodes:
                name = str(link_mapping.get("relationship") or "")
                if arity == 1:
                    if name:
                        skip(f"{path}.{name}", "一元关系的映射暂不支持")
                    continue
                if arity > 2:
                    skip(
                        f"{path}.{name or '(未命名)'}",
                        "三元及以上关系的映射暂不支持，内置模型只有二元关系",
                    )
                    continue
                if name not in attributes:
                    continue  # relations are mapped through data_join, not fields
                column = _column(
                    (link_mapping.get("object_mapping") or {}).get("expression"),
                    dataset_name or "",
                    columns,
                )
                if not column:
                    skip(f"{path}.{name}", "字段映射不是单列表达式，未导入这一列")
                    continue
                fields[name] = column

            source = str(dataset.get("source") or "")
            schema_name, _, table_name = source.rpartition(".")
            results.append(
                DataMapping(
                    id=uuid5(UUID(str(workspace_id)), f"mapping:{alias}.{concept}"),
                    type_id=object_type.id,
                    connection_alias=alias,
                    table_name=table_name or source or concept,
                    schema_name=schema_name or None,
                    key_column=key_column,
                    fields=fields,
                )
            )
    return results


def parse_joins(
    document: dict[str, Any],
    objects: list[ObjectTypeDefinition],
    links: list[LinkTypeDefinition],
) -> None:
    """Fill in relation join columns from the semantic model, in place."""
    datasets_by_concept = {item.technical_name: item.id for item in objects}
    for entry in document.get("ontology_mappings") or []:
        if not isinstance(entry, dict):
            continue
        model = entry.get("semantic_model") or {}
        for relationship in model.get("relationships") or []:
            if not isinstance(relationship, dict):
                continue
            source = datasets_by_concept.get(str(relationship.get("from") or ""))
            target = datasets_by_concept.get(str(relationship.get("to") or ""))
            columns = relationship.get("from_columns") or []
            targets = relationship.get("to_columns") or []
            if not source or not target or len(columns) != 1 or len(targets) != 1:
                continue
            for link in links:
                if link.technical_name != str(relationship.get("name") or ""):
                    continue
                if {link.source_type_id, link.target_type_id} != {source, target}:
                    continue
                forward = link.source_type_id == source
                link.data_join = DataJoin(
                    source_column=str(columns[0] if forward else targets[0]),
                    target_column=str(targets[0] if forward else columns[0]),
                )
