"""Lookups over a core-1 draft that follow single-parent inheritance.

Shared by expression resolution, validation and dependency analysis. A child
holds only what it adds: inherited properties, links and rules keep their
original ids and owners and are read through the ancestor chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from uuid import UUID

from ontofoundry_api.domain.core import (
    CoreDraft,
    Dataset,
    LinkType,
    ObjectType,
    Property,
    ValueType,
)


def _memoized(method):
    @wraps(method)
    def read(self, type_id):
        if getattr(self.draft, "_published_index", None) is not self:
            return method(self, type_id)
        key = (method.__name__, type_id)
        if key not in self._memo:
            self._memo[key] = tuple(method(self, type_id))
        return list(self._memo[key])

    return read


@dataclass
class DraftIndex:
    """Id lookups built once per draft."""

    draft: CoreDraft
    objects: dict[UUID, ObjectType] = field(init=False)
    properties: dict[UUID, Property] = field(init=False)
    links: dict[UUID, LinkType] = field(init=False)
    datasets: dict[UUID, Dataset] = field(init=False)
    value_types: dict[UUID, ValueType] = field(init=False)

    properties_by_owner: dict = field(init=False)
    rules_by_owner: dict = field(init=False)
    children_by_parent: dict = field(init=False)
    outgoing_by_owner: dict = field(init=False)
    incoming_by_owner: dict = field(init=False)
    mappings_by_type: dict = field(init=False)
    elements: dict = field(init=False)
    names: dict = field(init=False)
    _memo: dict = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.objects = {o.id: o for o in self.draft.object_types}
        self.properties = {p.id: p for p in self.draft.properties}
        self.links = {link.id: link for link in self.draft.link_types}
        self.datasets = {d.id: d for d in self.draft.datasets}
        self.value_types = {v.id: v for v in self.draft.value_types}

        def group(items, key):
            result = {}
            for ordinal, item in enumerate(items):
                result.setdefault(getattr(item, key), []).append((ordinal, item))
            return result

        self.properties_by_owner = group(self.draft.properties, "owner_type_id")
        self.rules_by_owner = group(self.draft.rules, "owner_id")
        self.children_by_parent = group(self.draft.object_types, "extends")
        self.outgoing_by_owner = group(self.draft.link_types, "source_type_id")
        self.incoming_by_owner = group(self.draft.link_types, "target_type_id")
        self.mappings_by_type = {m.type_id: m for m in self.draft.mappings}
        self.elements, self.names = {}, {}
        for kind, collection in (
            ("object_type", "object_types"),
            ("link_type", "link_types"),
            ("property", "properties"),
            ("rule", "rules"),
            ("metric", "metrics"),
            ("dataset", "datasets"),
            ("mapping", "mappings"),
            ("value_type", "value_types"),
        ):
            for item in getattr(self.draft, collection):
                self.elements[item.id] = (kind, item)
                if hasattr(item, "name"):
                    self.names.setdefault(item.name.casefold(), []).append((kind, item))

    def grouped(self, groups, owners):
        return [
            item
            for _, item in sorted(
                (pair for owner in owners for pair in groups.get(owner, [])),
                key=lambda pair: pair[0],
            )
        ]

    @_memoized
    def ancestors(self, type_id: UUID) -> list[UUID]:
        """Parent first, root last. Stops at a cycle or a missing parent."""
        chain: list[UUID] = []
        current = self.objects.get(type_id)
        while current is not None and current.extends is not None:
            if current.extends in chain or current.extends == type_id:
                break
            chain.append(current.extends)
            current = self.objects.get(current.extends)
        return chain

    def lineage(self, type_id: UUID) -> list[UUID]:
        """The object itself, then its ancestors."""
        return [type_id, *self.ancestors(type_id)]

    def is_a(self, type_id: UUID, ancestor_id: UUID) -> bool:
        return ancestor_id in self.lineage(type_id)

    @_memoized
    def effective_properties(self, type_id: UUID) -> list[Property]:
        """Own properties, then inherited ones, nearest ancestor first."""
        owners = self.lineage(type_id)
        rank = {owner: i for i, owner in enumerate(owners)}
        found = self.grouped(self.properties_by_owner, owners)
        return sorted(found, key=lambda p: rank[p.owner_type_id])

    def property_by_name(self, type_id: UUID, name: str) -> Property | None:
        wanted = name.lower()
        for prop in self.effective_properties(type_id):
            if prop.name.lower() == wanted:
                return prop
        return None

    @_memoized
    def outgoing_links(self, type_id: UUID) -> list[LinkType]:
        """Links whose source is this object or an ancestor (forward direction)."""
        owners = set(self.lineage(type_id))
        return self.grouped(self.outgoing_by_owner, owners)

    @_memoized
    def incoming_links(self, type_id: UUID) -> list[LinkType]:
        """Links whose target is this object or an ancestor (reverse direction)."""
        owners = set(self.lineage(type_id))
        return self.grouped(self.incoming_by_owner, owners)

    @_memoized
    def identifier(self, type_id: UUID) -> list[Property]:
        """Effective identifier properties, ordered by property UUID bytes."""
        props = [p for p in self.effective_properties(type_id) if p.identifier]
        return sorted(props, key=lambda p: p.id.bytes)

    @_memoized
    def children(self, type_id: UUID) -> list[ObjectType]:
        return self.grouped(self.children_by_parent, [type_id])

    @_memoized
    def effective_links(self, type_id: UUID) -> list[LinkType]:
        """Both directions, with a self-link occurring once."""
        return list(
            {
                link.id: link
                for link in [*self.outgoing_links(type_id), *self.incoming_links(type_id)]
            }.values()
        )

    @_memoized
    def effective_rules(self, type_id: UUID):
        owners = {
            *self.lineage(type_id),
            *(prop.id for prop in self.effective_properties(type_id)),
            *(link.id for link in self.outgoing_links(type_id)),
        }
        return self.grouped(self.rules_by_owner, owners)

    def title_property(self, type_id: UUID) -> Property | None:
        for ancestor_id in self.lineage(type_id):
            obj = self.objects.get(ancestor_id)
            if obj is not None and obj.title_property_id is not None:
                return self.properties.get(obj.title_property_id)
        return None


def draft_index(draft: CoreDraft) -> DraftIndex:
    """Only published read contexts attach an index; mutable drafts build local indexes."""
    index = getattr(draft, "_published_index", None)
    return index if index is not None else DraftIndex(draft)
