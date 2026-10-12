"""Explicit native semantic edits, with lossless untouched nodes and references."""

import re
from collections import defaultdict
from copy import deepcopy
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import PydanticUndefined
from sqlglot import Dialect
from sqlglot.errors import SqlglotError
from sqlglot.tokens import TokenType

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.models_v3 import V3_COLLECTION_MODELS
from ontofoundry_api.services.errors import ServiceError

COLLECTIONS = {
    "semantic_model": "semantic_models",
    "dataset": "datasets",
    "dataset_field": "dataset_fields",
    "dataset_relationship": "dataset_relationships",
    "metric": "metrics",
    "concept_mapping": "concept_mappings",
}
FIELDS = {
    "semantic_model": {
        "name",
        "description",
        "ai_context",
        "custom_extensions",
        "map_name",
        "map_description",
    },
    "dataset": {
        "name",
        "source",
        "description",
        "primary_key",
        "unique_keys",
        "ai_context",
        "custom_extensions",
    },
    "dataset_field": {
        "name",
        "expression",
        "datatype",
        "description",
        "dimension",
        "label",
        "ai_context",
        "custom_extensions",
    },
    "dataset_relationship": {
        "name",
        "from",
        "to",
        "from_columns",
        "to_columns",
        "ai_context",
        "custom_extensions",
    },
    "metric": {
        "name",
        "expression",
        "datatype",
        "description",
        "ai_context",
        "custom_extensions",
    },
    "concept_mapping": {"concept_id"},
}
NODE_FIELDS = {"parent_id", "slot", "kind", "relationship", "concept", "expression"}


class SemanticChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    operation: str = "update"
    id: UUID
    parent_id: UUID | None = None
    values: dict = Field(default_factory=dict)
    unset_fields: list[str] = Field(default_factory=list)
    nodes: list[dict] | None = None
    display_name: str | None = None


def invalid(message, code="SEMANTIC_EDIT_INVALID", **details):
    return ServiceError(message, code=code, status_code=422, details=details or None)


def identifier_edits(
    expression, *, dataset=None, field=None, metric=None, replacement, dialect=""
):
    """Edit identifier token spans, preserving whitespace, comments and literals."""
    try:
        sql_dialect = {
            "ANSI_SQL": "",
            "POSTGRESQL": "postgres",
            "POSTGRES": "postgres",
            "MYSQL": "mysql",
        }.get(dialect.upper(), dialect.lower())
        tokens = Dialect.get_or_raise(sql_dialect).tokenize(expression)
    except (ValueError, TypeError, SqlglotError) as exc:
        raise invalid(
            "表达式无法安全分析，请先检查方言与表达式", "SEMANTIC_REFERENCE_INVALID"
        ) from exc
    spans = []
    for i, token in enumerate(tokens):
        if token.token_type not in (TokenType.VAR, TokenType.IDENTIFIER):
            continue
        qualified = i + 2 < len(tokens) and tokens[i + 1].token_type == TokenType.DOT
        hit = (
            qualified
            and token.text == dataset
            and (field is None or tokens[i + 2].text == field)
        )
        hit = hit or (
            metric
            and token.text == metric
            and not qualified
            and (i + 1 == len(tokens) or tokens[i + 1].token_type != TokenType.L_PAREN)
            and (i == 0 or tokens[i - 1].token_type != TokenType.DOT)
        )
        if hit:
            part = tokens[i + 2] if field else token
            original = expression[part.start : part.end + 1]
            quote = original[0] if original[0] in ('"', "`") else ""
            if not quote and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", replacement):
                quote = "`" if sql_dialect == "mysql" else '"'
            value = (
                quote + replacement.replace(quote, quote * 2) + quote
                if quote
                else replacement
            )
            spans.append((part.start, part.end + 1, value))
    result = expression
    for start, end, value in reversed(spans):
        result = result[:start] + value + result[end:]
    return result, bool(spans)


def mark(node, field):
    if field.startswith("map_"):
        field = field[4:]
        node["map_presence"] = list(dict.fromkeys([*node.get("map_presence", []), field]))
    else:
        node["native_presence"] = list(
            dict.fromkeys([*node.get("native_presence", []), field])
        )


