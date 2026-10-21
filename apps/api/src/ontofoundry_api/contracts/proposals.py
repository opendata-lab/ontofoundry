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

from ontofoundry_api.contracts.proposal_diagnostics import diagnostic, schema_diagnostic
from ontofoundry_api.domain.canonical import canonical, domain_sha256, element_sha256
from ontofoundry_api.domain.core import CoreDraft, MaterialEvidence
from ontofoundry_api.domain.dependencies import (
    reference_index,
    strict_equal,
    validate_candidate_graph,
)
from ontofoundry_api.domain.evidence import (
    EvidenceError,
    MaterialLookup,
    check_material_evidence,
)
from ontofoundry_api.domain.instances import (
    INSTANCE_KINDS,
    baseline_elements,
    combined_snapshot,
    definitions,
    instance_hash,
    instance_references,
    validate_instances,
)
from ontofoundry_api.domain.models import (
    COLLECTIONS,
    ELEMENT_MODELS,
    PROPOSAL_COLLECTIONS,
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

    def transform(node, *, preserve_id=False):
        if not isinstance(node, dict):
            return
        for key, value in list(node.items()):
            if key == "properties":
                if not preserve_id:
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
            elif key == "required" and not preserve_id:
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
            # MappingSource.id is a caller-defined local source name, not a
            # server-assigned core element UUID.
            transform(definition, preserve_id=name == "MappingSource")
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
    instance_baseline: dict[str, Any] = field(default_factory=dict)


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
    expected_instance_revision: int | None = None


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


def walk_references(kind, value, resolve):
    """Resolve only core references at paths defined by the element's type."""
    result = deepcopy(value)

    def refs(node, *names):
        for name in names:
            if node.get(name) is not None:
                node[name] = resolve(node[name])

    def path(node):
        refs(node, "property_id")
        for step in node.get("links", []):
            refs(step, "link_type_id")

    def join(node):
        if node is None:
            return
        if node["kind"] == "direct":
            for name in ("source_property_ids", "target_property_ids"):
                node[name] = [resolve(v) for v in node[name]]
        else:
            refs(node, "dataset_id")
            for side in ("source_key", "target_key"):
                if node[side]["kind"] == "properties":
                    node[side]["property_ids"] = [
                        resolve(v) for v in node[side]["property_ids"]
                    ]

    if kind == "object_type":
        refs(result, "extends", "title_property_id")
        for branch in result.get("derived_by", []):
            for condition in branch.get("conditions", []):
                path(condition["path"])
    elif kind == "property":
        refs(result, "owner_type_id", "value_type_id")
    elif kind == "link_type":
        refs(result, "source_type_id", "target_type_id")
        join(result.get("data_join"))
    elif kind == "rule":
        refs(result, "owner_id")
    elif kind == "metric":
        refs(result, "dataset_id", "numerator_id", "denominator_id")
        for name in ("measure", "time_field"):
            if result.get(name) is not None:
                refs(result[name], "dataset_id")
        for condition in result.get("filters", []):
            refs(condition["column"], "dataset_id")
    elif kind == "mapping":
        refs(result, "type_id")
        for source in result.get("sources", []):
            refs(source, "dataset_id")
        # Field keys are property technical names; binding values contain only
        # local source names or expressions, never core element references.
        inherited = result.get("inherited_link_bindings", [])
        entries = (
            ((e["link_type_id"], e["data_join"]) for e in inherited)
            if isinstance(inherited, list)
            else inherited.items()
        )
        result["inherited_link_bindings"] = {}
        for identity, binding in entries:
            join(binding)
            result["inherited_link_bindings"][resolve(identity)] = binding
    elif kind == "material_object":
        refs(result, "type_id")
    elif kind == "material_link":
        refs(result, "type_id", "source_id", "target_id")
    return result


def apply_items(draft, items):
    candidate = deepcopy(draft)
    for item in items:
        collection = PROPOSAL_COLLECTIONS[ElementKind(item.target_kind)]
        candidate[collection] = [
            e for e in candidate.get(collection, []) if e["id"] != item.target_id
        ]
        if item.after is not None:
            candidate[collection].append(deepcopy(item.after))
    return candidate


def group_items(draft, items, *, references_resolved=False):
    """Group cyclic references and edits requiring simultaneous final-graph validation."""
    before = CoreDraft.model_validate(definitions(draft))
    candidate = (
        OntologyDraft.model_validate(definitions(apply_items(draft, items)))
        if references_resolved
        else validate_candidate_graph(
            before, CoreDraft.model_validate(definitions(apply_items(draft, items)))
        )
    )
    instance_candidate = apply_items(draft, [i for i in items if i.target_kind in INSTANCE_KINDS])
    objects = instance_candidate.get("material_objects", [])
    links = instance_candidate.get("material_links", [])
    object_lookup = {o["id"]: o for o in objects}
    changed_links = [i.after for i in items if i.target_kind == "material_link" and i.after is not None]
    relevant_ids = {i.target_id for i in items if i.target_kind == "material_object" and i.after is not None}
    relevant_ids.update(e for link in changed_links for e in (link["source_id"], link["target_id"]))
    validate_instances(candidate, [object_lookup[i] for i in relevant_ids if i in object_lookup], changed_links)
    final = {
        str(e.id): e.model_dump(mode="json")
        for c in COLLECTIONS.values()
        for e in getattr(candidate, c)
    }
    final.update({e["id"]: e for e in [*objects, *links]})
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
    refs = {**reference_index(candidate), **instance_references(candidate, objects, links)}
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
    original = {e["id"]: e for c in PROPOSAL_COLLECTIONS.values() for e in draft.get(c, [])}
    # Renames and deletions must include the changed reverse references. A
    # partial accept must never leave an old textual name dangling.
    old_refs = {**reference_index(before), **instance_references(before, draft.get("material_objects", []), draft.get("material_links", []))}
    for owner, references in old_refs.items():
        for reference in references:
            changed = by_target.get(str(reference.target_id))
            if changed is None:
                continue
            previous = original.get(changed.target_id, {})
            renamed = changed.after is not None and any(
                previous.get(k) != changed.after.get(k) for k in ("name",) if k in previous
            )
            if changed.operation == "delete" or renamed:
                dependent = by_target.get(str(owner))
                if dependent and dependent.id != changed.id:
                    deps[changed.id].add(dependent.id)
    untouched = set(original) - set(by_target)
    if any(not strict_equal(final.get(i), original[i]) for i in untouched if i in final):
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
        if kind in {"property", "link_type"}:
            return ("property_link", owner)
        if kind == "rule":
            return (kind, element["owner_kind"], owner)
        return (kind, owner)

    for item in items:
        if item.after is None or item.target_kind not in {
            "object_type",
            "property",
            "link_type",
            "rule",
            "metric",
            "dataset",
        }:
            continue
        for other in items:
            previous = original.get(other.target_id)
            if (
                item.id == other.id
                or previous is None
                or namespace(item, item.after) != namespace(other, previous)
            ):
                continue
            fields = ("name",)
            names = item.after
            old_names = previous
            if any(
                k in names
                and k in old_names
                and str(names[k]).casefold() == str(old_names[k]).casefold()
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
    current_item = None
    current_pointer = "/"

    def fail(
        code, message, *, pointer=None, expected="符合固定上下文及当前提案契约", actual=None
    ):
        raise ProposalContractError(
            code,
            diagnostic(
                pointer or current_pointer,
                message,
                expected,
                actual if actual is not None else message,
                current_item,
            ),
        )

    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ProposalContractError(
            "RESULT_JSON_INVALID",
            diagnostic("/", "建模结果不是合法 JSON", "UTF-8 JSON 对象", type(exc).__name__),
        ) from exc
    errors = list(Draft202012Validator(result_schema()).iter_errors(data))
    if errors:
        raise ProposalContractError(
            "RESULT_SCHEMA_INVALID", schema_diagnostic(errors[0], result_schema(), data)
        )
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
            fail(
                "RESULT_CONTEXT_MISMATCH",
                f"建模结果的 {name} 与固定上下文不一致",
                pointer="/" + name,
                expected=getattr(context, name),
                actual=data[name],
            )
    existing = {e["id"]: (k, e) for k, c in COLLECTIONS.items() for e in context.draft.get(c, [])}
    existing.update({identity: (ElementKind(kind), element)
        for identity, (kind, element) in baseline_elements(context.instance_baseline).items()})
    instance_entries = {i["target_id"]: i for i in context.instance_baseline.get("items", [])}
    batch_id = batch_id_for(context.session_id, context.run_token)
    refs, targets = {}, {}
    for n, item in enumerate(data["items"]):
        current_item, current_pointer = item, f"/items/{n}"
        ref = item.get("client_ref")
        if ref:
            if ref in refs:
                fail(
                    "CLIENT_REF_DUPLICATE",
                    f"client_ref {ref} 重复",
                    pointer=current_pointer + "/client_ref",
                    expected="不重复的 client_ref",
                    actual=ref,
                )
            refs[ref] = n
        if item["operation"] == "create":
            if (
                not ref
                or item.get("target_id") is not None
                or item["before"] is not None
                or item["after"] is None
            ):
                fail(
                    "OPERATION_SHAPE",
                    "新增必须有 client_ref 和 after，且无目标和 before",
                    expected={
                        "client_ref": "非空",
                        "before": None,
                        "target_id": None,
                        "after": "对象",
                    },
                    actual={
                        k: item.get(k)
                        for k in ("client_ref", "target_id", "before", "after")
                    },
                )
            targets[n] = create_target_id(batch_id, ref)
        else:
            target = item.get("target_id")
            if target not in existing:
                fail(
                    "TARGET_NOT_FOUND",
                    "更新或删除的目标不在固定草稿中",
                    pointer=current_pointer + "/target_id",
                    expected="固定草稿中已有的 UUID",
                    actual=target,
                )
            kind, current = existing[target]
            if kind.value != item["target_kind"]:
                fail(
                    "TARGET_KIND_MISMATCH",
                    "目标类型不符",
                    pointer=current_pointer + "/target_kind",
                    expected=kind.value,
                    actual=item["target_kind"],
                )
            if item["before"] is None or (item["operation"] == "update") != (
                item["after"] is not None
            ):
                fail(
                    "OPERATION_SHAPE",
                    "更新或删除的 before/after 形态不正确",
                    expected={
                        "before": "完整旧对象",
                        "after": "对象" if item["operation"] == "update" else None,
                    },
                    actual={"before": item["before"], "after": item["after"]},
                )
            if canonical(item["before"]) != canonical(current):
                fail(
                    "BEFORE_MISMATCH",
                    "before 与固定草稿不一致",
                    pointer=current_pointer + "/before",
                    expected=current,
                    actual=item["before"],
                )
            expected_hash = (instance_hash(current, instance_entries[target]["revision"])
                if kind.value in INSTANCE_KINDS else element_sha256(current, collection=COLLECTIONS[kind]))
            if expected_hash != item.get(
                "expected_target_hash"
            ):
                fail(
                    "TARGET_HASH_MISMATCH",
                    "目标哈希不一致",
                    pointer=current_pointer + "/expected_target_hash",
                    expected=expected_hash,
                    actual=item.get("expected_target_hash"),
                )
            targets[n] = target
    if len(set(targets.values())) != len(targets):
        fail(
            "TARGET_DUPLICATE",
            "同一批次不能重复作用于同一目标",
            pointer="/items",
            expected="所有目标 UUID 不重复",
            actual=list(targets.values()),
        )
    ids = [str(uuid5(UUID(batch_id), f"item:{n}")) for n in targets]
    all_ids = set(existing) | set(targets.values())
    parsed = []
    for n, raw_item in enumerate(data["items"]):
        current_item, current_pointer = raw_item, f"/items/{n}"
        deps = set()

        def resolve(value, n=n, deps=deps):
            if isinstance(value, dict):
                ref = value["client_ref"]
                if ref not in refs or data["items"][refs[ref]]["operation"] != "create":
                    fail(
                        "CLIENT_REF_UNKNOWN",
                        f"未知新增引用 {ref}",
                        expected={
                            "可用新增引用": [
                                k
                                for k, v in refs.items()
                                if data["items"][v]["operation"] == "create"
                            ]
                        },
                        actual=ref,
                    )
                target_index = refs[ref]
                if target_index != n:
                    deps.add(ids[target_index])
                return targets[target_index]
            if str(value) not in all_ids:
                fail(
                    "REFERENCE_UNKNOWN",
                    f"未知引用 {value}",
                    expected="固定草稿或本批新增的 UUID",
                    actual=value,
                )
            return str(value)

        for ref in raw_item.get("depends_on", []):
            if ref not in refs:
                fail(
                    "DEPENDENCY_UNKNOWN",
                    f"未知依赖 {ref}",
                    pointer=current_pointer + "/depends_on",
                    expected=list(refs),
                    actual=ref,
                )
            deps.add(ids[refs[ref]])
        after = raw_item["after"]
        if after is not None:
            after = walk_references(raw_item["target_kind"], after, resolve)
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
                    fail(
                        "MANUAL_EVIDENCE_FORBIDDEN",
                        "智能体不能新增、修改或删除人工证据",
                        pointer=current_pointer + "/after/evidence",
                        expected=manual(raw_item["before"]),
                        actual=manual(after),
                    )
            evidence = deepcopy(raw_item.get("evidence", []))
            for e in evidence:
                e.setdefault("id", str(uuid5(UUID(targets[n]), canonical(e))))
                MaterialEvidence.model_validate(e)
                check_material_evidence(e, material_lookup, "evidence")
        except (ValueError, EvidenceError) as exc:
            if isinstance(exc, ProposalContractError):
                raise
            raise ProposalContractError(
                "ELEMENT_INVALID",
                diagnostic(
                    current_pointer + "/after",
                    str(exc),
                    "有效元素与真实材料证据",
                    str(exc),
                    raw_item,
                ),
            ) from exc
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
        for item in parsed:
            if item.target_kind in INSTANCE_KINDS and item.operation != "create":
                item.expected_instance_revision = instance_entries[item.target_id]["revision"]
        group_items(combined_snapshot(context.draft, context.instance_baseline), parsed)
    except ValueError as exc:
        raise ProposalContractError(
            "ELEMENT_INVALID",
            diagnostic("/items", "候选图校验未通过", "完整合法的候选图", str(exc)),
        ) from exc
    return ParsedBatch(batch_id, hashlib.sha256(raw).hexdigest(), parsed)


def validate_draft_model(draft):
    return OntologyDraft.model_validate(draft)
