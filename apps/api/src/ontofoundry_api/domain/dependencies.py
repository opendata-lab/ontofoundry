"""Stable-ID references and candidate analysis over unpersisted core drafts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from ontofoundry_api.domain.core import (
    COLLECTIONS,
    BindingMode,
    CoreDraft,
    DerivedExpression,
    DirectJoin,
    ExpressionBinding,
    ExpressionMetric,
    MappingTableJoin,
    PropertiesKey,
    RatioMetric,
    SimpleMetric,
)
from ontofoundry_api.domain.expressions import (
    render_references,
    resolve_derived_expression,
    resolve_field_expression,
    resolve_metric_expression,
    resolve_rule_expression,
)
from ontofoundry_api.domain.graph import DraftIndex


@dataclass(frozen=True)
class Reference:
    owner_id: UUID
    target_id: UUID
    path: str
    column: str | None = None


def reference_index(draft: CoreDraft) -> dict[UUID, tuple[Reference, ...]]:
    """Include dictionary keys, textual references and row-count dataset scopes."""
    index = DraftIndex(draft)
    refs: dict[UUID, list[Reference]] = {
        item.id: [] for collection in COLLECTIONS for item in getattr(draft, collection)
    }

    def add(owner, target, path, column=None):
        if target is not None:
            refs[owner].append(Reference(owner, target, path, column))

    def expression(owner, resolved, path):
        for ref in resolved.references:
            add(owner, ref.root_id, path)
            add(owner, ref.property_id, path)
            for link_id, _ in ref.links:
                add(owner, link_id, path)
            add(owner, ref.dataset_id, path, ref.column)

    def join(owner, value, path, source_type, target_type):
        if isinstance(value, DirectJoin):
            for prop in [*value.source_property_ids, *value.target_property_ids]:
                add(owner, prop, path)
        elif isinstance(value, MappingTableJoin):
            add(owner, value.dataset_id, path)
            for column in [*value.source_columns, *value.target_columns]:
                add(owner, value.dataset_id, path, column)
            for key, type_id in [
                (value.source_key, source_type),
                (value.target_key, target_type),
            ]:
                if isinstance(key, PropertiesKey):
                    for prop in key.property_ids:
                        add(owner, prop, path)
                else:
                    # Mapping-key joins depend on the effective source identity.
                    for type_in_chain in index.lineage(type_id):
                        mapping = next(
                            (m for m in draft.mappings if m.type_id == type_in_chain), None
                        )
                        if mapping is not None:
                            add(owner, mapping.id, path)

    for obj in draft.object_types:
        add(obj.id, obj.extends, "extends")
        add(obj.id, obj.title_property_id, "title_property_id")
        for i, branch in enumerate(obj.derived_by):
            path = f"derived_by.{i}"
            if isinstance(branch, DerivedExpression):
                expression(
                    obj.id,
                    resolve_derived_expression(draft, obj.extends, branch.expression),
                    path,
                )
            else:
                for condition in branch.conditions:
                    add(obj.id, condition.path.property_id, path)
                    for step in condition.path.links:
                        add(obj.id, step.link_type_id, path)
    for prop in draft.properties:
        add(prop.id, prop.owner_type_id, "owner_type_id")
    for link in draft.link_types:
        add(link.id, link.source_type_id, "source_type_id")
        add(link.id, link.target_type_id, "target_type_id")
        join(link.id, link.data_join, "data_join", link.source_type_id, link.target_type_id)
    for rule in draft.rules:
        add(rule.id, rule.owner_id, "owner_id")
        expression(rule.id, resolve_rule_expression(draft, rule), "expression")
    for metric in draft.metrics:
        if isinstance(metric, RatioMetric):
            add(metric.id, metric.numerator_id, "numerator_id")
            add(metric.id, metric.denominator_id, "denominator_id")
            continue
        add(metric.id, metric.dataset_id, "dataset_id")
        if metric.time_field:
            add(metric.id, metric.dataset_id, "time_field", metric.time_field.column)
        if isinstance(metric, SimpleMetric):
            if metric.measure:
                add(metric.id, metric.dataset_id, "measure", metric.measure.column)
            for condition in metric.filters:
                add(metric.id, metric.dataset_id, "filters", condition.column.column)
        else:
            expression(metric.id, resolve_metric_expression(draft, metric), "expression")
    for mapping in draft.mappings:
        add(mapping.id, mapping.type_id, "type_id")
        if mapping.binding_mode == BindingMode.SHARED_PARENT:
            for ancestor in index.ancestors(mapping.type_id):
                parent = next((m for m in draft.mappings if m.type_id == ancestor), None)
                if parent:
                    add(mapping.id, parent.id, "binding_mode")
        for source in mapping.sources:
            add(mapping.id, source.dataset_id, f"sources.{source.id}")
            for column in source.key_columns:
                add(
                    mapping.id,
                    source.dataset_id,
                    f"sources.{source.id}.key_columns",
                    column,
                )
        from ontofoundry_api.domain.bindings import resolve_binding

        effective = resolve_binding(draft, mapping.type_id)
        for name, binding in mapping.fields.items():
            prop = index.property_by_name(mapping.type_id, name)
            if prop:
                add(mapping.id, prop.id, f"fields.{name}")
            if isinstance(binding, ExpressionBinding):
                expression(
                    mapping.id,
                    resolve_field_expression(draft, mapping, binding.expression),
                    f"fields.{name}",
                )
            elif binding.source_id in effective.sources:
                add(
                    mapping.id,
                    effective.sources[binding.source_id].dataset_id,
                    f"fields.{name}",
                    binding.column,
                )
        for link_id, value in mapping.inherited_link_bindings.items():
            add(mapping.id, link_id, "inherited_link_bindings")
            join(
                mapping.id,
                value,
                "inherited_link_bindings",
                mapping.type_id,
                index.links[link_id].target_type_id,
            )
    for fact in draft.material_objects:
        add(fact.id, fact.type_id, "type_id")
        for name in fact.values:
            prop = index.property_by_name(fact.type_id, name)
            if prop:
                add(fact.id, prop.id, f"values.{name}")
    for fact in draft.material_links:
        for name in ("type_id", "source_id", "target_id"):
            add(fact.id, getattr(fact, name), name)
    return {owner: tuple(values) for owner, values in refs.items()}


def reverse_dependencies(
    draft: CoreDraft, targets: set[UUID], *, transitive: bool = True
) -> set[UUID]:
    reverse = defaultdict(set)
    for owner, refs in reference_index(draft).items():
        for ref in refs:
            reverse[ref.target_id].add(owner)
    found, pending = set(), list(targets)
    while pending:
        target = pending.pop()
        for owner in reverse[target] - found - targets:
            found.add(owner)
            if transitive:
                pending.append(owner)
    return found


def rewrite_references(before: CoreDraft, candidate: CoreDraft) -> CoreDraft:
    """Rewrite unchanged definitions using the old graph, supporting name swaps.

    Explicitly edited expression text is resolved only in the final candidate;
    it must not be interpreted using an obsolete namespace.
    """
    result = candidate.model_copy(deep=True)
    old = DraftIndex(before)
    new = DraftIndex(result)
    old_rules = {r.id: r for r in before.rules}
    for rule in result.rules:
        previous = old_rules.get(rule.id)
        if previous and rule.expression == previous.expression:
            rule.expression = render_references(
                resolve_rule_expression(before, previous), result
            )
    for obj in result.object_types:
        previous = old.objects.get(obj.id)
        if previous:
            for i, branch in enumerate(obj.derived_by):
                if (
                    i < len(previous.derived_by)
                    and isinstance(branch, DerivedExpression)
                    and branch == previous.derived_by[i]
                ):
                    branch.expression = render_references(
                        resolve_derived_expression(
                            before, previous.extends, branch.expression
                        ),
                        result,
                    )
    old_metrics = {m.id: m for m in before.metrics}
    for metric in result.metrics:
        previous = old_metrics.get(metric.id)
        if (
            isinstance(metric, ExpressionMetric)
            and isinstance(previous, ExpressionMetric)
            and metric.expression == previous.expression
        ):
            metric.expression = render_references(
                resolve_metric_expression(before, previous), result
            )
    old_mappings = {m.id: m for m in before.mappings}

    def rewrite_fields(previous, fields):
        rewritten = {}
        for name, original_binding in fields.items():
            binding = original_binding.model_copy(deep=True)
            prop = old.property_by_name(previous.type_id, name)
            if prop and prop.id in new.properties and name in previous.fields:
                name = new.properties[prop.id].technical_name
                if (
                    isinstance(binding, ExpressionBinding)
                    and binding == previous.fields[prop.technical_name]
                ):
                    binding.expression = render_references(
                        resolve_field_expression(before, previous, binding.expression),
                        result,
                    )
            if name in rewritten:
                raise ValueError("属性改名后的绑定键冲突")
            rewritten[name] = binding
        return rewritten

    for mapping in result.mappings:
        previous = old_mappings.get(mapping.id)
        if previous is None:
            continue
        # Recognize the exact final rewrite before interpreting any submitted key
        # in the old namespace. In a swap every final name is also an old name.
        try:
            final_fields = rewrite_fields(previous, previous.fields)
        except ValueError:
            # An explicit removal/revision may eliminate an obsolete reference.
            # Only rewriting the submitted definition is authoritative then.
            final_fields = None
        if mapping.fields != final_fields:
            mapping.fields = rewrite_fields(previous, mapping.fields)

    def rewrite_values(previous, values):
        rewritten = {}
        for name, value in values.items():
            prop = old.property_by_name(previous.type_id, name)
            if prop and prop.id in new.properties and name in previous.values:
                name = new.properties[prop.id].technical_name
            if name in rewritten:
                raise ValueError("属性改名后的事实值键冲突")
            rewritten[name] = value
        return rewritten

    old_facts = {fact.id: fact for fact in before.material_objects}
    for fact in result.material_objects:
        previous = old_facts.get(fact.id)
        if previous is None:
            continue
        try:
            final_values = rewrite_values(previous, previous.values)
        except ValueError:
            final_values = None
        if fact.values != final_values:
            fact.values = rewrite_values(previous, fact.values)
    return result


def affected_metrics(before: CoreDraft, candidate: CoreDraft) -> set[UUID]:
    """Dataset changes propagate through simple/expression -> ratio, never objects."""
    old = {d.id: d for d in before.datasets}
    new = {d.id: d for d in candidate.datasets}
    changed = {did for did in old.keys() | new.keys() if old.get(did) != new.get(did)}
    old_metrics = {m.id: m for m in before.metrics}
    new_metrics = {m.id: m for m in candidate.metrics}
    changed_metrics = {
        mid
        for mid in old_metrics.keys() | new_metrics.keys()
        if old_metrics.get(mid) != new_metrics.get(mid)
    }
    affected = set(changed_metrics)
    for draft in (before, candidate):
        # No ontology parsing here: unrelated ontology edits can be incomplete.
        pending = changed_metrics | {
            m.id
            for m in draft.metrics
            if not isinstance(m, RatioMetric) and m.dataset_id in changed
        }
        affected.update(pending)
        while pending:
            following = {
                m.id
                for m in draft.metrics
                if isinstance(m, RatioMetric)
                and (m.numerator_id in pending or m.denominator_id in pending)
            } - affected
            affected.update(following)
            pending = following
    return affected


def validate_candidate_graph(before: CoreDraft, candidate: CoreDraft) -> CoreDraft:
    from ontofoundry_api.domain.validation import validate_core_graph

    return validate_core_graph(rewrite_references(before, candidate))