def patch(node, values, *, unset=(), collection):
    cls = V3_COLLECTION_MODELS[collection]
    result = deepcopy(node)
    for key, value in values.items():
        if result.get(key) != value:
            result[key] = deepcopy(value)
            if key not in {"concept_id", "parent_id", "slot", "kind"}:
                mark(result, key)
    for key in unset:
        model_field = next(
            f for k, f in cls.model_fields.items() if k == key or f.alias == key
        )
        default = model_field.get_default(call_default_factory=True)
        if default is PydanticUndefined:
            raise invalid("不能删除必填字段：" + key)
        result[key] = deepcopy(default)
        if key.startswith("map_"):
            result["map_presence"] = [
                k for k in result.get("map_presence", []) if k != key[4:]
            ]
        else:
            result["native_presence"] = [
                k for k in result.get("native_presence", []) if k != key
            ]
    return cls.model_validate(result).model_dump(mode="json", by_alias=True)


def expressions(snapshot, model_id):
    cm_ids = {
        c["id"] for c in snapshot["concept_mappings"] if c["semantic_model_id"] == model_id
    }
    for node in snapshot["mapping_nodes"]:
        if node["concept_mapping_id"] in cm_ids and node.get("expression") is not None:
            yield node, "expression", ""
    for metric in snapshot["metrics"]:
        if metric["semantic_model_id"] == model_id:
            for dialect in metric["expression"]["dialects"]:
                yield dialect, "expression", dialect["dialect"]


def references(snapshot, kind, target):
    result = []

    def add(collection, node, field):
        result.append(
            dict(
                kind=collection,
                id=node["id"],
                name=node.get("name", node.get("relationship") or "映射节点"),
                field=field,
            )
        )

    if kind == "semantic_model":
        for collection in (
            "datasets",
            "dataset_relationships",
            "metrics",
            "concept_mappings",
        ):
            for node in snapshot[collection]:
                if node["semantic_model_id"] == target["id"]:
                    add(collection, node, "semantic_model_id")
        return result
    if kind not in {"dataset", "dataset_field", "metric"}:
        return result
    ds = (
        target
        if kind == "dataset"
        else next(
            (d for d in snapshot["datasets"] if d["id"] == target.get("dataset_id")), None
        )
    )
    mid = target.get("semantic_model_id") or ds["semantic_model_id"]
    args = (
        {
            "dataset": ds["name"],
            "field": target["name"] if kind == "dataset_field" else None,
        }
        if ds
        else {"metric": target["name"]}
    )
    for node, key, dialect in expressions(snapshot, mid):
        _, found = identifier_edits(
            node[key], **args, replacement="__reference_check__", dialect=dialect
        )
        if found:
            # Dialects do not have IDs. Locate their metric without changing the payload.
            owner = next(
                (
                    m
                    for m in snapshot["metrics"]
                    if any(d is node for d in m["expression"]["dialects"])
                ),
                node,
            )
            add("metrics" if owner is not node else "mapping_nodes", owner, key)
    if ds:
        for rel in snapshot["dataset_relationships"]:
            if rel["semantic_model_id"] != mid:
                continue
            for side in ("from", "to"):
                if rel[side] == ds["name"] and (
                    kind == "dataset" or target["name"] in rel[side + "_columns"]
                ):
                    add("dataset_relationships", rel, side)
        if kind == "dataset_field":
            if target["name"] in ds["primary_key"]:
                add("datasets", ds, "primary_key")
            if any(target["name"] in key for key in ds["unique_keys"]):
                add("datasets", ds, "unique_keys")
    return result


def rename(snapshot, kind, before, after):
    if (
        kind not in {"dataset", "dataset_field", "metric"}
        or before["name"] == after["name"]
    ):
        return
    ds = (
        before
        if kind == "dataset"
        else next(
            (d for d in snapshot["datasets"] if d["id"] == before.get("dataset_id")), None
        )
    )
    mid = before.get("semantic_model_id") or ds["semantic_model_id"]
    args = (
        {
            "dataset": ds["name"],
            "field": before["name"] if kind == "dataset_field" else None,
        }
        if ds
        else {"metric": before["name"]}
    )
    for node, key, dialect in expressions(snapshot, mid):
        text, changed = identifier_edits(
            node[key], **args, replacement=after["name"], dialect=dialect
        )
        if changed:
            node[key] = text
            if "id" in node:
                mark(node, key)
    if ds:
        for rel in snapshot["dataset_relationships"]:
            if rel["semantic_model_id"] != mid:
                continue
            for side in ("from", "to"):
                if rel[side] != ds["name"]:
                    continue
                key = side if kind == "dataset" else side + "_columns"
                value = (
                    after["name"]
                    if kind == "dataset"
                    else [after["name"] if v == before["name"] else v for v in rel[key]]
                )
                if value != rel[key]:
                    rel[key] = value
                    mark(rel, key)
        if kind == "dataset_field":
            for key in ("primary_key", "unique_keys"):
                value = (
                    [after["name"] if v == before["name"] else v for v in ds[key]]
                    if key == "primary_key"
                    else [
                        [after["name"] if v == before["name"] else v for v in group]
                        for group in ds[key]
                    ]
                )
                if value != ds[key]:
                    ds[key] = value
                    mark(ds, key)


