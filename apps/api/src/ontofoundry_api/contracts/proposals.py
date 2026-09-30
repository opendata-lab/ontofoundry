"""`ontofoundry.proposals/v1`: what a modeling run returns, and how it is read.

The JSON Schema is generated from the v2 element models so the two can never
drift: a proposal's `after` is an element without `id`, where every field that
references another element accepts either a UUID of an element in the pinned
draft or `{"client_ref": "..."}` naming a create item in the same batch.

`parse_result` turns a raw result into rows ready to store, or raises
`ProposalContractError` for the whole result — nothing is ever half-accepted.
It is pure: the caller supplies the pinned draft and a material lookup.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid5

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ontofoundry_api.domain.canonical import canonical, domain_sha256, element_sha256
from ontofoundry_api.domain.evidence import (
    EvidenceError,
    MaterialLookup,
    check_material_evidence,
)
from ontofoundry_api.domain.models import (
    COLLECTIONS,
    ActionDefinition,
    DataMapping,
    ElementKind,
    LinkTypeDefinition,
    MaterialEvidence,
    MaterialLink,
    MaterialObject,
    ObjectTypeDefinition,
    OntologyDraft,
    PropertyDefinition,
    RuleDefinition,
)

SCHEMA_VERSION = "ontofoundry.proposals/v1"
MAX_ITEMS = 500
CLIENT_REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"

MODELS: dict[ElementKind, type] = {
    ElementKind.OBJECT_TYPE: ObjectTypeDefinition,
    ElementKind.PROPERTY: PropertyDefinition,
    ElementKind.LINK_TYPE: LinkTypeDefinition,
    ElementKind.RULE: RuleDefinition,
    ElementKind.ACTION: ActionDefinition,
    ElementKind.MATERIAL_OBJECT: MaterialObject,
    ElementKind.MATERIAL_LINK: MaterialLink,
    ElementKind.MAPPING: DataMapping,
}

# Fields holding another element's id, per kind. "[]" marks a list of ids;
# "effects[]." reaches into action effects.
REFERENCE_FIELDS: dict[ElementKind, tuple[str, ...]] = {
    ElementKind.OBJECT_TYPE: ("extends[]",),
    ElementKind.PROPERTY: ("owner_type_id",),
    ElementKind.LINK_TYPE: ("source_type_id", "target_type_id"),
    ElementKind.RULE: ("owner_id",),
    ElementKind.ACTION: (
        "input_type_id",
        "precondition_rule_ids[]",
        "effects[].property_id",
        "effects[].link_type_id",
    ),
    ElementKind.MATERIAL_OBJECT: ("type_id",),
    ElementKind.MATERIAL_LINK: ("type_id", "source_id", "target_id"),
    ElementKind.MAPPING: ("type_id",),
}


class ProposalContractError(ValueError):
    """The whole result is rejected; `code` is stable for the caller."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --- schema -------------------------------------------------------------------

_CLIENT_REF = {
    "type": "object",
    "properties": {"client_ref": {"type": "string", "pattern": CLIENT_REF_PATTERN}},
    "required": ["client_ref"],
    "additionalProperties": False,
}
_UUID = {"type": "string", "format": "uuid"}
_REF = {"anyOf": [_UUID, _CLIENT_REF]}


def _after_schema(kind: ElementKind) -> dict[str, Any]:
    schema = MODELS[kind].model_json_schema(ref_template="#/$defs/{model}")
    defs = schema.pop("$defs", {})
    # The server assigns ids: the element's own, and those of its sub-items.
    schema["properties"].pop("id", None)
    schema["required"] = [name for name in schema.get("required", []) if name != "id"]
    for name in ("ActionParameter", "ActionEffect", "MaterialEvidence"):
        if name in defs:
            defs[name]["required"] = [r for r in defs[name].get("required", []) if r != "id"]
    # Agents author material evidence only. Manual entries may appear solely as
    # an unchanged echo of `before` (checked in parse_result).
    if "evidence" in schema["properties"]:
        schema["properties"]["evidence"] = {
            "type": "array",
            "maxItems": 50,
            "items": {
                "anyOf": [{"$ref": "#/$defs/MaterialEvidence"}, {"$ref": "#/$defs/ManualEvidence"}]
            },
        }
    for path in REFERENCE_FIELDS[kind]:
        if path.startswith("effects[]."):
            defs["ActionEffect"]["properties"][path.split(".", 1)[1]] = {"anyOf": [_REF, {"type": "null"}]}
        elif path.endswith("[]"):
            schema["properties"][path[:-2]] = {"type": "array", "items": _REF}
        else:
            schema["properties"][path] = _REF
    schema["additionalProperties"] = False
    # Sub-schemas of `after` differ from the stored element's (ids optional), so
    # they live under their own names and never clash with the element defs.
    text = json.dumps({"schema": schema, "defs": defs})
    for name in defs:
        text = text.replace(f'"#/$defs/{name}"', f'"#/$defs/After{name}"')
    renamed = json.loads(text)
    return {
        "schema": renamed["schema"],
        "defs": {f"After{name}": value for name, value in renamed["defs"].items()},
    }


