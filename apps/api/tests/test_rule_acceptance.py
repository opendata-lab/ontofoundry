"""AC-07 through the decision endpoint: violations refuse the accept; unchecked rules warn."""

from uuid import uuid4

from test_instance_store import create_instance
from test_modeling import create_session, save
from test_t4_proposal_decisions import create, decide, seed_batch


def with_rules(client, session, *rules):
    draft = session["draft"]
    types = {o["name"]: o["id"] for o in draft["object_types"]}
    for name, label, owner_kind, owner, expression in rules:
        draft["rules"].append({"id": str(uuid4()), "name": name, "display_name": label, "owner_kind": owner_kind,
                               "owner_id": types.get(owner, owner), "rule_kind": "constraint",
                               "expression": expression, "evidence": []})
    saved = save(client, session, draft)
    assert saved.status_code == 200, saved.text
    return saved.json()


def accept(client, session, item):
    batch = seed_batch(client, session, [item])
    return decide(client, session, [(batch["items"][0]["id"], "accept")])


def test_a_value_that_breaks_a_rule_is_refused_with_property_rule_and_value(client):
    session = with_rules(client, create_session(client),
                         ("no_test_customer", "不收测试客户", "object_type", "customer", "customer.label <> '测试客户'"))
    refused = accept(client, session, create_instance(session, "测试客户"))
    assert refused.status_code == 422, refused.text
    message = refused.json()["error"]["message"]
    assert "label" in message and "'测试客户'" in message and "不收测试客户" in message
    assert accept(client, session, create_instance(session, "月湾客户")).status_code == 200


def test_rules_that_reach_another_object_are_reported_not_blocking(client):
    session = create_session(client)
    buyer = next(link for link in session["draft"]["link_types"] if link["name"] == "buyer")
    session = with_rules(
        client, session,
        ("buyer_named", "买方有名称", "object_type", "order", "order.buyer.label IS NOT NULL"),
        ("buyer_rule", "买方关系规则", "link_type", buyer["id"], "order.order_no IS NOT NULL"),
    )
    order = next(o for o in session["draft"]["object_types"] if o["name"] == "order")
    accepted = accept(client, session, create(
        "order-" + uuid4().hex[:6], "material_object", {"type_id": order["id"], "values": {"order_no": "O-001"}, "evidence": []}))
    assert accepted.status_code == 200, accepted.text
    warnings = [w for w in accepted.json()["validation"]["warnings"] if w.get("code") == "RULE_NOT_CHECKED"]
    assert {w["message"] for w in warnings} == {
        "规则未检查：买方有名称（buyer_named），涉及其他对象",
        "规则未检查：买方关系规则（buyer_rule），涉及其他对象",
    }
