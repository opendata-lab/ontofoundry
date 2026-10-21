"""Namespace and rewrite regressions, including literals, direction and scope."""

from uuid import uuid4

import pytest
from core1_fixtures import example_draft

from ontofoundry_api.domain.core import ExpressionMetric, Rule
from ontofoundry_api.domain.expressions import (
    ExpressionError,
    render_references,
    resolve_derived_expression,
    resolve_field_expression,
    resolve_metric_expression,
    resolve_rule_expression,
)


def _rule(draft, text, owner=None):
    return Rule(
        id=uuid4(),
        display_name="校验",
        name="check_value",
        owner_kind="object_type",
        owner_id=owner or draft.object_types[0].id,
        rule_kind="constraint",
        expression=text,
    )


def _sales_rule(text):
    draft = example_draft("01-basic-sales")
    order = next(o for o in draft.object_types if o.name == "sales_order")
    return draft, _rule(draft, text, order.id)


def test_rule_reserved_word_and_literal_parameter_are_preserved():
    draft, rule = _sales_rule(
        "sales_order.amount > :amount AND 'sales_order.amount' <> 'x'"
    )
    resolved = resolve_rule_expression(draft, rule)
    changed = draft.model_copy(deep=True)
    next(o for o in changed.object_types if o.id == rule.owner_id).name = "order"
    amount = next(
        p
        for p in changed.properties
        if p.owner_type_id == rule.owner_id and p.name == "amount"
    )
    amount.name = "total"
    text = render_references(resolved, changed)
    assert text == "order.total > :amount AND 'sales_order.amount' <> 'x'"
    rule.expression = text
    assert resolve_rule_expression(changed, rule).references[0].property_id == amount.id


@pytest.mark.parametrize(
    "text",
    [
        "SUM(sales_order.amount)",
        "sales_order.amount OVER ()",
        "(SELECT 1)",
        "sales_order.customer",
        "customer.customer_no IS NOT NULL",
        "amount > 0",
        "sales_order.missing > 0",
        "sales_order.amount; DROP TABLE orders",
        "EXISTS (sales_order.customer)",
        "sales_order.*",
        " ",
    ],
)
def test_rules_reject_invalid_or_unquantified_references(text):
    draft, rule = _sales_rule(text)
    with pytest.raises(ExpressionError):
        resolve_rule_expression(draft, rule)


def test_rule_property_and_link_owners_use_definition_context():
    draft = example_draft("08-rules")
    for owner_kind, owner_id, text in [
        ("property", draft.properties[0].id, "sales_order.order_no IS NOT NULL"),
        (
            "link_type",
            draft.link_types[0].id,
            "sales_order.customer.customer_no IS NOT NULL",
        ),
    ]:
        rule = _rule(draft, text)
        rule.owner_kind, rule.owner_id = owner_kind, owner_id
        assert resolve_rule_expression(draft, rule).references


def test_exists_reverse_collection_self_and_parallel_links():
    draft = example_draft("05-self-and-parallel-links")
    employee = next(o for o in draft.object_types if o.name == "employee")
    manager = next(
        link
        for link in draft.link_types
        if link.source_type_id == employee.id and link.target_type_id == employee.id
    )
    forward = f"EXISTS (employee.{manager.name})"
    reverse = f"EXISTS (employee.REVERSE({manager.name}))"
    first = resolve_derived_expression(draft, employee.id, forward).references[0]
    second = resolve_derived_expression(draft, employee.id, reverse).references[0]
    assert first.links == ((manager.id, "forward"),)
    assert second.links == ((manager.id, "reverse"),)
    prop = next(p for p in draft.properties if p.owner_type_id == employee.id)
    with pytest.raises(ExpressionError, match="集合"):
        resolve_derived_expression(
            draft,
            employee.id,
            f"employee.REVERSE({manager.name}).{prop.name} IS NULL",
        )
    assert resolve_derived_expression(
        draft,
        employee.id,
        f"employee.{manager.name}.{prop.name} IS NULL",
    )
    trade = next(o for o in draft.object_types if o.name == "trade")
    parallel = [link for link in draft.link_types if link.source_type_id == trade.id]
    refs = [
        resolve_derived_expression(
            draft, trade.id, f"EXISTS (trade.{link.name})"
        ).references[0]
        for link in parallel
    ]
    assert len({r.links for r in refs}) == len(parallel)


def test_multihop_exists_rewrite_leaves_wrapper_and_string_unchanged():
    draft = example_draft("05-self-and-parallel-links")
    employee = next(o for o in draft.object_types if o.name == "employee")
    manager = next(
        link
        for link in draft.link_types
        if link.source_type_id == employee.id and link.target_type_id == employee.id
    )
    text = (
        f"EXISTS ( employee.{manager.name}.REVERSE({manager.name}) ) AND 'employee' <> ''"
    )
    resolved = resolve_derived_expression(draft, employee.id, text)
    candidate = draft.model_copy(deep=True)
    next(o for o in candidate.object_types if o.id == employee.id).name = "person"
    next(link for link in candidate.link_types if link.id == manager.id).name = "boss"
    assert (
        render_references(resolved, candidate)
        == "EXISTS ( person.boss.REVERSE(boss) ) AND 'employee' <> ''"
    )


