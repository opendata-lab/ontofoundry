"""Identity matching and additive candidate construction for trusted imports."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from uuid import UUID

from ontofoundry_api.contracts.proposals import walk_references
from ontofoundry_api.domain.core import CoreDraft, DerivedExpression, ExpressionMetric
from ontofoundry_api.domain.dependencies import (
    reference_index,
    rewrite_references,
    strict_equal,
)
from ontofoundry_api.domain.expressions import (
    render_references,
    resolve_derived_expression,
    resolve_field_expression,
    resolve_metric_expression,
    resolve_rule_expression,
)
from ontofoundry_api.domain.models import COLLECTIONS
from ontofoundry_api.domain.validation import validate_core_graph


def elements(model):
    return {
        str(e.id): (kind.value, e.model_dump(mode="json"))
        for kind, c in COLLECTIONS.items()
        for e in getattr(model, c)
    }


def match_import(base: CoreDraft, source: CoreDraft, *, native: bool) -> dict[str, str]:
    """Lock all UUIDs before matching any natural key, including child UUIDs."""
    old, incoming = elements(base), elements(source)
    matched = {
        i: i for i, (k, _) in incoming.items() if native and i in old and old[i][0] == k
    }
    used = set(matched.values())

    def key(kind, item, remap):
        def owner(name):
            value = str(item[name])
            return remap.get(value, value)

        technical = str(item.get("name", "")).casefold()
        if kind in {"object_type", "metric", "value_type"}:
            return technical
        if kind == "property":
            return owner("owner_type_id"), technical
        if kind == "link_type":
            return owner("source_type_id"), technical
        if kind == "rule":
            return item["owner_kind"], owner("owner_id"), technical
        if kind == "dataset":
            return item["name"].casefold()
        if kind == "mapping":
            return owner("type_id")
        return None

    for kind in (
        "object_type",
        # Before properties and rules, which reference value types.
        "value_type",
        "property",
        "link_type",
        "rule",
        "metric",
        "dataset",
        "mapping",
        "material_object",
        "material_link",
    ):
        for ident, (found_kind, item) in incoming.items():
            if kind != found_kind or ident in matched:
                continue
            # A cross-kind UUID is a conflict, never permission to choose a different identity.
            if native and ident in old and old[ident][0] != kind:
                matched[ident] = ident
                continue
            natural = key(kind, item, matched)
            candidates = [
                i
                for i, (k, e) in old.items()
                if k == kind
                and i not in used
                and natural is not None
                and key(k, e, {}) == natural
            ]
            target = candidates[0] if len(candidates) == 1 else ident
            matched[ident] = target
            used.add(target)
    return matched


def rewrite_import_ids(source: CoreDraft, ids: dict[str, str]) -> CoreDraft:
    def resolve(value):
        return ids.get(str(value), str(value))

    data = source.model_dump(mode="json")
    for kind, collection in COLLECTIONS.items():
        data[collection] = [
            {**walk_references(kind.value, item, resolve), "id": resolve(item["id"])}
            for item in data[collection]
        ]
    result = CoreDraft.model_validate(data)

    def render(resolved):
        refs = tuple(
            replace(
                ref,
                root_id=UUID(resolve(ref.root_id)) if ref.root_id else None,
                property_id=UUID(resolve(ref.property_id)) if ref.property_id else None,
                dataset_id=UUID(resolve(ref.dataset_id)) if ref.dataset_id else None,
                links=tuple((UUID(resolve(i)), d) for i, d in ref.links),
            )
            for ref in resolved.references
        )
        return render_references(replace(resolved, references=refs), result)

    for previous, current in zip(source.rules, result.rules, strict=True):
        current.expression = render(resolve_rule_expression(source, previous))
    for previous, current in zip(source.object_types, result.object_types, strict=True):
        for before, after in zip(previous.derived_by, current.derived_by, strict=True):
            if isinstance(before, DerivedExpression):
                after.expression = render(
                    resolve_derived_expression(source, previous.extends, before.expression)
                )
    for previous, current in zip(source.metrics, result.metrics, strict=True):
        if isinstance(previous, ExpressionMetric):
            current.expression = render(resolve_metric_expression(source, previous))
    for previous, current in zip(source.mappings, result.mappings, strict=True):
        for name, binding in previous.fields.items():
            if binding.kind == "expression":
                current.fields[name].expression = render(
                    resolve_field_expression(source, previous, binding.expression)
                )
    return result


@dataclass
class CandidateGraph:
    model: CoreDraft
    id_map: dict[str, str]
    blocked: list[dict]
    changes: list[dict]
    unchanged: int


def build_candidate_graph(
    base: CoreDraft,
    source: CoreDraft,
    *,
    native: bool,
    registered: dict[str, str] | None = None,
) -> CandidateGraph:
    ids = match_import(base, source, native=native)
    imported = rewrite_import_ids(source, ids)
    original, incoming = elements(base), elements(imported)
    registered = {**{i: k for i, (k, _) in original.items()}, **(registered or {})}
    edges = {
        str(i): {str(r.target_id) for r in refs}
        for i, refs in reference_index(imported).items()
    }
    # Include reverse textual dependencies already present in the workspace.
    for i, refs in reference_index(base).items():
        if str(i) in incoming:
            edges.setdefault(str(i), set()).update(str(r.target_id) for r in refs)

    # Keep simultaneous name exchanges together while pruning unrelated errors.
    def namespace(kind, item):
        if kind in {"property", "link_type"}:
            return ("member", item.get("owner_type_id", item.get("source_type_id")))
        if kind == "rule":
            return (kind, item["owner_kind"], item["owner_id"])
        return (kind,)

    for ident, (kind, item) in incoming.items():
        if kind not in {
            "object_type",
            "property",
            "link_type",
            "rule",
            "metric",
            "dataset",
        }:
            continue
        fields = ("name",)
        for other, (old_kind, previous) in original.items():
            if (
                other == ident
                or other not in incoming
                or namespace(kind, item) != namespace(old_kind, previous)
            ):
                continue
            names = item
            old_names = previous
            if any(
                key in old_names
                and str(names.get(key, "")).casefold() == str(old_names[key]).casefold()
                for key in fields
            ):
                edges.setdefault(ident, set()).add(other)
                edges.setdefault(other, set()).add(ident)
    blocked = {}
    previous_evidence = {
        str(ev["id"]): i
        for i, (_, element) in original.items()
        for ev in element.get("evidence", [])
    }
    for ident, (kind, item) in incoming.items():
        if ident in registered and registered[ident] != kind:
            blocked[ident] = "UUID 已登记为其他元素种类"
        if any(
            str(e["id"]) in previous_evidence and previous_evidence[str(e["id"])] != ident
            for e in item.get("evidence", [])
        ):
            blocked[ident] = "证据 UUID 不能转移归属"
        previous = original.get(ident)
        if (
            kind == "dataset"
            and previous
            and not item.get("connection_id")
            and previous[1].get("connection_id")
        ):
            # Exchange files never carry connection ids; keep the local binding.
            item["connection_id"] = previous[1]["connection_id"]
        if kind == "dataset" and previous and item.get("columns") is None:
            # A missing column list means "not provided", not "remove the registered columns".
            item["columns"] = previous[1].get("columns")
        if previous and "evidence" in item:
            by_id = {e["id"]: e for e in item["evidence"]}
            for evidence in previous[1].get("evidence", []):
                if (
                    evidence["id"] in by_id
                    and evidence["kind"] == "manual"
                    and not strict_equal(evidence, by_id[evidence["id"]])
                ):
                    blocked[ident] = "已保存的人工证据不能修改"
                if evidence["id"] not in by_id:
                    item["evidence"].append(evidence)

    def closure(seeds):
        result = set(seeds)
        while True:
            extra = {i for i, refs in edges.items() if refs & result} - result
            if not extra:
                return result
            result.update(extra)

    for i in closure(blocked):
        blocked.setdefault(i, "依赖已阻断的导入元素")
    active = set(incoming) - set(blocked)

    def candidate(selected):
        data = deepcopy(base.model_dump(mode="json"))
        for kind, collection in COLLECTIONS.items():
            updates = {
                i: e for i, (k, e) in incoming.items() if i in selected and k == kind.value
            }
            data[collection] = [updates.pop(e["id"], e) for e in data[collection]] + list(
                updates.values()
            )
        return validate_core_graph(
            rewrite_references(
                base,
                CoreDraft.model_validate(data),
                explicit_ids=frozenset(UUID(i) for i in selected),
            )
        )

    # Remove dependency closures until the final graph is valid, then restore
    # every independently valid closure. Never synthesize deletion proposals.
    removed = []
    while True:
        try:
            final = candidate(active)
            break
        except ValueError as error:
            if not active:
                raise
            reason = str(error).splitlines()[0]
            choices = []
            for ident in sorted(active):
                group = closure({ident}) & active
                try:
                    candidate(active - group)
                except ValueError:
                    continue
                choices.append(group)
            group = (
                min(choices, key=lambda g: (len(g), sorted(g)))
                if choices
                else closure({sorted(active)[-1]}) & active
            )
            active -= group
            removed.append((group, reason))
    # Restoring larger groups first also retains valid atomic name exchanges.
    for group, reason in sorted(removed, key=lambda v: -len(v[0])):
        try:
            final = candidate(active | group)
            active |= group
        except ValueError:
            for ident in group:
                blocked[ident] = reason
    final = candidate(active)
    changes = []
    unchanged = 0
    for ident, (kind, item) in elements(final).items():
        old = original.get(ident)
        if old and strict_equal(old[1], item):
            unchanged += ident in incoming and ident in active
        else:
            changes.append(
                {
                    "target_kind": kind,
                    "target_id": ident,
                    "operation": "update" if old else "create",
                    "before": old[1] if old else None,
                    "after": item,
                }
            )
    return CandidateGraph(
        final,
        ids,
        [{"target_id": i, "reason": reason} for i, reason in sorted(blocked.items())],
        changes,
        unchanged,
    )