def result_schema() -> dict[str, Any]:
    """The Draft 2020-12 JSON Schema of `ontofoundry.proposals/v1`."""
    defs: dict[str, Any] = {}
    variants = []
    for kind in ElementKind:
        after = _after_schema(kind)
        defs.update(after["defs"])
        full = MODELS[kind].model_json_schema(ref_template="#/$defs/{model}")
        defs.update(full.pop("$defs", {}))
        defs[f"{kind.value}_after"] = after["schema"]
        defs[f"{kind.value}_element"] = full
        variants.append(
            {
                "properties": {
                    "target_kind": {"const": kind.value},
                    "after": {"anyOf": [{"$ref": f"#/$defs/{kind.value}_after"}, {"type": "null"}]},
                    "before": {"anyOf": [{"$ref": f"#/$defs/{kind.value}_element"}, {"type": "null"}]},
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
                "items": {"$ref": "#/$defs/AfterMaterialEvidence"},
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
            "items": {"type": "array", "maxItems": MAX_ITEMS, "items": {"$ref": "#/$defs/item"}},
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


# --- parsing ------------------------------------------------------------------


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
    draft: dict[str, Any]  # the pinned v2 session draft


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
    depends_on: list[str] = field(default_factory=list)  # item ids


@dataclass
class ParsedBatch:
    id: str
    result_sha256: str
    items: list[ParsedItem]


def batch_id_for(session_id: str, run_token: str) -> str:
    return str(uuid5(UUID(session_id), f"proposal-batch:{run_token}"))


def create_target_id(batch_id: str, client_ref: str) -> str:
    return str(uuid5(UUID(batch_id), f"create:{client_ref}"))


def item_fingerprint(operation: str, target_kind: str, target_id: str, after: dict | None) -> str:
    """Design §T1: sha256 over {operation, target_kind, target_id, after}."""
    projection = {
        "operation": operation,
        "target_kind": target_kind,
        "target_id": target_id,
        # A single element under algorithm B; null stays null.
        "after": json.loads(canonical(after)) if after is not None else None,
    }
    return domain_sha256(projection)


def _fail(code: str, message: str) -> ProposalContractError:
    return ProposalContractError(code, message)


def _check_quote(evidence: dict, lookup: MaterialLookup, where: str) -> None:
    try:
        check_material_evidence(evidence, lookup, where)
    except EvidenceError as exc:
        raise _fail(exc.code, str(exc)) from exc


def parse_result(
    raw: bytes | str | dict[str, Any],
    context: RunContext,
    *,
    material_lookup: MaterialLookup,
) -> ParsedBatch:
    raw_bytes = (
        raw if isinstance(raw, bytes) else raw.encode("utf-8") if isinstance(raw, str) else None
    )
    try:
        data = json.loads(raw_bytes) if raw_bytes is not None else deepcopy(raw)
    except ValueError as exc:
        raise _fail("RESULT_NOT_JSON", "建模结果不是合法 JSON") from exc
    # Algorithm C: the raw bytes as delivered. A dict (tests) is hashed as sorted
    # compact JSON; algorithm B's field table does not apply to results.
    result_sha256 = hashlib.sha256(
        raw_bytes
        if raw_bytes is not None
        else json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    errors = sorted(
        Draft202012Validator(result_schema()).iter_errors(data), key=lambda e: list(e.path)
    )
    if errors:
        first = errors[0]
        where = "/".join(map(str, first.path)) or "$"
        raise _fail("RESULT_SCHEMA_INVALID", f"建模结果不符合 {SCHEMA_VERSION}：{where}：{first.message}")

    pinned = {
        "run_token": context.run_token,
        "workspace_id": context.workspace_id,
        "session_id": context.session_id,
        "base_version_id": context.base_version_id,
        "base_version_sha256": context.base_version_sha256,
        "source_session_revision": context.source_session_revision,
        "source_draft_sha256": context.source_draft_sha256,
    }
    for key, expected in pinned.items():
        if data[key] != expected:
            raise _fail("RESULT_CONTEXT_MISMATCH", f"建模结果的 {key} 与本次运行固定的上下文不一致")

    draft = context.draft
    existing: dict[str, tuple[ElementKind, dict]] = {
        str(element["id"]): (kind, element)
        for kind, collection in COLLECTIONS.items()
        for element in draft.get(collection, [])
    }
    batch_id = batch_id_for(context.session_id, context.run_token)
    raw_items = data["items"]

    refs: dict[str, int] = {}
    for index, item in enumerate(raw_items):
        ref = item.get("client_ref")
        if ref is None:
            continue
        if ref in refs:
            raise _fail("CLIENT_REF_DUPLICATE", f"items[{index}]：client_ref {ref} 重复")
        refs[ref] = index
    targets: dict[int, str] = {}
    for index, item in enumerate(raw_items):
        op, kind = item["operation"], ElementKind(item["target_kind"])
        where = f"items[{index}]"
        if op == "create":
            if item.get("client_ref") is None:
                raise _fail("CREATE_WITHOUT_CLIENT_REF", f"{where}：新增必须带 client_ref")
            if item.get("target_id") is not None or item["before"] is not None or item["after"] is None:
                raise _fail("OPERATION_SHAPE", f"{where}：新增的 target_id、before 必须为 null，after 必须给出")
            targets[index] = create_target_id(batch_id, item["client_ref"])
            continue
        target = item.get("target_id")
        if target is None or target not in existing:
            raise _fail("TARGET_NOT_FOUND", f"{where}：{op} 的目标不在本次运行固定的草稿中")
        if existing[target][0] != kind:
            raise _fail("TARGET_KIND_MISMATCH", f"{where}：目标类型不是 {kind.value}")
        if item["before"] is None or (op == "update") != (item["after"] is not None):
            raise _fail("OPERATION_SHAPE", f"{where}：{op} 的 before/after 形态不正确")
        current = existing[target][1]
        if canonical(item["before"], None) != canonical(current, None):
            raise _fail("BEFORE_MISMATCH", f"{where}：before 与固定草稿中的目标不一致")
        if item.get("expected_target_hash") != element_sha256(current):
            raise _fail("TARGET_HASH_MISMATCH", f"{where}：expected_target_hash 与目标不一致")
        targets[index] = target

    def resolve(value: Any, index: int, deps: set[int], where: str) -> Any:
        if isinstance(value, dict) and set(value) == {"client_ref"}:
            ref = value["client_ref"]
            if ref not in refs or raw_items[refs[ref]]["operation"] != "create":
                raise _fail("CLIENT_REF_UNKNOWN", f"{where}：client_ref {ref} 不是本批次的新增项")
            if refs[ref] == index:
                raise _fail("DEPENDENCY_CYCLE", f"{where}：元素不能引用自身")
            deps.add(refs[ref])
            return targets[refs[ref]]
        if value is not None and str(value) not in existing:
            raise _fail("REFERENCE_UNKNOWN", f"{where}：引用的元素 {value} 不在固定草稿中")
        return value

    parsed: list[ParsedItem] = []
    item_ids = [str(uuid5(UUID(batch_id), f"item:{i}")) for i in range(len(raw_items))]
    deps_by_index: dict[int, set[int]] = {}
    for index, item in enumerate(raw_items):
        where = f"items[{index}]"
        kind = ElementKind(item["target_kind"])
        target_id = targets[index]
        deps: set[int] = set()
        for ref in item.get("depends_on") or []:
            if ref not in refs:
                raise _fail("DEPENDENCY_UNKNOWN", f"{where}：depends_on {ref} 不在本批次")
            deps.add(refs[ref])
        after = deepcopy(item["after"])
        if after is not None:
            if "id" in after and str(after["id"]) != target_id:
                raise _fail("OPERATION_SHAPE", f"{where}：after.id 必须等于目标 id")
            after["id"] = target_id
            for path in REFERENCE_FIELDS[kind]:
                if path.startswith("effects[]."):
                    key = path.split(".", 1)[1]
                    for effect in after.get("effects") or []:
                        effect[key] = resolve(effect.get(key), index, deps, f"{where}.effects.{key}")
                elif path.endswith("[]"):
                    key = path[:-2]
                    after[key] = [resolve(v, index, deps, f"{where}.{key}") for v in after.get(key) or []]
                elif path in after:
                    after[path] = resolve(after[path], index, deps, f"{where}.{path}")
            for sub, prefix in (("parameters", "parameter"), ("effects", "effect")):
                for position, entry in enumerate(after.get(sub) or []):
                    entry.setdefault("id", str(uuid5(UUID(target_id), f"{prefix}:{position}")))
            for position, evidence in enumerate(after.get("evidence") or []):
                if evidence.get("kind") == "manual":
                    continue
                evidence.setdefault(
                    "id",
                    str(uuid5(UUID(target_id), "evidence:" + canonical({k: v for k, v in evidence.items() if k != "id"}))),
                )
                _check_quote(evidence, material_lookup, f"{where}.evidence[{position}]")
            try:
                # The stored and fingerprinted form is the model's own dump:
                # omitted fields take their defaults, so a sparse `after` and
                # one spelling the defaults out are the same proposal.
                after = MODELS[kind].model_validate(after).model_dump(mode="json")
            except ValidationError as exc:
                raise _fail("ELEMENT_INVALID", f"{where}：{exc.errors()[0]['msg']}") from exc

            # Manual evidence is echoed from `before`, never authored: after must
            # carry exactly the same manual entries, unchanged.
            def manual(element: dict | None) -> str:
                entries = [e for e in (element or {}).get("evidence") or [] if e.get("kind") == "manual"]
                return canonical(entries, "evidence")

            before_model = (
                MODELS[kind].model_validate(item["before"]).model_dump(mode="json")
                if item["before"] is not None
                else None
            )
            if manual(after) != manual(before_model):
                raise _fail("MANUAL_EVIDENCE_FORBIDDEN", f"{where}：智能体不能新增、修改或删除人工证据")
        evidence = []
        for position, entry in enumerate(item.get("evidence") or []):
            entry = deepcopy(entry)
            entry.setdefault(
                "id",
                str(uuid5(UUID(target_id), "item-evidence:" + canonical({k: v for k, v in entry.items() if k != "id"}))),
            )
            try:
                entry = MaterialEvidence.model_validate(entry).model_dump(mode="json")
            except ValidationError as exc:
                raise _fail("RESULT_SCHEMA_INVALID", f"{where}.evidence[{position}]：{exc.errors()[0]['msg']}") from exc
            _check_quote(entry, material_lookup, f"{where}.evidence[{position}]")
            evidence.append(entry)
        deps_by_index[index] = deps
        parsed.append(
            ParsedItem(
                id=item_ids[index],
                ordinal=index,
                client_ref=item.get("client_ref"),
                operation=item["operation"],
                target_kind=kind.value,
                target_id=target_id,
                expected_target_hash=item.get("expected_target_hash"),
                before=item["before"],
                after=after,
                field_changes=item.get("field_changes") or [],
                evidence=evidence,
                reason=item.get("reason") or "",
                fingerprint=item_fingerprint(item["operation"], kind.value, target_id, after),
            )
        )

    # Two items acting on the same target would make acceptance order-dependent.
    seen_targets: dict[str, int] = {}
    for entry in parsed:
        if entry.target_id in seen_targets:
            raise _fail("TARGET_DUPLICATE", f"items[{entry.ordinal}]：与 items[{seen_targets[entry.target_id]}] 作用于同一目标")
        seen_targets[entry.target_id] = entry.ordinal
    fingerprints = [entry.fingerprint for entry in parsed]
    if len(set(fingerprints)) != len(fingerprints):
        raise _fail("ITEM_DUPLICATE", "同一批次中存在完全相同的提案")

    # Dependencies must form a DAG.
    state: dict[int, int] = {}

    def visit(node: int) -> None:
        if state.get(node) == 1:
            raise _fail("DEPENDENCY_CYCLE", f"items[{node}] 的依赖形成了环")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in deps_by_index[node]:
            visit(dep)
        state[node] = 2

    for node in deps_by_index:
        visit(node)
    for entry in parsed:
        entry.depends_on = sorted(item_ids[d] for d in deps_by_index[entry.ordinal])
    return ParsedBatch(id=batch_id, result_sha256=result_sha256, items=parsed)


def validate_draft_model(draft: dict[str, Any]) -> OntologyDraft:
    """Full cross-element validation, used when items are applied."""
    return OntologyDraft.model_validate(draft)
