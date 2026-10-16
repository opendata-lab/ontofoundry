"""Strict core-1 proposal contract and pure, whole-batch parsing."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid5

from jsonschema import Draft202012Validator
from pydantic import TypeAdapter

from ontofoundry_api.domain.canonical import canonical, domain_sha256, element_sha256
from ontofoundry_api.domain.core import CoreDraft, MaterialEvidence
from ontofoundry_api.domain.dependencies import reference_index, validate_candidate_graph
from ontofoundry_api.domain.evidence import (
    EvidenceError,
    MaterialLookup,
    check_material_evidence,
)
from ontofoundry_api.domain.models import (
    COLLECTIONS,
    ELEMENT_MODELS,
    ElementKind,
    OntologyDraft,
)

SCHEMA_VERSION = "ontofoundry.proposals/v1"
MAX_ITEMS = 500
CLIENT_REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
_UUID = {"type": "string", "format": "uuid"}
_CLIENT_REF = {
    "type": "object",
    "properties": {"client_ref": {"type": "string", "pattern": CLIENT_REF_PATTERN}},
    "required": ["client_ref"],
    "additionalProperties": False,
}
_REF = {"anyOf": [_UUID, _CLIENT_REF]}


class ProposalContractError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _after_schema(kind):
    schema = TypeAdapter(ELEMENT_MODELS[kind]).json_schema(ref_template="#/$defs/{model}")
    defs = schema.pop("$defs", {})

    def transform(node):
        if not isinstance(node, dict):
            return
        for key, value in list(node.items()):
            if key == "properties":
                value.pop("id", None)
                for name, definition in list(value.items()):
                    if name == "inherited_link_bindings":
                        value[name] = {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "link_type_id": _REF,
                                    "data_join": definition["additionalProperties"],
                                },
                                "required": ["link_type_id", "data_join"],
                                "additionalProperties": False,
                            },
                        }
                    elif name != "evidence":
                        references(definition)
            elif key == "required":
                node[key] = [x for x in value if x != "id"]
            elif isinstance(value, dict):
                transform(value)
            elif isinstance(value, list):
                for v in value:
                    transform(v)

    def references(node):
        if isinstance(node, dict):
            if node.get("format") == "uuid":
                node.clear()
                node.update(deepcopy(_REF))
            else:
                for v in node.values():
                    references(v)
        elif isinstance(node, list):
            for v in node:
                references(v)

    transform(schema)
    for name, definition in defs.items():
        if name not in ("ManualEvidence", "MaterialEvidence", "EvidenceLocator"):
            transform(definition)
    # Evidence IDs may be assigned by the receiver; authorship is checked separately.
    if "MaterialEvidence" in defs:
        defs["MaterialEvidence"]["required"].remove("id")
    renamed = json.loads(
        json.dumps({"schema": schema, "defs": defs}).replace("#/$defs/", "#/$defs/After")
    )
    return {
        "schema": renamed["schema"],
        "defs": {"After" + k: v for k, v in renamed["defs"].items()},
    }


def result_schema():
    defs, variants = {}, []
    for kind in ElementKind:
        after = _after_schema(kind)
        defs.update(after["defs"])
        full = TypeAdapter(ELEMENT_MODELS[kind]).json_schema(ref_template="#/$defs/{model}")
        defs.update(full.pop("$defs", {}))
        defs[f"{kind.value}_after"] = after["schema"]
        defs[f"{kind.value}_element"] = full
        variants.append(
            {
                "properties": {
                    "target_kind": {"const": kind.value},
                    "after": {
                        "anyOf": [{"$ref": f"#/$defs/{kind.value}_after"}, {"type": "null"}]
                    },
                    "before": {
                        "anyOf": [
                            {"$ref": f"#/$defs/{kind.value}_element"},
                            {"type": "null"},
                        ]
                    },
                }
            }
        )
    item = {
        "type": "object",
        "properties": {
            "client_ref": {"type": "string", "pattern": CLIENT_REF_PATTERN},
            "operation": {"enum": ["create", "update", "delete"]},
            "target_kind": {"enum": [k.value for k in ElementKind]},
            "target_id": {"anyOf": [_UUID, {"type": "null"}]},
            "expected_target_hash": {
                "anyOf": [{"type": "string", "pattern": "^[0-9a-f]{64}$"}, {"type": "null"}]
            },
            "before": {},
            "after": {},
            "field_changes": {
                "type": "array",
                "maxItems": 200,
                "items": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "before": {}, "after": {}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
            "evidence": {
                "type": "array",
                "maxItems": 50,
                "items": {"$ref": "#/$defs/MaterialEvidence"},
            },
            "depends_on": {
                "type": "array",
                "maxItems": 50,
                "items": {"type": "string", "pattern": CLIENT_REF_PATTERN},
            },
            "reason": {"type": "string", "maxLength": 2000},
        },
        "required": ["operation", "target_kind", "before", "after"],
        "additionalProperties": False,
        "oneOf": variants,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://ontofoundry.local/schemas/ontofoundry.proposals.v1.json",
        "title": SCHEMA_VERSION,
        "type": "object",
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "run_token": {"type": "string", "minLength": 1, "maxLength": 128},
            "workspace_id": _UUID,
            "session_id": _UUID,
            "base_version_id": {"anyOf": [_UUID, {"type": "null"}]},
            "base_version_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "source_session_revision": {"type": "integer", "minimum": 0},
            "source_draft_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "items": {
                "type": "array",
                "maxItems": MAX_ITEMS,
                "items": {"$ref": "#/$defs/item"},
            },
        },
        "required": [
            "schema_version",
            "run_token",
            "workspace_id",
            "session_id",
            "base_version_id",
            "base_version_sha256",
            "source_session_revision",
            "source_draft_sha256",
            "items",
        ],
        "additionalProperties": False,
        "$defs": {**defs, "item": item},
    }


@dataclass(frozen=True)
class RunContext:
    """What the run was pinned to when it started (design §6.2)."""

    workspace_id: str
    session_id: str
    run_token: str
    base_version_id: str | None
    base_version_sha256: str
    source_session_revision: int
    source_draft_sha256: str
    draft: dict[str, Any]  # the pinned session draft


@dataclass
class ParsedItem:
    id: str
    ordinal: int
    client_ref: str | None
    operation: str
    target_kind: str
    target_id: str
    expected_target_hash: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    field_changes: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    reason: str
    fingerprint: str
    depends_on: list[str] = field(default_factory=list)
    atomic_group_id: str | None = None


@dataclass
class ParsedBatch:
    id: str
    result_sha256: str
    items: list[ParsedItem]


def batch_id_for(session_id: str, run_token: str) -> str:
    return str(uuid5(UUID(session_id), f"proposal-batch:{run_token}"))


def create_target_id(batch_id: str, client_ref: str) -> str:
    return str(uuid5(UUID(batch_id), f"create:{client_ref}"))


def item_fingerprint(operation, target_kind, target_id, after):
    return domain_sha256(
        {
            "operation": operation,
            "target_kind": target_kind,
            "target_id": target_id,
            "after": after,
        }
    )


REF_FIELDS = {
    "extends",
    "title_property_id",
    "owner_type_id",
    "source_type_id",
    "target_type_id",
    "owner_id",
    "dataset_id",
    "numerator_id",
    "denominator_id",
    "property_id",
    "link_type_id",
    "type_id",
    "source_id",
    "target_id",
}
REF_ARRAYS = {"source_property_ids", "target_property_ids", "property_ids"}


def walk_references(value, resolve):
    """Only typed reference positions; local source IDs and fact values stay intact."""
    if isinstance(value, list):
        return [walk_references(v, resolve) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, entry in value.items():
        if key == "inherited_link_bindings":
            if isinstance(entry, list):
                result[key] = {
                    resolve(e["link_type_id"]): walk_references(e["data_join"], resolve)
                    for e in entry
                }
            else:
                result[key] = {
                    resolve(k): walk_references(v, resolve) for k, v in entry.items()
                }
        elif key in REF_ARRAYS:
            result[key] = [resolve(v) for v in entry]
        elif key in REF_FIELDS and entry is not None:
            # ColumnBinding.source_id names a local source, not an element.
            result[key] = (
                entry
                if key == "source_id" and value.get("kind") == "column"
                else resolve(entry)
            )
        elif key in {"values", "evidence", "columns"}:
            result[key] = deepcopy(entry)
        else:
            result[key] = walk_references(entry, resolve)
    return result


def apply_items(draft, items):
    candidate = deepcopy(draft)
    for item in items:
        collection = COLLECTIONS[ElementKind(item.target_kind)]
        candidate[collection] = [
            e for e in candidate[collection] if e["id"] != item.target_id
        ]
        if item.after is not None:
            candidate[collection].append(deepcopy(item.after))
    return candidate


def group_items(draft, items):
    """Group cyclic references and edits requiring simultaneous final-graph validation."""
    before = CoreDraft.model_validate(draft)
    candidate = validate_candidate_graph(
        before, CoreDraft.model_validate(apply_items(draft, items))
    )
    final = {
        str(e.id): e.model_dump(mode="json")
        for c in COLLECTIONS.values()
        for e in getattr(candidate, c)
    }
    by_target = {i.target_id: i for i in items}
    previous_evidence = {
        str(e.id): str(item.id)
        for c in COLLECTIONS.values()
        for item in getattr(before, c)
        for e in getattr(item, "evidence", [])
    }
    for c in COLLECTIONS.values():
        for element in getattr(candidate, c):
            for evidence in getattr(element, "evidence", []):
                if str(evidence.id) in previous_evidence and previous_evidence[
                    str(evidence.id)
                ] != str(element.id):
                    raise ValueError("证据 UUID 不能转移归属")
    refs = reference_index(candidate)
    deps = {i.id: set(i.depends_on) for i in items}
    for item in items:
        if item.after is not None:
            item.after = final[item.target_id]
            item.fingerprint = item_fingerprint(
                item.operation, item.target_kind, item.target_id, item.after
            )
        for ref in refs.get(UUID(item.target_id), ()):
            dependency = by_target.get(str(ref.target_id))
            if dependency and dependency.id != item.id:
                deps[item.id].add(dependency.id)
    original = {e["id"]: e for c in COLLECTIONS.values() for e in draft[c]}
    # Renames and deletions must include the changed reverse references. A
    # partial accept must never leave an old textual name dangling.
    old_refs = reference_index(before)
    for owner, references in old_refs.items():
        for reference in references:
            changed = by_target.get(str(reference.target_id))
            if changed is None:
                continue
            previous = original.get(changed.target_id, {})
            renamed = changed.after is not None and any(
                previous.get(k) != changed.after.get(k)
                for k in ("technical_name", "name")
                if k in previous
            )
            if changed.operation == "delete" or renamed:
                dependent = by_target.get(str(owner))
                if dependent and dependent.id != changed.id:
                    deps[changed.id].add(dependent.id)
    untouched = set(original) - set(by_target)
    if any(final.get(i) != original[i] for i in untouched if i in final):
        raise ValueError("引用改写涉及批次外元素，请显式补齐受影响提案")
    parent = {i.id: i.id for i in items}

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a, b):
        parent[root(a)] = root(b)

    # A name exchange has no reference edge; detect collisions in its actual
    # core namespace, instead of grouping unrelated incomplete create items.
    def namespace(item, element):
        kind = item.target_kind
        owner = element.get(
            "owner_type_id", element.get("source_type_id", element.get("owner_id"))
        )
        return (kind, owner)

    for item in items:
        if item.after is None:
            continue
        for other in items:
            previous = original.get(other.target_id)
            if (
                item.id == other.id
                or previous is None
                or namespace(item, item.after) != namespace(other, previous)
            ):
                continue
            fields = (
                ("name",) if item.target_kind == "dataset" else ("name", "technical_name")
            )
            if any(
                str(item.after.get(k, "")).casefold() == str(previous.get(k, "")).casefold()
                for k in fields
            ):
                union(item.id, other.id)
    # Tarjan SCCs compress true dependency cycles into atomic decisions.
    next_index = 0
    indices, low, stack, active = {}, {}, [], set()

    def visit(node):
        nonlocal next_index
        indices[node] = low[node] = next_index
        next_index += 1
        stack.append(node)
        active.add(node)
        for dep in deps[node]:
            if dep not in indices:
                visit(dep)
                low[node] = min(low[node], low[dep])
            elif dep in active:
                low[node] = min(low[node], indices[dep])
        if low[node] == indices[node]:
            members = []
            while True:
                member = stack.pop()
                active.remove(member)
                members.append(member)
                if member == node:
                    break
            for member in members[1:]:
                union(members[0], member)

    for node in deps:
        if node not in indices:
            visit(node)
    groups = {}
    for item in items:
        groups.setdefault(root(item.id), []).append(item)
    for members in groups.values():
        group_id = (
            str(uuid5(UUID(members[0].id), "atomic-group")) if len(members) > 1 else None
        )
        for item in members:
            item.atomic_group_id = group_id
            item.depends_on = sorted(d for d in deps[item.id] if root(d) != root(item.id))
    return candidate


def parse_result(
    raw: bytes, context: RunContext, material_lookup: MaterialLookup
) -> ParsedBatch:
    def fail(code, message):
        raise ProposalContractError(code, message)

    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ProposalContractError("RESULT_JSON_INVALID", "建模结果不是合法 JSON") from exc
    errors = list(Draft202012Validator(result_schema()).iter_errors(data))
    if errors:
        fail("RESULT_SCHEMA_INVALID", f"建模结果不符合契约：{errors[0].message}")
    for name in (
        "workspace_id",
        "session_id",
        "run_token",
        "base_version_id",
        "base_version_sha256",
        "source_session_revision",
        "source_draft_sha256",
    ):
        if data[name] != getattr(context, name):
            fail("RESULT_CONTEXT_MISMATCH", f"建模结果的 {name} 与固定上下文不一致")
    existing = {e["id"]: (k, e) for k, c in COLLECTIONS.items() for e in context.draft[c]}
    batch_id = batch_id_for(context.session_id, context.run_token)
    refs, targets = {}, {}
    for n, item in enumerate(data["items"]):
        ref = item.get("client_ref")
        if ref:
            if ref in refs:
                fail("CLIENT_REF_DUPLICATE", f"client_ref {ref} 重复")
            refs[ref] = n
        if item["operation"] == "create":
            if (
                not ref
                or item.get("target_id") is not None
                or item["before"] is not None
                or item["after"] is None
            ):
                fail("OPERATION_SHAPE", "新增必须有 client_ref 和 after，且无目标和 before")
            targets[n] = create_target_id(batch_id, ref)
        else:
            target = item.get("target_id")
            if target not in existing:
                fail("TARGET_NOT_FOUND", "更新或删除的目标不在固定草稿中")
            kind, current = existing[target]
            if kind.value != item["target_kind"]:
                fail("TARGET_KIND_MISMATCH", "目标类型不符")
            if item["before"] is None or (item["operation"] == "update") != (
                item["after"] is not None
            ):
                fail("OPERATION_SHAPE", "更新或删除的 before/after 形态不正确")
            if canonical(item["before"]) != canonical(current):
                fail("BEFORE_MISMATCH", "before 与固定草稿不一致")
            if element_sha256(current, collection=COLLECTIONS[kind]) != item.get(
                "expected_target_hash"
            ):
                fail("TARGET_HASH_MISMATCH", "目标哈希不一致")
            targets[n] = target
    if len(set(targets.values())) != len(targets):
        fail("TARGET_DUPLICATE", "同一批次不能重复作用于同一目标")
    ids = [str(uuid5(UUID(batch_id), f"item:{n}")) for n in targets]
    all_ids = set(existing) | set(targets.values())
    parsed = []
    for n, raw_item in enumerate(data["items"]):
        deps = set()

        def resolve(value, n=n, deps=deps):
            if isinstance(value, dict):
                ref = value["client_ref"]
                if ref not in refs or data["items"][refs[ref]]["operation"] != "create":
                    fail("CLIENT_REF_UNKNOWN", f"未知新增引用 {ref}")
                target_index = refs[ref]
                if target_index != n:
                    deps.add(ids[target_index])
                return targets[target_index]
            if str(value) not in all_ids:
                fail("REFERENCE_UNKNOWN", f"未知引用 {value}")
            return str(value)

        for ref in raw_item.get("depends_on", []):
            if ref not in refs:
                fail("DEPENDENCY_UNKNOWN", f"未知依赖 {ref}")
            deps.add(ids[refs[ref]])
        after = raw_item["after"]
        if after is not None:
            after = walk_references(after, resolve)
            after["id"] = targets[n]
        try:
            if after is not None:
                for evidence in after.get("evidence", []):
                    if evidence["kind"] == "material":
                        evidence.setdefault(
                            "id", str(uuid5(UUID(targets[n]), canonical(evidence)))
                        )
                        check_material_evidence(evidence, material_lookup, "evidence")
                after = (
                    TypeAdapter(ELEMENT_MODELS[ElementKind(raw_item["target_kind"])])
                    .validate_python(after)
                    .model_dump(mode="json")
                )

                def manual(e):
                    return sorted(
                        (v for v in (e or {}).get("evidence", []) if v["kind"] == "manual"),
                        key=lambda e: e["id"],
                    )

                if manual(after) != manual(raw_item["before"]):
                    fail("MANUAL_EVIDENCE_FORBIDDEN", "智能体不能新增、修改或删除人工证据")
            evidence = deepcopy(raw_item.get("evidence", []))
            for e in evidence:
                e.setdefault("id", str(uuid5(UUID(targets[n]), canonical(e))))
                MaterialEvidence.model_validate(e)
                check_material_evidence(e, material_lookup, "evidence")
        except (ValueError, EvidenceError) as exc:
            if isinstance(exc, ProposalContractError):
                raise
            raise ProposalContractError("ELEMENT_INVALID", str(exc)) from exc
        parsed.append(
            ParsedItem(
                ids[n],
                n,
                raw_item.get("client_ref"),
                raw_item["operation"],
                raw_item["target_kind"],
                targets[n],
                raw_item.get("expected_target_hash"),
                raw_item["before"],
                after,
                raw_item.get("field_changes", []),
                evidence,
                raw_item.get("reason", ""),
                item_fingerprint(
                    raw_item["operation"], raw_item["target_kind"], targets[n], after
                ),
                sorted(deps),
            )
        )
    try:
        group_items(context.draft, parsed)
    except ValueError as exc:
        raise ProposalContractError("ELEMENT_INVALID", str(exc)) from exc
    return ParsedBatch(batch_id, hashlib.sha256(raw).hexdigest(), parsed)


def validate_draft_model(draft):
    return OntologyDraft.model_validate(draft)
