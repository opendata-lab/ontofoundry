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


def test_a_rule_that_only_says_required_is_refused_at_proposal(client):
    """Found in the AC verification: the agent moved required into `x IS NOT NULL`, which never blocks."""
    from test_pending_merge import run_on_top_of_pending
    from test_t1_proposal_contract import items_only

    session = create_session(client)
    order = next(o for o in session["draft"]["object_types"] if o["name"] == "order")
    rule = create("order_no_required", "rule", {
        "name": "order_no_required", "display_name": "订单号必填", "owner_kind": "object_type",
        "owner_id": order["id"], "rule_kind": "constraint", "expression": "order.order_no IS NOT NULL"})
    _, _, url, headers = run_on_top_of_pending(client, session)
    response = client.post(url, json={"items": items_only([rule])}, headers=headers)
    assert response.status_code == 200 and not response.json()["passed"], response.text
    assert "是否必填在属性上设置" in response.text and "订单号必填" in response.text


def test_accept_all_accepts_what_passes_and_lists_the_rest(client):
    import uuid as _uuid

    from test_modeling import ROOT

    session = with_rules(client, create_session(client),
                         ("no_test_customer", "不收测试客户", "object_type", "customer", "customer.label <> '测试客户'"))
    order = next(o for o in session["draft"]["object_types"] if o["name"] == "order")
    buyer = next(link for link in session["draft"]["link_types"] if link["name"] == "buyer")
    good, bad = create_instance(session, "月湾客户"), create_instance(session, "测试客户")
    order_item = create("order-1", "material_object", {"type_id": order["id"], "values": {"order_no": "O-1"}, "evidence": []})
    link = create("buyer-1", "material_link", {"type_id": buyer["id"], "source_id": {"client_ref": "order-1"},
                                               "target_id": {"client_ref": bad["client_ref"]}, "evidence": []})
    batch = seed_batch(client, session, [good, bad, order_item, link])
    ids = {i["client_ref"]: i["id"] for i in batch["items"]}
    decisions = [{"proposal_id": i, "decision": "accept"} for i in ids.values()]

    def post(partial):
        current = client.get(ROOT + f"/sessions/{session['id']}").json()
        return client.post(ROOT + f"/sessions/{session['id']}/proposal-decisions", json={
            "idempotency_key": str(_uuid.uuid4()), "expected_session_revision": current["revision"],
            "decisions": decisions, **({"partial": True} if partial else {})})

    assert post(False).status_code == 422  # one by one or all at once: still all or nothing
    response = post(True)
    assert response.status_code == 200, response.text
    results = {r["proposal_id"]: r for r in response.json()["results"]}
    assert results[ids[good["client_ref"]]]["status"] == "accepted"
    assert results[ids["order-1"]]["status"] == "accepted"
    refused = results[ids[bad["client_ref"]]]
    assert refused["status"] == "pending" and "不收测试客户" in refused["reason"]
    assert results[ids["buyer-1"]]["status"] == "pending" and "未通过" in results[ids["buyer-1"]]["reason"]