def replace_nodes(snapshot, cm, nodes):
    old = {
        n["id"]: n for n in snapshot["mapping_nodes"] if n["concept_mapping_id"] == cm["id"]
    }
    occupied = {n["id"] for n in snapshot["mapping_nodes"] if n["id"] not in old}
    result, counters = [], defaultdict(int)
    for values in nodes:
        if set(values) - NODE_FIELDS - {"id"}:
            raise invalid("映射节点包含内部或未知字段")
        nid = str(UUID(values.get("id") or str(uuid4())))
        if nid in occupied or any(n["id"] == nid for n in result):
            raise invalid("映射节点 ID 重复或属于其他映射")
        node = old.get(nid) or dict(
            id=nid,
            concept_mapping_id=cm["id"],
            origin="platform",
            native_presence=[],
            position=0,
        )
        node = patch(
            node, {k: v for k, v in values.items() if k != "id"}, collection="mapping_nodes"
        )
        group = (node["parent_id"], node["slot"])
        node["position"] = counters[group]
        counters[group] += 1
        result.append(node)
    snapshot["mapping_nodes"] = [
        n for n in snapshot["mapping_nodes"] if n["concept_mapping_id"] != cm["id"]
    ] + result
    for parent in result:
        for slot in ("object_mapping", "children", "referent_mappings"):
            if any(n["parent_id"] == parent["id"] and n["slot"] == slot for n in result):
                mark(parent, slot)
    if any(n["slot"] == "object_mappings" for n in result):
        mark(cm, "object_mappings")
    if any(n["slot"] == "link_mappings" for n in result):
        mark(cm, "link_mappings")


def apply_changes(snapshot, changes):
    result = deepcopy(snapshot)
    for change in changes:
        if change.kind not in COLLECTIONS or change.operation not in {
            "create",
            "update",
            "delete",
        }:
            raise invalid("未知的语义对象或编辑操作")
        collection = COLLECTIONS[change.kind]
        target_id = str(change.id)
        allowed = FIELDS[change.kind]
        if set(change.values) - allowed or set(change.unset_fields) - allowed:
            raise invalid("编辑包含内部或不属于当前对象的字段")
        if set(change.values) & set(change.unset_fields):
            raise invalid("同一字段不能同时设置和删除")
        old = next((n for n in result[collection] if n["id"] == target_id), None)
        if change.operation == "create":
            if any(
                n["id"] == target_id for key in V3_COLLECTION_MODELS for n in result[key]
            ):
                raise invalid("元素 ID 已存在")
            parent = str(change.parent_id) if change.parent_id else None
            parent_key = (
                "dataset_id" if change.kind == "dataset_field" else "semantic_model_id"
            )
            old = dict(
                id=target_id,
                origin="platform",
                native_presence=[],
                position=max(
                    (
                        n.get("position") or 0
                        for n in result[collection]
                        if n.get(parent_key) == parent
                    ),
                    default=-1,
                )
                + 1,
            )
            if change.kind != "semantic_model":
                old[parent_key] = parent
            else:
                old["map_presence"] = ["concept_mappings"]
        elif old is None:
            raise invalid("语义对象不存在，请重新读取", "SEMANTIC_ELEMENT_NOT_FOUND")
        if change.operation == "delete":
            refs = references(result, change.kind, old)
            if refs:
                raise invalid(
                    "元素仍被引用，请先解除引用",
                    "SEMANTIC_ELEMENT_REFERENCED",
                    references=refs,
                )
            result[collection] = [n for n in result[collection] if n["id"] != target_id]
            if change.kind == "dataset":
                result["dataset_fields"] = [
                    n for n in result["dataset_fields"] if n["dataset_id"] != target_id
                ]
            if change.kind == "concept_mapping":
                result["mapping_nodes"] = [
                    n
                    for n in result["mapping_nodes"]
                    if n["concept_mapping_id"] != target_id
                ]
            result["extension_v4"]["display_names"].pop(target_id, None)
            continue
        node = patch(old, change.values, unset=change.unset_fields, collection=collection)
        if change.operation == "update":
            rename(result, change.kind, old, node)
            result[collection] = [
                node if n["id"] == target_id else n for n in result[collection]
            ]
        else:
            result[collection].append(node)
        if change.nodes is not None:
            if change.kind != "concept_mapping":
                raise invalid("只有概念映射可以编辑映射树")
            replace_nodes(result, node, change.nodes)
        if change.display_name is not None:
            names = result["extension_v4"]["display_names"]
            if change.display_name:
                names[target_id] = change.display_name
            else:
                names.pop(target_id, None)
    for rel in result["dataset_relationships"]:
        for side in ("from", "to"):
            dataset = next(
                (
                    d
                    for d in result["datasets"]
                    if d["semantic_model_id"] == rel["semantic_model_id"]
                    and d["name"] == rel[side]
                ),
                None,
            )
            if dataset is None:
                raise invalid(
                    "连接数据集不存在：" + rel[side], "SEMANTIC_REFERENCE_INVALID"
                )
            fields = {
                f["name"]
                for f in result["dataset_fields"]
                if f["dataset_id"] == dataset["id"]
            }
            missing = [c for c in rel[side + "_columns"] if c not in fields]
            if missing:
                raise invalid(
                    "连接字段不存在：" + dataset["name"] + "." + "、".join(missing),
                    "SEMANTIC_REFERENCE_INVALID",
                )
    existing_ids = {
        n["id"] for collection in V3_COLLECTION_MODELS for n in result[collection]
    }
    result["extension_v4"]["display_names"] = {
        key: value
        for key, value in result["extension_v4"]["display_names"].items()
        if key in existing_ids
    }
    return OntologyDraft.model_validate(result).model_dump(mode="json")


