
from copy import deepcopy
from uuid import uuid4

import pytest
from dataset_binding import bind_datasets
from test_modeling import ONTOLOGY, ROOT, create_session, published_snapshot, save


def submit(client, draft, *, kind="object_type", target_id=None, session=None):
    session = session or client.get(ROOT + "/sessions/personal").json()
    bind_datasets(client, draft)
    body = save_body(client, session, draft, kind=kind,
                     target_id=target_id or draft["object_types"][0]["id"])
    return client.post(ROOT + f"/sessions/{session['id']}/element-saves", json=body)


def test_selected_aggregate_stays_in_session(client):
    session = create_session(client)
    session["draft"]["object_types"][1]["description"] = "其他未处理的草稿"
    session = save(client, session, session["draft"]).json()
    edited = deepcopy(session["draft"])
    edited["object_types"][0]["description"] = "保存当前元素"
    response = submit(client, edited, session=session)
    assert response.status_code == 200, response.text
    current = published_snapshot(client, ROOT)
    assert current["object_types"][0]["description"] != "保存当前元素"
    assert current["object_types"][1]["description"] != "其他未处理的草稿"
    updated = client.get(ROOT + f"/sessions/{session['id']}").json()
    assert updated["revision"] == session["revision"] + 1
    assert updated["draft"]["object_types"][1]["description"] == "其他未处理的草稿"


def test_stale_session_and_validation_failure_are_atomic(client):
    session = create_session(client)
    old = deepcopy(session)
    session["draft"]["object_types"][0]["description"] = "其他窗口"
    newer = save(client, session, session["draft"]).json()
    assert submit(client, old["draft"], session=old).status_code == 409
    invalid = deepcopy(newer["draft"])
    invalid["object_types"][0]["name"] = "bad name"
    assert submit(client, invalid, session=newer).status_code == 422
    assert client.get(ONTOLOGY + "/version").json()["version"] == 1
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == newer["revision"]
    )


def test_out_of_scope_changes_are_rejected(client):
    draft = published_snapshot(client, ROOT)
    draft["object_types"][1]["description"] = "额外修改"
    response = submit(client, draft)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"


def test_relation_description_preserves_readings_and_other_metadata(client):
    draft = published_snapshot(client, ROOT)
    original = deepcopy(draft)
    relation = draft["link_types"][0]
    relation["description"] = "统一描述"
    response = submit(client, draft, kind="link_type", target_id=relation["id"])
    assert response.status_code == 200, response.text
    expected = original["link_types"][0] | {"description": "统一描述"}
    assert response.json()["draft"]["link_types"][0] == expected
    assert response.json()["draft"]["rules"] == original["rules"]


def test_cannot_take_another_types_property_by_changing_owner(client):
    draft = published_snapshot(client, ROOT)
    selected = draft["object_types"][0]["id"]
    other = next(p for p in draft["properties"] if p["owner_type_id"] != selected)
    other["owner_type_id"] = selected
    response = submit(client, draft)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    assert client.get(ONTOLOGY + "/version").json()["version"] == 1


def test_preflight_rejects_unrelated_edits_and_stale_session(client):
    session = create_session(client)
    edited = deepcopy(session["draft"])
    edited["object_types"][1]["description"] = "越界修改"
    body = {
        "target_kind": "object_type",
        "target_id": edited["object_types"][0]["id"],
        "expected_session_revision": session["revision"],
        "draft": edited,
    }
    response = client.post(ROOT + f"/sessions/{session['id']}/element-saves/preview", json={k: v for k, v in body.items() if k != "idempotency_key"})
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    )
    newer = save(client, session, session["draft"]).json()
    assert newer["revision"] == session["revision"] + 1
    response = client.post(ROOT + f"/sessions/{session['id']}/element-saves/preview", json={k: v for k, v in body.items() if k != "idempotency_key"})
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "SESSION_REVISION_CHANGED"
    )


