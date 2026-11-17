"""AC-07: constraint rules are evaluated on accepted instances, within an allow-list."""

from decimal import Decimal
from uuid import uuid4

import pytest
import sqlglot
from core1_fixtures import example_draft_json

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.rule_evaluation import (
    Unsupported,
    check_instance_rules,
    evaluate,
)


def draft_with(*rules, value_type=None):
    draft = example_draft_json("01-basic-sales")
    order = next(o for o in draft["object_types"] if o["name"] == "sales_order")
    status = next(p for p in draft["properties"] if p["name"] == "status")
    if value_type:
        draft["value_types"].append({"id": value_type["id"], "name": "order_status", "display_name": "订单状态值",
                                     "value_kind": "string", "evidence": []})
        status["value_type_id"] = value_type["id"]
    for owner_kind, owner_id, expression, kind in rules:
        draft["rules"].append({"id": str(uuid4()), "name": f"rule_{len(draft['rules'])}", "owner_kind": owner_kind,
                               "owner_id": owner_id, "rule_kind": kind, "expression": expression, "evidence": []})
    return OntologyDraft.model_validate(draft), order["id"]


def outcomes(model, type_id, values):
    return {o.rule.name: (o.passed, o.reason) for o in check_instance_rules(model, type_id, values)}


ORDER = {"order_no": "SO-1", "amount": 120, "status": "已支付"}


def test_single_object_rules_pass_and_fail_with_exact_decimals():
    model, order = draft_with()
    assert outcomes(model, order, ORDER) == {"positive": (True, ""), "status_values": (True, "")}
    found = outcomes(model, order, {**ORDER, "amount": -0.01, "status": "钻石"})
    assert found == {"positive": (False, ""), "status_values": (False, "")}


def test_missing_values_are_not_evaluated():
    model, order = draft_with()
    assert outcomes(model, order, {"order_no": "SO-1", "status": "  "}) == {}


def test_value_type_rules_hold_for_each_property_that_uses_them():
    vt = {"id": str(uuid4())}
    model, order = draft_with(("value_type", vt["id"], "order_status IN ('已支付', '已完成')", "constraint"), value_type=vt)
    assert outcomes(model, order, ORDER)["rule_2"] == (True, "")
    assert outcomes(model, order, {**ORDER, "status": "待支付"})["rule_2"] == (False, "")


def test_rules_that_reach_another_object_are_not_checked():
    model, order = draft_with()
    customer_link = model.link_types[0].id
    model, order = draft_with(
        ("object_type", order, "sales_order.customer.region IS NOT NULL", "constraint"),
        ("link_type", str(customer_link), "sales_order.amount > 0", "constraint"),
    )
    found = outcomes(model, order, ORDER)
    assert found["rule_2"] == (None, "涉及其他对象")
    assert found["rule_3"] == (None, "涉及其他对象")


@pytest.fixture
def order_rules():
    def build(*expressions, kind="constraint"):
        draft = example_draft_json("01-basic-sales")
        order = next(o for o in draft["object_types"] if o["name"] == "sales_order")
        for n, expression in enumerate(expressions):
            draft["rules"].append({"id": str(uuid4()), "name": f"extra_{n}", "owner_kind": "object_type",
                                   "owner_id": order["id"], "rule_kind": kind, "expression": expression, "evidence": []})
        return OntologyDraft.model_validate(draft), order["id"]
    return build


def test_derivations_are_skipped(order_rules):
    model, order = order_rules("sales_order.amount > 1000", kind="derivation")
    assert "extra_0" not in outcomes(model, order, ORDER)


@pytest.mark.parametrize("expression, expected", [
    ("sales_order.amount BETWEEN 100 AND 200", True),
    ("sales_order.amount * 2 - 40 = 200", True),
    ("sales_order.amount / 3 > 39.99", True),
    ("sales_order.order_no LIKE 'SO-_'", True),
    ("REGEXP_LIKE(sales_order.order_no, '^SO-[0-9]+$')", True),
    ("LENGTH(TRIM(sales_order.order_no)) = 4 AND UPPER(sales_order.order_no) = 'SO-1'", True),
    ("NOT (sales_order.status = '已支付' OR sales_order.amount < 0)", False),
    ("sales_order.status IS NOT NULL", True),
    ("sales_order.status IS NULL", False),
])
def test_allow_listed_syntax_is_evaluated(order_rules, expression, expected):
    model, order = order_rules(expression)
    assert outcomes(model, order, ORDER)["extra_0"] == (expected, "")


@pytest.mark.parametrize("expression", [
    "ROUND(sales_order.amount) > 0",
    "COALESCE(sales_order.status, 'x') = 'x'",
    "sales_order.amount > '100'",
    "sales_order.amount / 0 > 1",
])
def test_anything_else_is_reported_not_checked(order_rules, expression):
    model, order = order_rules(expression)
    passed, reason = outcomes(model, order, ORDER)["extra_0"]
    assert passed is None and reason.startswith("用到暂不支持的写法")


def test_arithmetic_is_exact():
    assert evaluate(sqlglot.parse_one("0.1 + 0.2 = 0.3"), lambda _: None) is True
    assert evaluate(sqlglot.parse_one("1 / 3"), lambda _: None) == Decimal(1) / Decimal(3)
    with pytest.raises(Unsupported):
        evaluate(sqlglot.parse_one("TRY_CAST('abc' AS INT) IS NOT NULL"), lambda _: None)


def test_is_not_null_on_an_empty_value_is_not_evaluated(order_rules):
    model, order = order_rules("sales_order.status IS NOT NULL")
    assert "extra_0" not in outcomes(model, order, {**ORDER, "status": None})


@pytest.mark.parametrize("expression, names", [
    ("sales_order.status IS NOT NULL", ["status"]),
    ("(sales_order.status IS NOT NULL) AND sales_order.amount IS NOT NULL", ["status", "amount"]),
    ("sales_order.status IS NOT NULL AND sales_order.amount > 0", []),
    ("sales_order.customer.region IS NOT NULL", []),
    ("sales_order.status IS NULL", []),
])
def test_rules_that_only_say_required_are_found(order_rules, expression, names):
    from ontofoundry_api.domain.rule_evaluation import only_says_required

    model, _ = order_rules(expression)
    rule = next(r for r in model.rules if r.name == "extra_0")
    assert [n.split("（")[-1].rstrip("）") if "（" in n else n for n in only_says_required(model, rule)] == names
