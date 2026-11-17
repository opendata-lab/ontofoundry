"""Accepted document instances state numbers as numbers and datetimes with a time.

Proposals and reads stay lenient: an agent may propose "42" and fix it in the
session, and instances stored before this rule are not hidden."""

from uuid import uuid4

import pytest
from test_instance_store import accept_all
from test_modeling import ONTOLOGY, create_session, publish, save
from test_t4_proposal_decisions import create, decide, seed_batch

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.instance_validation import value_issues
from ontofoundry_api.domain.instances import check_accepted_values, validate_instances
from ontofoundry_api.domain.snapshot import empty_snapshot


def member_draft():
    data = empty_snapshot(str(uuid4()))
    type_id = str(uuid4())
    data["object_types"].append({"id": type_id, "name": "member"})
    data["properties"] += [
        {"id": str(uuid4()), "owner_type_id": type_id, "name": "member_no",
         "display_name": "会员号", "value_kind": "integer", "identifier": True, "unique": True},
        {"id": str(uuid4()), "owner_type_id": type_id, "name": "balance",
         "display_name": "余额", "value_kind": "decimal"},
        {"id": str(uuid4()), "owner_type_id": type_id, "name": "joined_at",
         "display_name": "入会时间", "value_kind": "datetime"},
    ]
    return CoreDraft.model_validate(data), type_id


def instance(type_id, **values):
    return {"id": str(uuid4()), "type_id": type_id, "values": values}


@pytest.mark.parametrize("values", [
    {"member_no": 42, "balance": 12.5, "joined_at": "2026-01-20 10:12"},
    {"member_no": -3, "balance": 7, "joined_at": "2026-01-20T10:12:00+08:00"},
])
def test_numbers_are_accepted(values):
    draft, type_id = member_draft()
    model = validate_instances(draft, [instance(type_id, **values)], [])
    check_accepted_values(model, [instance(type_id, **values)])


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"member_no": "42"}, "会员号（member_no）必须是整数，不能写成文本 '42'"),
        ({"member_no": 42.0}, "会员号（member_no）必须是整数"),
        ({"member_no": True}, "会员号（member_no）必须是整数"),
        ({"balance": "12.50"}, "余额（balance）必须是数字，不能写成文本 '12.50'"),
        ({"joined_at": "2026-01-20"}, "入会时间（joined_at）必须是日期时间，缺少时间：'2026-01-20'"),
        ({"joined_at": "2026/01/20 10:12"}, "入会时间（joined_at）必须是日期时间"),
    ],
)
def test_numbers_written_as_text_are_rejected_with_the_property_named(values, message):
    draft, type_id = member_draft()
    model = validate_instances(draft, [], [])
    with pytest.raises(ValueError) as error:
        check_accepted_values(model, [instance(type_id, **values)])
    assert str(error.value).startswith("member「") and str(error.value).endswith("：" + message)


def test_every_wrong_property_is_reported():
    draft, type_id = member_draft()
    model = validate_instances(draft, [], [])
    with pytest.raises(ValueError, match="会员号.*；member「42」：余额"):
        check_accepted_values(model, [instance(type_id, member_no="42", balance="1.5")])


def test_text_numbers_still_pass_the_shared_check_used_by_proposals_and_reads():
    draft, type_id = member_draft()
    validate_instances(draft, [instance(type_id, member_no="42", balance="12.50", joined_at="2026-01-20")], [])


def test_database_reads_still_accept_decimals_carried_as_text():
    draft, type_id = member_draft()
    model = validate_instances(draft, [], [])
    assert value_issues(model, type_id, {"member_no": "42", "balance": "12.50"}, "row") == []


def test_a_proposal_may_say_text_but_accepting_needs_a_number(client):
    session = create_session(client)
    customer = next(o for o in session["draft"]["object_types"] if o["name"] == "customer")
    session["draft"]["properties"].append({"id": str(uuid4()), "owner_type_id": customer["id"],
                                           "name": "visits", "display_name": "到店次数", "value_kind": "integer"})
    session = publish(client, save(client, session, session["draft"]).json()).json()["session"]

    def fact(visits):
        return create("c-" + uuid4().hex[:6], "material_object",
                      {"type_id": customer["id"], "values": {"label": "月湾客户", "visits": visits}, "evidence": []})

    batch = seed_batch(client, session, [fact("42")])  # the proposal itself is fine
    response = decide(client, session, [(batch["items"][0]["id"], "accept")])
    assert response.status_code >= 400
    assert "到店次数（visits）必须是整数，不能写成文本 '42'" in response.text

    rejected = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert rejected.status_code == 200, rejected.text
    session, _ = accept_all(client, rejected.json()["session"], [fact(42)])
    published = publish(client, session)
    assert published.status_code == 200, published.text
    values = [o["values"].get("visits") for o in client.get(ONTOLOGY + "/objects").json()["items"]]
    assert 42 in values


def test_each_error_names_its_instance():
    draft, type_id = member_draft()
    model = validate_instances(draft, [], [])
    first, second = instance(type_id, member_no=1, balance="9.9"), instance(type_id, member_no=2, balance="9.9")
    with pytest.raises(ValueError) as error:
        check_accepted_values(model, [first, second])
    assert str(error.value) == (
        "member「1」：余额（balance）必须是数字，不能写成文本 '9.9'；"
        "member「2」：余额（balance）必须是数字，不能写成文本 '9.9'"
    )


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_optional_value_is_missing_not_a_type_error(blank):
    draft, type_id = member_draft()
    model = validate_instances(draft, [instance(type_id, member_no=1, balance=blank, joined_at=blank)], [])
    check_accepted_values(model, [instance(type_id, member_no=1, balance=blank, joined_at=blank)])