def test_dataset_preflight_lists_direct_and_ratio_impacts_with_server_hashes(client):
    from pr23_fixtures import example_session

    from ontofoundry_api.domain.canonical import element_sha256

    session = example_session(client, "13-dataset-metrics", published=True)
    candidate = deepcopy(session["draft"])
    dataset = candidate["datasets"][0]
    dataset["snapshot_date_column"] = "stat_date"
    response = client.post(
        ROOT + f"/sessions/{session['id']}/element-saves/preview",
        json={
            "target_kind": "dataset",
            "target_id": dataset["id"],
            "expected_session_revision": session["revision"],
            "draft": candidate,
        },
    )
    assert response.status_code == 200, response.text
    assert {
        i["target_id"]: i["expected_target_hash"] for i in response.json()["affected_items"]
    } == {
        m["id"]: element_sha256(m, collection="metrics")
        for m in session["draft"]["metrics"]
    }
    assert {i["target_kind"] for i in response.json()["affected_items"]} == {"metric"}


def save_body(client, session, candidate, *, kind="object_type", target_id):
    return {
        "target_kind": kind,
        "target_id": target_id,
        "expected_session_revision": session["revision"],
        "draft": candidate,
        "idempotency_key": str(uuid4()),
    }


def preflight_confirmations(client, session, body):
    response = client.post(ROOT + f"/sessions/{session['id']}/element-saves/preview", json={k: v for k, v in body.items() if k != "idempotency_key"})
    assert response.status_code == 200, response.text
    return [
        {k: v for k, v in item.items() if k != "reason"}
        for item in response.json()["affected_items"]
    ]


def test_dataset_save_requires_exact_confirmation_set_and_is_atomic(client):
    from pr23_fixtures import example_session

    session = example_session(client, "13-dataset-metrics", published=True)
    candidate = deepcopy(session["draft"])
    dataset = candidate["datasets"][0]
    dataset["snapshot_date_column"] = "stat_date"
    body = save_body(client, session, candidate, kind="dataset", target_id=dataset["id"])
    confirmations = preflight_confirmations(client, session, body)
    assert len(confirmations) == 6
    before_version = client.get(ONTOLOGY + "/version").json()
    before_session = client.get(ROOT + f"/sessions/{session['id']}").json()
    invalid_sets = [
        [],
        confirmations[:-1],
        [*confirmations, confirmations[0]],
        [*confirmations, {**confirmations[0], "target_id": dataset["id"]}],
        [{**confirmations[0], "target_kind": "dataset"}, *confirmations[1:]],
    ]
    for items in invalid_sets:
        response = client.post(
            ROOT + f"/sessions/{session['id']}/element-saves", json={**body, "affected_items": items}
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
        assert client.get(ONTOLOGY + "/version").json() == before_version
        assert client.get(ROOT + f"/sessions/{session['id']}").json() == before_session
    response = client.post(
        ROOT + f"/sessions/{session['id']}/element-saves",
        json={**body, "affected_items": list(reversed(confirmations))},
    )
    assert response.status_code == 200, response.text
    for raw in (response.json()["draft"],):
        assert (
            next(d for d in raw["datasets"] if d["id"] == dataset["id"])[
                "snapshot_date_column"
            ]
            == "stat_date"
        )
        assert raw["metrics"] == session["draft"]["metrics"]


def test_object_description_cannot_smuggle_dependent_relation_edit(client):
    from pr23_fixtures import example_session

    session = example_session(client, "07-instances-and-evidence", published=True)
    candidate = deepcopy(session["draft"])
    customer = next(o for o in candidate["object_types"] if o["name"] == "customer")
    customer["description"] = "客户说明修正"
    relation = next(
        r
        for r in candidate["link_types"]
        if customer["id"] in (r["source_type_id"], r["target_type_id"])
    )
    relation["description"] = "夹带的关系修改"
    body = save_body(client, session, candidate, target_id=customer["id"])
    for suffix in ("/preview", ""):
        response = client.post(ROOT + f"/sessions/{session['id']}/element-saves" + suffix, json={k: v for k, v in body.items() if suffix != "/preview" or k != "idempotency_key"})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    assert published_snapshot(client, ROOT) == session["draft"]
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == session["revision"]
    )