def edit_scope(original, edited, changes):
    """Primary aggregates are whole; induced reference edits are field scoped."""
    primary = defaultdict(set)
    for change in changes:
        primary[COLLECTIONS[change.kind]].add(str(change.id))
        if change.kind == "concept_mapping":
            primary["mapping_nodes"].update(
                n["id"]
                for snap in (original, edited)
                for n in snap["mapping_nodes"]
                if n["concept_mapping_id"] == str(change.id)
            )
    scope = {}
    for collection in (*COLLECTIONS.values(), "mapping_nodes"):
        old, new = ({n["id"]: n for n in s[collection]} for s in (original, edited))
        changed = {
            i for i in old.keys() | new.keys() if old.get(i) != new.get(i)
        } | primary[collection]
        scope[collection] = {
            i: None
            if i in primary[collection] or i not in old or i not in new
            else {
                k for k in old[i].keys() | new[i].keys() if old[i].get(k) != new[i].get(k)
            }
            for i in changed
        }
    scope["display_names"] = {
        key: None
        for key in original["extension_v4"]["display_names"].keys()
        | edited["extension_v4"]["display_names"].keys()
        if original["extension_v4"]["display_names"].get(key)
        != edited["extension_v4"]["display_names"].get(key)
    }
    return scope


def copy_scope(destination, source, scope):
    result = deepcopy(destination)
    for collection, entries in scope.items():
        if collection == "display_names":
            for key in entries:
                value = source["extension_v4"]["display_names"].get(key)
                if value is None:
                    result["extension_v4"]["display_names"].pop(key, None)
                else:
                    result["extension_v4"]["display_names"][key] = value
            continue
        incoming = {n["id"]: n for n in source[collection]}
        existing = {n["id"]: n for n in result[collection]}
        for key, fields in entries.items():
            if key not in incoming:
                existing.pop(key, None)
            elif fields is None or key not in existing:
                existing[key] = deepcopy(incoming[key])
            else:
                for field in fields:
                    existing[key][field] = deepcopy(incoming[key][field])
        result[collection] = list(existing.values())
    # Retired v2 IDs remain audit data only while their native mapping exists.
    cm_ids = {c["id"] for c in result["concept_mappings"]}
    result["extension_v4"]["legacy_mapping_ids"] = {
        k: v for k, v in result["extension_v4"]["legacy_mapping_ids"].items() if v in cm_ids
    }
    return result