def test_membership_exists_rejects_arbitrary_sql_query():
    draft, rule = _sales_rule("1 = 1")
    with pytest.raises(ExpressionError):
        resolve_derived_expression(draft, rule.owner_id, "EXISTS (SELECT 1 FROM orders)")


@pytest.mark.parametrize(
    "text",
    [
        "SUM(main.total_spent)",
        "main.total_spent OVER ()",
        "other.total_spent",
        "customer.level",
        "(SELECT main.total_spent)",
        "main.*",
        "main.total_spent + computed",
    ],
)
def test_field_expressions_are_same_row_physical_columns_only(text):
    draft = example_draft("08-rules")
    mapping = next(m for m in draft.mappings if "level" in m.fields)
    with pytest.raises(ExpressionError):
        resolve_field_expression(draft, mapping, text)


def test_field_case_and_cross_source_arithmetic_are_allowed():
    draft = example_draft("08-rules")
    mapping = next(m for m in draft.mappings if "level" in m.fields)
    assert resolve_field_expression(
        draft, mapping, mapping.fields["level"].expression
    ).references
    multi = example_draft("11-multi-source-and-unique-link")
    mapping = next(m for m in multi.mappings if len(m.sources) > 1)
    refs = resolve_field_expression(
        multi,
        mapping,
        "CASE WHEN main.account_id IS NULL THEN 0 ELSE amounts.available_amount END",
    )
    assert {r.source_id for r in refs.references} == {"main", "amounts"}


def _metric(text):
    draft = example_draft("01-basic-sales")
    ds = next(d for d in draft.datasets if d.name == "orders")
    metric = ExpressionMetric(
        id=uuid4(),
        display_name="复杂指标",
        name="complex_metric",
        kind="expression",
        dataset_id=ds.id,
        expression=text,
    )
    return draft, metric


@pytest.mark.parametrize(
    "text",
    [
        "SUM(orders.amount)",
        "COUNT(*)",
        "COUNT(orders.amount)",
        "COUNT(CASE WHEN orders.status = 'Y' THEN orders.amount END)",
        "COUNT(DISTINCT orders.order_id || '::' || orders.status)",
        "SUM(CASE WHEN orders.status = 'Y' OR orders.status = 'N' THEN orders.amount ELSE 0 END)",
        "CUSTOM_ENGINE_AGG(orders.amount)",
    ],
)
def test_metric_semantic_save_is_broader_than_preview_engine(text):
    draft, metric = _metric(text)
    resolved = resolve_metric_expression(draft, metric)
    assert resolved.text == text


@pytest.mark.parametrize(
    "text",
    [
        "SELECT SUM(orders.amount)",
        "SUM(orders.amount) FROM orders",
        "SUM(customers.customer_id)",
        "SUM(orders.amount) OVER ()",
        "SUM(sales_order.amount)",
        "SUM(orders.no_such_column)",
        "SUM(orders.amount) + (SELECT 1)",
        "SUM(orders.amount); SELECT 1",
        "orders.*",
        "*",
        "SUM(amount)",
        "SUM(orders.amount) AS total",
    ],
)
def test_metric_rejects_query_scopes_and_other_datasets(text):
    draft, metric = _metric(text)
    with pytest.raises(ExpressionError):
        resolve_metric_expression(draft, metric)


def test_dataset_rename_uses_id_and_preserves_strings_comments_parameters():
    draft, metric = _metric(
        "SUM(orders.amount) + :amount /* orders.amount */ + CASE WHEN 'orders.amount' = '' THEN 1 ELSE 0 END"
    )
    resolved = resolve_metric_expression(draft, metric)
    next(d for d in draft.datasets if d.id == metric.dataset_id).name = "sales data"
    rendered = render_references(resolved, draft)
    assert rendered.startswith('SUM("sales data".amount) + :amount /* orders.amount */')
    assert "'orders.amount'" in rendered
    metric.expression = rendered
    assert (
        resolve_metric_expression(draft, metric).references[0].dataset_id
        == metric.dataset_id
    )


def test_internal_placeholder_names_cannot_bypass_column_resolution():
    draft, metric = _metric("SUM(orders.amount) + __core_ref_1")
    with pytest.raises(ExpressionError, match="无法解析"):
        resolve_metric_expression(draft, metric)


@pytest.mark.parametrize("text", ["USE example_database", "BEGIN", "COMMIT"])
def test_statement_roots_are_not_scalar_expressions(text):
    draft, metric = _metric(text)
    with pytest.raises(ExpressionError):
        resolve_metric_expression(draft, metric)


def test_unknown_function_cannot_claim_scalar_field_semantics():
    draft = example_draft("08-rules")
    mapping = next(m for m in draft.mappings if "level" in m.fields)
    with pytest.raises(ExpressionError, match="标量函数"):
        resolve_field_expression(draft, mapping, "CUSTOM_AGG(main.total_spent)")


@pytest.mark.parametrize(
    "text",
    [
        "SUM(orders.amount) FILTER (WHERE orders.status = 'Y')",
        "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY orders.amount)",
    ],
)
def test_aggregate_modifiers_keep_single_dataset_semantics(text):
    draft, metric = _metric(text)
    assert resolve_metric_expression(draft, metric).references


def test_aggregate_filter_cannot_add_another_dataset_scope():
    draft, metric = _metric("SUM(orders.amount) FILTER (WHERE customers.region = 'Y')")
    with pytest.raises(ExpressionError):
        resolve_metric_expression(draft, metric)