def rename_customer(client, session):
    candidate = deepcopy(session["draft"])
    prop = next(p for p in candidate["properties"] if p["name"] == "customer_no")
    prop["name"] = "customer_code"
    body = save_body(client, session, candidate, target_id=prop["owner_type_id"])
    confirmations = preflight_confirmations(client, session, body)
    assert confirmations == []
    response = client.post(
        ROOT + f"/sessions/{session['id']}/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    return response.json(), prop["owner_type_id"]


def test_second_save_after_rename_preflight_and_save_agree(client):
    from pr23_fixtures import example_session

    session = example_session(client, "07-instances-and-evidence", published=True)
    session, customer_id = rename_customer(client, session)
    candidate = deepcopy(session["draft"])
    next(o for o in candidate["object_types"] if o["id"] == customer_id)["description"] = (
        "改名后的第二次描述"
    )
    body = save_body(client, session, candidate, target_id=customer_id)
    before = client.get(ROOT + f"/sessions/{session['id']}").json()
    assert preflight_confirmations(client, session, body) == []
    assert client.get(ROOT + f"/sessions/{session['id']}").json() == before
    response = client.post(ROOT + f"/sessions/{session['id']}/element-saves", json=body)
    assert response.status_code == 200, response.text
    assert_customer_code_graphs(response.json(), customer_id)


@pytest.mark.parametrize("member_kind", ["property", "rule", "mapping"])
@pytest.mark.parametrize("direction", ["in", "out"])
def test_existing_members_cannot_cross_aggregate_boundaries(
    client, member_kind, direction
):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales", published=True)
    candidate = deepcopy(session["draft"])
    customer, order = candidate["object_types"]
    if member_kind == "property":
        member = next(p for p in candidate["properties"] if p["name"] == "region")
        source, destination = customer, order
        member["owner_type_id"] = destination["id"]
        candidate["mappings"][0]["fields"].pop("region")
    elif member_kind == "rule":
        member = candidate["rules"][0]
        source, destination = order, customer
        member.update(
            owner_kind="object_type", owner_id=destination["id"], expression="1 > 0"
        )
    else:
        member = candidate["mappings"][0]
        source, destination = customer, order
        member["type_id"] = destination["id"]
    target = destination if direction == "in" else source
    body = save_body(client, session, candidate, target_id=target["id"])
    before_session = client.get(ROOT + f"/sessions/{session['id']}").json()
    before_published = published_snapshot(client, ROOT)
    for suffix in ("/preview", ""):
        response = client.post(ROOT + f"/sessions/{session['id']}/element-saves" + suffix, json={k: v for k, v in body.items() if suffix != "/preview" or k != "idempotency_key"})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    assert published_snapshot(client, ROOT) == before_published
    assert client.get(ROOT + f"/sessions/{session['id']}").json() == before_session


def test_customer_property_can_be_deleted_without_moving_it(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales", published=True)
    candidate = deepcopy(session["draft"])
    prop = next(p for p in candidate["properties"] if p["name"] == "region")
    candidate["properties"].remove(prop)
    candidate["mappings"][0]["fields"].pop("region")
    body = save_body(client, session, candidate, target_id=prop["owner_type_id"])
    assert preflight_confirmations(client, session, body) == []
    response = client.post(ROOT + f"/sessions/{session['id']}/element-saves", json=body)
    assert response.status_code == 200, response.text
    for raw in (response.json()["draft"],):
        assert all(p["id"] != prop["id"] for p in raw["properties"])
        assert "region" not in raw["mappings"][0]["fields"]


@pytest.mark.parametrize("already_rewritten", [False, True])
def test_property_swap_keeps_bindings_by_uuid_for_both_candidate_forms(
    client, already_rewritten
):
    from pr23_fixtures import example_session

    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.dependencies import rewrite_references
    from ontofoundry_api.services.element_save import calculate_element_save

    session = example_session(client, "01-basic-sales", published=True)
    original = session["draft"]
    candidate = deepcopy(original)
    customer_id = candidate["object_types"][0]["id"]
    props = [p for p in candidate["properties"] if p["owner_type_id"] == customer_id]
    first, second = props[:2]
    first["name"], second["name"] = (
        second["name"],
        first["name"],
    )
    final = rewrite_references(
        CoreDraft.model_validate(original), CoreDraft.model_validate(candidate)
    ).model_dump(mode="json")
    before_inputs = deepcopy((original, candidate, final))
    unrewritten = calculate_element_save(
        original, candidate, "object_type", customer_id
    )
    rewritten = calculate_element_save(
        original, final, "object_type", customer_id
    )
    assert unrewritten == rewritten
    assert (original, candidate, final) == before_inputs
    body = save_body(
        client, session, final if already_rewritten else candidate, target_id=customer_id
    )
    assert preflight_confirmations(client, session, body) == []
    response = client.post(ROOT + f"/sessions/{session['id']}/element-saves", json=body)
    assert response.status_code == 200, response.text
    original_fields = original["mappings"][0]["fields"]
    bindings_by_uuid = {
        p["id"]: original_fields[p["name"]]
        for p in original["properties"]
        if p["owner_type_id"] == customer_id
    }
    for raw in (response.json()["draft"],):
        mapping = next(m for m in raw["mappings"] if m["type_id"] == customer_id)
        assert {
            p["id"]: mapping["fields"][p["name"]]
            for p in raw["properties"]
            if p["owner_type_id"] == customer_id
        } == bindings_by_uuid


@pytest.mark.parametrize("defect", ["duplicate", "missing", "extra", "kind", "hash"])
def test_confirmation_error_priority_is_independent_of_order(client, defect):
    from itertools import permutations

    from pr23_fixtures import example_session

    session = example_session(client, "13-dataset-metrics", published=True)
    candidate = deepcopy(session["draft"])
    candidate["datasets"][0]["snapshot_date_column"] = "stat_date"
    body = save_body(
        client, session, candidate, kind="dataset", target_id=candidate["datasets"][0]["id"]
    )
    confirmations = preflight_confirmations(client, session, body)
    bad_hash = {**confirmations[0], "expected_target_hash": "0" * 64}
    rest = confirmations[1:]
    if defect == "duplicate":
        tail = [confirmations[0]]
    elif defect == "missing":
        rest = rest[:-1]
        tail = []
    elif defect == "extra":
        tail = [{**confirmations[0], "target_id": candidate["datasets"][0]["id"]}]
    elif defect == "kind":
        tail = [{**rest.pop(), "target_kind": "dataset"}]
    else:
        tail = []
    # Move the stale hash before/after every structural defect and valid entry.
    groups = [[bad_hash], rest, tail]
    before_version = client.get(ONTOLOGY + "/version").json()
    before_session = client.get(ROOT + f"/sessions/{session['id']}").json()
    for order in permutations(groups):
        items = [item for group in order for item in group]
        response = client.post(
            ROOT + f"/sessions/{session['id']}/element-saves", json={**body, "affected_items": items}
        )
        assert response.status_code == (409 if defect == "hash" else 422), response.text
        assert response.json()["error"]["code"] == (
            "PREVIEW_OUTDATED" if defect == "hash" else "ELEMENT_SCOPE_INVALID"
        )
        assert client.get(ONTOLOGY + "/version").json() == before_version
        assert client.get(ROOT + f"/sessions/{session['id']}").json() == before_session


@pytest.mark.parametrize("column", ["vip_note", "party_name"])
def test_example06_shared_parent_note_rename_keeps_column_binding(client, column):
    from pr23_fixtures import example_session

    from ontofoundry_api.domain.bindings import binding_readiness, resolve_binding
    from ontofoundry_api.domain.core import CoreDraft

    session = example_session(client, "06-inheritance", published=True)
    candidate = deepcopy(session["draft"])
    vip = next(o for o in candidate["object_types"] if o["name"] == "vip_party")
    next(p for p in candidate["properties"] if p["owner_type_id"] == vip["id"])["name"] = (
        "note2"
    )
    mapping = next(m for m in candidate["mappings"] if m["type_id"] == vip["id"])
    assert mapping["sources"] == []
    mapping["fields"] = {"note2": {"kind": "column", "source_id": "main", "column": column}}
    body = save_body(client, session, candidate, target_id=vip["id"])
    assert preflight_confirmations(client, session, body) == []
    response = client.post(ROOT + f"/sessions/{session['id']}/element-saves", json=body)
    assert response.status_code == 200, response.text
    for raw in (response.json()["draft"],):
        graph = CoreDraft.model_validate(raw)
        obj = next(o for o in graph.object_types if str(o.id) == vip["id"])
        binding = resolve_binding(graph, obj.id)
        assert binding.fields["note2"].model_dump(mode="json") == mapping["fields"]["note2"]
        assert "note" not in binding.fields
        assert binding_readiness(graph, obj.id).status == "bound"


def assert_customer_code_graphs(result, customer_id):
    from ontofoundry_api.domain.models import OntologyDraft
    for raw in (result["draft"],):
        model = OntologyDraft.model_validate(raw)
        customer = next(o for o in model.object_types if str(o.id) == customer_id)
        assert customer.description == "改名后的第二次描述"
        assert "customer_code" in {p.name for p in model.properties if p.owner_type_id == customer.id}
        assert "material_objects" not in raw
