"""Lookups over a core-1 draft that follow single-parent inheritance.

Shared by expression resolution, validation and dependency analysis. A child
holds only what it adds: inherited properties, links and rules keep their
original ids and owners and are read through the ancestor chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from ontofoundry_api.domain.core import CoreDraft, Dataset, LinkType, ObjectType, Property


@dataclass
class DraftIndex:
    """Id lookups built once per draft."""

    draft: CoreDraft
    objects: dict[UUID, ObjectType] = field(init=False)
    properties: dict[UUID, Property] = field(init=False)
    links: dict[UUID, LinkType] = field(init=False)
    datasets: dict[UUID, Dataset] = field(init=False)

    def __post_init__(self) -> None:
        self.objects = {o.id: o for o in self.draft.object_types}
        self.properties = {p.id: p for p in self.draft.properties}
        self.links = {link.id: link for link in self.draft.link_types}
        self.datasets = {d.id: d for d in self.draft.datasets}

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

    def effective_properties(self, type_id: UUID) -> list[Property]:
        """Own properties, then inherited ones, nearest ancestor first."""
        owners = self.lineage(type_id)
        rank = {owner: i for i, owner in enumerate(owners)}
        found = [p for p in self.draft.properties if p.owner_type_id in rank]
        return sorted(found, key=lambda p: rank[p.owner_type_id])

    def property_by_name(self, type_id: UUID, technical_name: str) -> Property | None:
        wanted = technical_name.lower()
        for prop in self.effective_properties(type_id):
            if prop.technical_name.lower() == wanted:
                return prop
        return None

    def outgoing_links(self, type_id: UUID) -> list[LinkType]:
        """Links whose source is this object or an ancestor (forward direction)."""
        owners = set(self.lineage(type_id))
        return [link for link in self.draft.link_types if link.source_type_id in owners]

    def incoming_links(self, type_id: UUID) -> list[LinkType]:
        """Links whose target is this object or an ancestor (reverse direction)."""
        owners = set(self.lineage(type_id))
        return [link for link in self.draft.link_types if link.target_type_id in owners]

    def identifier(self, type_id: UUID) -> list[Property]:
        """Effective identifier properties, ordered by property UUID bytes."""
        props = [p for p in self.effective_properties(type_id) if p.identifier]
        return sorted(props, key=lambda p: p.id.bytes)

    def children(self, type_id: UUID) -> list[ObjectType]:
        return [o for o in self.draft.object_types if o.extends == type_id]

    def effective_links(self, type_id: UUID) -> list[LinkType]:
        """Both directions, with a self-link occurring once."""
        return list(
            {
                link.id: link
                for link in [*self.outgoing_links(type_id), *self.incoming_links(type_id)]
            }.values()
        )

    def effective_rules(self, type_id: UUID):
        owners = {
            *self.lineage(type_id),
            *(prop.id for prop in self.effective_properties(type_id)),
            *(link.id for link in self.outgoing_links(type_id)),
        }
        return [rule for rule in self.draft.rules if rule.owner_id in owners]

    def title_property(self, type_id: UUID) -> Property | None:
        for ancestor_id in self.lineage(type_id):
            obj = self.objects.get(ancestor_id)
            if obj is not None and obj.title_property_id is not None:
                return self.properties.get(obj.title_property_id)
        return None
