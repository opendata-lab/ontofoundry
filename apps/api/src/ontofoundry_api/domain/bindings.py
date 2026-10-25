"""Effective binding projections; readiness never changes the stored model."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from ontofoundry_api.domain.core import (
    BindingMode,
    ColumnBinding,
    CoreDraft,
    DataJoin,
    DataMapping,
    FieldBinding,
    MappingSource,
)
from ontofoundry_api.domain.graph import draft_index


@dataclass(frozen=True)
class ResolvedBinding:
    type_id: UUID
    mappings: tuple[DataMapping, ...] = ()
    sources: dict[str, MappingSource] = field(default_factory=dict)
    fields: dict[str, FieldBinding] = field(default_factory=dict)
    link_bindings: dict[UUID, DataJoin] = field(default_factory=dict)
    virtual_types: tuple[UUID, ...] = ()

    @property
    def main(self) -> MappingSource | None:
        return self.sources.get("main")


@dataclass(frozen=True)
class BindingReadiness:
    status: str
    reasons: tuple[str, ...] = ()


def resolve_binding(draft: CoreDraft, type_id: UUID) -> ResolvedBinding:
    index = getattr(draft, "_published_index", None)
    if index is None:
        return _resolve_binding(draft, type_id)
    key = ("binding", type_id)
    if key not in index._memo:
        index._memo[key] = _resolve_binding(draft, type_id)
    return index._memo[key]


def _resolve_binding(draft: CoreDraft, type_id: UUID) -> ResolvedBinding:
    """Walk from the root; shared children only add local sources and fields."""
    index = draft_index(draft)
    if type_id not in index.objects:
        raise ValueError("绑定对象不存在")
    by_type = index.mappings_by_type
    chain: list[DataMapping] = []
    sources: dict[str, MappingSource] = {}
    fields: dict[str, FieldBinding] = {}
    links: dict[UUID, DataJoin] = {}
    for ancestor_id in reversed(index.lineage(type_id)):
        mapping = by_type.get(ancestor_id)
        if mapping is None:
            continue
        if mapping.binding_mode == BindingMode.INDEPENDENT:
            chain, sources, fields, links = [], {}, {}, {}
        chain.append(mapping)
        sources.update({source.id: source for source in mapping.sources})
        fields.update(mapping.fields)
        links.update(mapping.inherited_link_bindings)
    virtual_types = (
        tuple(
            obj.id
            for obj in draft.object_types
            if obj.id != type_id
            and index.is_a(obj.id, type_id)
            and obj.id in by_type
            and not any(a in by_type for a in index.ancestors(obj.id))
        )
        if not chain
        else ()
    )
    return ResolvedBinding(type_id, tuple(chain), sources, fields, links, virtual_types)


MEMBERS_MISSING = "还没有成员条件：在概览中编辑“成员条件”，写明父表里哪些行属于本对象"


def binding_readiness(draft: CoreDraft, type_id: UUID) -> BindingReadiness:
    index = getattr(draft, "_published_index", None)
    if index is None:
        return _binding_readiness(draft, type_id)
    key = ("readiness", type_id)
    if key not in index._memo:
        index._memo[key] = _binding_readiness(draft, type_id)
    return index._memo[key]


def _binding_readiness(draft: CoreDraft, type_id: UUID) -> BindingReadiness:
    """Static readiness only. Connection/authorization checks belong to services."""
    from ontofoundry_api.domain.validation import physical_value_kind

    index = draft_index(draft)
    binding = resolve_binding(draft, type_id)
    if not binding.mappings:
        return BindingReadiness("virtual" if index.children(type_id) else "unbound")
    reasons: list[str] = []
    if binding.main is None or any(not s.key_columns for s in binding.sources.values()):
        return BindingReadiness("missing_key", ("来源逻辑键待补全",))
    # A descendant reads its mapped ancestor's table; its own mapping record is
    # optional (derivable), but which of those rows belong to it is not.
    mapped = {m.type_id for m in binding.mappings}
    for obj_id in index.lineage(type_id):
        obj = index.objects[obj_id]
        mapping = next((m for m in binding.mappings if m.type_id == obj_id), None)
        shares = any(a in mapped for a in index.ancestors(obj_id))
        if (
            shares
            and (mapping is None or mapping.binding_mode == BindingMode.SHARED_PARENT)
            and not obj.derived_by
            and (mapping is None or mapping.membership_source_id is None)
        ):
            reasons.append(f"{obj.display_name or obj.name}{MEMBERS_MISSING}")
    if reasons:
        return BindingReadiness("unbound", tuple(reasons))
    if any(p.name not in binding.fields for p in index.effective_properties(type_id)):
        reasons.append("属性绑定待补全")
    for source in binding.sources.values():
        dataset = index.datasets.get(source.dataset_id)
        if (
            dataset is None
            or not dataset.columns
            or any(
                physical_value_kind(column.physical_type) is None
                for column in dataset.columns
            )
        ):
            reasons.append("来源列元数据待补全")
    if reasons:
        return BindingReadiness("unbound", tuple(dict.fromkeys(reasons)))
    return BindingReadiness("bound")


def column_binding(
    draft: CoreDraft, type_id: UUID, property_id: UUID
) -> ColumnBinding | None:
    prop = draft_index(draft).properties.get(property_id)
    if prop is None:
        return None
    binding = resolve_binding(draft, type_id).fields.get(prop.name)
    return binding if isinstance(binding, ColumnBinding) else None
