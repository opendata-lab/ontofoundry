"""What must hold before proposals are accepted (docs/design/2026-11-15-accept-completeness.md).

Proposals may be incomplete; accepting them may not. Definition checks run only
for definitions being accepted and instance checks only for instances being
accepted (AC-08), each on the draft as it would be after the accept, so a
mapping accepted together with its property satisfies the property.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import CoreDraft, MaterialObject, Multiplicity
from ontofoundry_api.domain.graph import draft_index


@dataclass(frozen=True)
class Change:
    """One accepted proposal, reduced to what the checks read."""

    kind: str
    target_id: str
    after: dict | None
    before: dict | None = None


def _label(element) -> str:
    return element.display_name or element.name


def _touched_types(draft: CoreDraft, changes: list[Change]) -> set[UUID]:
    """Object types whose table binding an accept can change, with the
    descendants that share it."""
    index = draft_index(draft)
    types: set[UUID] = set()
    datasets: set[str] = set()
    for change in changes:
        element = change.after or change.before or {}
        if change.kind == "object_type":
            types.add(UUID(change.target_id))
        elif change.kind == "property" and element.get("owner_type_id"):
            types.add(UUID(str(element["owner_type_id"])))
        elif change.kind == "mapping" and element.get("type_id"):
            types.add(UUID(str(element["type_id"])))
        elif change.kind == "dataset":
            datasets.add(change.target_id)
    if datasets:
        for mapping in draft.mappings:
            if any(str(source.dataset_id) in datasets for source in mapping.sources):
                types.add(mapping.type_id)
    pending = [t for t in types if t in index.objects]
    found: set[UUID] = set()
    while pending:
        type_id = pending.pop()
        if type_id in found:
            continue
        found.add(type_id)
        pending.extend(child.id for child in index.children(type_id))
    return found


def _unsynced(index, dataset_id) -> str | None:
    dataset = index.datasets.get(dataset_id)
    if dataset is not None and not dataset.columns:
        return dataset.name
    return None


def definition_issues(draft: CoreDraft, changes: list[Change]) -> list[str]:
    """AC-04: a touched object that has a table is fully bound; AC-10: columns
    used by accepted metrics can be verified."""
    index = draft_index(draft)
    issues: list[str] = []
    for type_id in sorted(_touched_types(draft, changes), key=str):
        binding = resolve_binding(draft, type_id)
        if not binding.mappings:
            continue  # no table: document-only objects and virtual parents
        obj = index.objects[type_id]
        if binding.main is None or any(not s.key_columns for s in binding.sources.values()):
            issues.append(f"{_label(obj)}：来源逻辑键待补全")
        for prop in index.effective_properties(type_id):
            if prop.name not in binding.fields:
                issues.append(f"{_label(obj)}：属性 {_label(prop)}（{prop.name}）未绑定")
        for source in binding.sources.values():
            name = _unsynced(index, source.dataset_id)
            if name:
                issues.append(f"{_label(obj)}：请先同步数据集 {name} 的表结构，列无法验证")
    for change in changes:
        if change.kind != "metric" or change.after is None:
            continue
        for dataset_id in sorted(_dataset_ids(change.after)):
            name = _unsynced(index, UUID(dataset_id))
            if name:
                label = change.after.get("display_name") or change.after.get("name")
                issues.append(f"指标 {label}：请先同步数据集 {name} 的表结构，列无法验证")
    return list(dict.fromkeys(issues))


def _dataset_ids(value) -> set[str]:
    if isinstance(value, dict):
        found = {str(v) for k, v in value.items() if k == "dataset_id" and v}
        for v in value.values():
            found |= _dataset_ids(v)
        return found
    if isinstance(value, list):
        return set().union(*(_dataset_ids(v) for v in value)) if value else set()
    return set()


def link_count_issues(draft: CoreDraft, objects: dict, links: list[dict], changed: set[str]) -> list[str]:
    """AC-11: accepted relation instances respect the declared multiplicity.

    `objects` maps instance id to instance JSON, `links` is every relation
    instance after the accept, `changed` the ids of relations being accepted."""
    from ontofoundry_api.domain.instance_display import document_display_text

    index = draft_index(draft)

    def title(identity) -> str:
        obj = objects.get(str(identity))
        if obj is None:
            return str(identity)
        fact = MaterialObject.model_validate(obj)
        owner = index.objects.get(fact.type_id)
        name = _label(owner) if owner else ""
        return f"{name}「{document_display_text(draft, fact)}」"

    issues: list[str] = []
    for link in links:
        if str(link["id"]) not in changed:
            continue
        definition = index.links.get(UUID(str(link["type_id"])))
        if definition is None or definition.multiplicity == Multiplicity.MANY_TO_MANY:
            continue
        same = [o for o in links if o["type_id"] == link["type_id"] and o["id"] != link["id"]]
        for other in same:
            if other["source_id"] == link["source_id"]:
                issues.append(
                    f"{title(link['source_id'])}：关系 {_label(definition)} 只能连一个，"
                    f"已连 {title(other['target_id'])}"
                )
            elif definition.multiplicity == Multiplicity.ONE_TO_ONE and other["target_id"] == link["target_id"]:
                issues.append(
                    f"{title(link['target_id'])}：关系 {_label(definition)} 只能被连一次，"
                    f"已被 {title(other['source_id'])} 连接"
                )
    return list(dict.fromkeys(issues))
