"""The only way into a stored snapshot or draft.

`read_snapshot` accepts any stored shape (schema v1 or v2) and returns the v2
model. Services never look at `schema_version` or at v1 nesting themselves; if
something needs a snapshot, it calls this. Historical v1 rows are never
rewritten — normalization happens on every read and is deterministic, so the
same v1 row always yields the same v2 snapshot and the same hashes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.models import OntologyDraft, RuleKind, RuleOwnerKind


def empty_snapshot(workspace_id: str | UUID) -> dict[str, Any]:
    return OntologyDraft(workspace_id=workspace_id).model_dump(mode="json")


def _legacy_evidence(workspace: UUID, owner_id: str, items: list[dict]) -> list[dict]:
    result = []
    for index, item in enumerate(items or []):
        if item.get("kind"):  # already v2
            result.append(item)
            continue
        material_id = str(item.get("material_id") or "")
        start, end = int(item.get("line_start") or 1), int(item.get("line_end") or 1)
        result.append(
            {
                "kind": "material",
                "id": str(
                    uuid5(workspace, f"evidence:{owner_id}:{index}:{material_id}:{start}:{end}")
                ),
                "material_id": material_id,
                "material_sha256": None,
                "locator": {"heading": None, "line_start": start, "line_end": max(start, end)},
                "quote": item.get("quote") or "",
            }
        )
    return result


def legacy_rule_id(
    workspace: UUID, owner_kind: str, owner_id: str, rule_kind: str, expression: str
) -> UUID:
    """Stable id for a v1 `requires`/`derived_by` string (design §10.2).

    The same expression on the same owner always gets the same id, so reading a
    v1 row twice never invents two rules. Once in v2, editing the expression keeps
    the id; across two v1 versions a changed expression cannot be proven to be
    the same rule and shows as remove + add.
    """
    normalized = " ".join(expression.split())
    return uuid5(workspace, f"rule:{owner_kind}:{owner_id}:{rule_kind}:{normalized}")


def normalize_v1(data: dict[str, Any]) -> dict[str, Any]:
    """Map a schema-v1 draft dict onto schema v2. Pure: no database access."""
    workspace = UUID(str(data["workspace_id"]))
    object_types, properties, link_types, rules = [], [], [], []
    seen_rules: set[str] = set()

    def add_rules(owner_kind: RuleOwnerKind, owner: dict, label: str) -> None:
        for field, kind in (("requires", RuleKind.CONSTRAINT), ("derived_by", RuleKind.DERIVATION)):
            for expression in owner.get(field) or []:
                rule_id = str(
                    legacy_rule_id(workspace, owner_kind.value, str(owner["id"]), kind.value, expression)
                )
                if rule_id in seen_rules:
                    continue
                seen_rules.add(rule_id)
                rules.append(
                    {
                        "id": rule_id,
                        "name": f"{label}·{'约束' if kind == RuleKind.CONSTRAINT else '派生'}"
                        f"{len([r for r in rules if r['owner_id'] == str(owner['id'])]) + 1}",
                        "technical_name": f"{kind.value}_{rule_id.replace('-', '')[:8]}",
                        "description": "",
                        "owner_kind": owner_kind.value,
                        "owner_id": str(owner["id"]),
                        "rule_kind": kind.value,
                        "expression": expression,
                        "verbalizes": [],
                        "evidence": [],
                    }
                )

    for item in data.get("object_types") or []:
        object_types.append(
            {
                "id": item["id"],
                "name": item["name"],
                "technical_name": item["technical_name"],
                "description": item.get("description") or "",
                "tags": item.get("tags") or [],
                "extends": item.get("extends") or [],
                "evidence": [],
            }
        )
        add_rules(RuleOwnerKind.OBJECT_TYPE, item, item["name"])
        for attribute in item.get("attributes") or []:
            prop = {
                key: value
                for key, value in attribute.items()
                if key not in ("requires", "derived_by")
            }
            prop["owner_type_id"] = item["id"]
            prop.setdefault("verbalizes", [])
            prop["evidence"] = []
            properties.append(prop)
            add_rules(RuleOwnerKind.PROPERTY, attribute, f"{item['name']}.{attribute['name']}")
    for item in data.get("link_types") or []:
        link = {key: value for key, value in item.items() if key not in ("requires", "derived_by")}
        link["evidence"] = []
        link_types.append(link)
        add_rules(RuleOwnerKind.LINK_TYPE, item, item["name"])

    material_objects = [
        {**obj, "evidence": _legacy_evidence(workspace, str(obj["id"]), obj.get("evidence"))}
        for obj in data.get("objects") or []
    ]
    material_links = [
        {**link, "evidence": _legacy_evidence(workspace, str(link["id"]), link.get("evidence"))}
        for link in data.get("links") or []
    ]
    return {
        "schema_version": "2",
        "workspace_id": str(workspace),
        "ontology_requires": list(data.get("requires") or []),
        "object_types": object_types,
        "properties": properties,
        "link_types": link_types,
        "rules": rules,
        "actions": [],
        "material_objects": material_objects,
        "material_links": material_links,
        "mappings": list(data.get("mappings") or []),
    }


def as_v2_dict(data: dict[str, Any] | None, workspace_id: str | UUID | None = None) -> dict[str, Any]:
    """Stored JSON of either schema → v2 JSON (unvalidated; see read_snapshot)."""
    if not data:
        if workspace_id is None:
            raise ValueError("空快照必须提供 workspace_id")
        return empty_snapshot(workspace_id)
    if workspace_id is not None and str(data.get("workspace_id")) != str(workspace_id):
        raise ValueError("快照不属于该工作空间")
    version = str(data.get("schema_version") or "1")
    if version == "2":
        return data
    if version == "1":
        return normalize_v1(data)
    raise ValueError(f"不支持的快照 schema_version：{version}")


def read_snapshot(data: dict[str, Any] | None, workspace_id: str | UUID | None = None) -> OntologyDraft:
    """Validated v2 model for any stored snapshot or draft."""
    return OntologyDraft.model_validate(as_v2_dict(data, workspace_id))


def read_snapshot_json(
    data: dict[str, Any] | None, workspace_id: str | UUID | None = None
) -> dict[str, Any]:
    return read_snapshot(data, workspace_id).model_dump(mode="json")


def normalized_snapshot_sha256(
    data: dict[str, Any] | None, workspace_id: str | UUID | None = None
) -> str:
    return snapshot_sha256(read_snapshot_json(data, workspace_id))


def draft_sha256(data: dict[str, Any] | None, workspace_id: str | UUID | None = None) -> str:
    """`draft_sha256` of a stored draft of either schema (not validated)."""
    return snapshot_sha256(as_v2_dict(data, workspace_id))
