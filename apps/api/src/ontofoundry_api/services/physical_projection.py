"""Authorized read DTOs derived from effective bindings, never core model fields."""

from uuid import UUID

from ontofoundry_api.contracts.read_models import (
    EffectiveBindingRead,
    EffectiveLinkRead,
    MembershipRead,
)
from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import RatioMetric
from ontofoundry_api.domain.graph import draft_index


def physical_projection(draft, kind, identity, dataset_views):
    """Use the same resolver as execution, including concrete virtual children."""
    index = draft_index(draft)
    dataset_ids, bindings, types = set(), [], []
    identity = UUID(str(identity))
    if kind == "object_type":
        types = [identity]
    elif kind == "link_type":
        link = index.links[identity]
        types = [link.source_type_id, link.target_type_id]
        if link.data_join and link.data_join.kind == "mapping_table":
            dataset_ids.add(link.data_join.dataset_id)
    elif kind == "metric":
        metric = next(m for m in draft.metrics if m.id == identity)
        components = (
            [
                m
                for m in draft.metrics
                if m.id in {metric.numerator_id, metric.denominator_id}
            ]
            if isinstance(metric, RatioMetric)
            else [metric]
        )
        dataset_ids.update(m.dataset_id for m in components)
    concrete = set()
    for type_id in types:
        concrete.update(resolve_binding(draft, type_id).virtual_types or (type_id,))
    for type_id in sorted(concrete, key=str):
        binding = resolve_binding(draft, type_id)
        links = []
        for link in index.effective_links(type_id):
            join = binding.link_bindings.get(link.id, link.data_join)
            if join and join.kind == "mapping_table":
                dataset_ids.add(join.dataset_id)
            links.append(
                EffectiveLinkRead(
                    link_type_id=link.id,
                    source_type_id=link.source_type_id,
                    target_type_id=link.target_type_id,
                    data_join=join,
                )
            )
        dataset_ids.update(s.dataset_id for s in binding.sources.values())
        bindings.append(
            EffectiveBindingRead(
                type_id=type_id,
                sources=list(binding.sources.values()),
                fields=binding.fields,
                memberships=[
                    MembershipRead(
                        type_id=m.type_id,
                        mapping_id=m.id,
                        binding_mode=m.binding_mode,
                        membership_source_id=m.membership_source_id,
                        derived_by=index.objects[m.type_id].derived_by,
                    )
                    for m in binding.mappings
                ],
                links=links,
            ).model_dump(mode="json")
        )
    dataset_views = dataset_views(dataset_ids) if callable(dataset_views) else dataset_views
    return {
        "effective_bindings": bindings,
        "datasets": [d for d in dataset_views if UUID(d["id"]) in dataset_ids],
    }
