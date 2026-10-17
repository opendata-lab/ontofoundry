from copy import deepcopy

import pytest
from test_modeling import ONTOLOGY, ROOT, create_session, save


def submit(
    client, draft, *, kind="object_type", target_id=None, session=None, version=None
):
    return client.post(
        ROOT + "/element-saves",
        json={
            "target_kind": kind,
            "target_id": target_id or draft["object_types"][0]["id"],
            "expected_current_version_id": version
            or client.get(ONTOLOGY + "/version").json()["version_id"],
            "session_id": session["id"] if session else None,
            "expected_session_revision": session["revision"] if session else None,
            "draft": draft,
        },
    )


def test_save_immediately_creates_version_and_preserves_history(client):
    old = client.get(ONTOLOGY + "/version").json()
    draft = client.get(ROOT + "/published-snapshot").json()
    draft["object_types"][0]["description"] = "当前弹窗修改"
    response = submit(client, draft)
    assert response.status_code == 200, response.text
    assert response.json()["version"]["version"] == 2
    assert client.get(ROOT + "/published-snapshot").json() == response.json()["draft"]
    historical = client.get(ROOT + f"/versions/{old['version_id']}/presentation").json()[
        "model"
    ]
    assert historical["object_types"][0]["description"] != "当前弹窗修改"


def test_only_selected_aggregate_is_committed_from_session(client):
    session = create_session(client)
    session["draft"]["object_types"][1]["description"] = "其他未处理的草稿"
    session = save(client, session, session["draft"]).json()
    edited = deepcopy(session["draft"])
    edited["object_types"][0]["description"] = "保存当前元素"
    response = submit(client, edited, session=session)
    assert response.status_code == 200, response.text
    current = client.get(ROOT + "/published-snapshot").json()
    assert current["object_types"][0]["description"] == "保存当前元素"
    assert current["object_types"][1]["description"] != "其他未处理的草稿"
    updated = client.get(ROOT + f"/sessions/{session['id']}").json()
    assert updated["revision"] == session["revision"] + 1
    assert updated["draft"]["object_types"][1]["description"] == "其他未处理的草稿"


def test_stale_version_refuses_overwrite(client):
    version = client.get(ONTOLOGY + "/version").json()["version_id"]
    draft = client.get(ROOT + "/published-snapshot").json()
    draft["object_types"][0]["description"] = "第一次"
    assert submit(client, draft).status_code == 200
    draft["object_types"][0]["description"] = "旧窗口"
    response = submit(client, draft, version=version)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_CHANGED"
    assert (
        client.get(ROOT + "/published-snapshot").json()["object_types"][0]["description"]
        == "第一次"
    )


def test_stale_session_and_validation_failure_are_atomic(client):
    session = create_session(client)
    old = deepcopy(session)
    session["draft"]["object_types"][0]["description"] = "其他窗口"
    newer = save(client, session, session["draft"]).json()
    assert submit(client, old["draft"], session=old).status_code == 409
    invalid = deepcopy(newer["draft"])
    invalid["object_types"][0]["technical_name"] = "bad name"
    assert submit(client, invalid, session=newer).status_code == 422
    assert client.get(ONTOLOGY + "/version").json()["version"] == 1
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == newer["revision"]
    )


def test_out_of_scope_changes_are_rejected(client):
    draft = client.get(ROOT + "/published-snapshot").json()
    draft["object_types"][1]["description"] = "额外修改"
    response = submit(client, draft)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"


def test_relation_description_preserves_readings_and_other_metadata(client):
    draft = client.get(ROOT + "/published-snapshot").json()
    original = deepcopy(draft)
    relation = draft["link_types"][0]
    relation["description"] = "统一描述"
    response = submit(client, draft, kind="link_type", target_id=relation["id"])
    assert response.status_code == 200, response.text
    expected = original["link_types"][0] | {"description": "统一描述"}
    assert response.json()["draft"]["link_types"][0] == expected
    assert response.json()["draft"]["rules"] == original["rules"]


def test_selected_session_conflict_does_not_commit(client):
    session = create_session(client)
    session["draft"]["object_types"][0]["description"] = "旧草稿修改"
    session = save(client, session, session["draft"]).json()
    latest = client.get(ROOT + "/published-snapshot").json()
    latest["object_types"][0]["description"] = "另一个窗口保存"
    assert submit(client, latest).status_code == 200
    response = submit(client, session["draft"], session=session)
    assert response.status_code == 409
    assert client.get(ONTOLOGY + "/version").json()["version"] == 2
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == session["revision"]
    )


def test_cannot_take_another_types_property_by_changing_owner(client):
    draft = client.get(ROOT + "/published-snapshot").json()
    selected = draft["object_types"][0]["id"]
    other = next(p for p in draft["properties"] if p["owner_type_id"] != selected)
    other["owner_type_id"] = selected
    response = submit(client, draft)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    assert client.get(ONTOLOGY + "/version").json()["version"] == 1


def test_saved_session_displays_latest_merged_values_of_selected_element(client):
    session = create_session(client)
    session["draft"]["object_types"][0]["description"] = "会话中的描述"
    session = save(client, session, session["draft"]).json()
    current = client.get(ROOT + "/published-snapshot").json()
    current["object_types"][0]["name"] = "新的供应商名称"
    assert submit(client, current).status_code == 200
    response = submit(client, session["draft"], session=session)
    assert response.status_code == 200, response.text
    published = response.json()["draft"]["object_types"][0]
    assert published["name"] == "新的供应商名称"
    assert published["description"] == "会话中的描述"
    assert response.json()["session"]["draft"]["object_types"][0] == published


def test_example07_rename_preflight_hashes_and_synchronizes_session(client):
    from pr23_fixtures import example_session
    from test_modeling import preview

    from ontofoundry_api.domain.canonical import element_sha256
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.validation import validate_core_graph

    session = example_session(client, "07-instances-and-evidence", published=True)
    session["draft"]["object_types"][1]["description"] = "不相关的会话修改"
    session = save(client, session, session["draft"]).json()
    edited = deepcopy(session["draft"])
    prop = next(p for p in edited["properties"] if p["technical_name"] == "customer_no")
    prop["technical_name"] = "customer_code"
    body = {
        "target_kind": "object_type",
        "target_id": prop["owner_type_id"],
        "expected_current_version_id": client.get(ONTOLOGY + "/version").json()[
            "version_id"
        ],
        "session_id": session["id"],
        "expected_session_revision": session["revision"],
        "draft": edited,
    }
    before = client.get(ROOT + f"/sessions/{session['id']}").json()
    response = client.post(ROOT + "/element-saves/preview", json=body)
    assert response.status_code == 200, response.text
    impact = response.json()
    fact = next(
        f for f in session["draft"]["material_objects"] if "customer_no" in f["values"]
    )
    assert impact["affected_items"] == [
        {
            "target_kind": "material_object",
            "target_id": fact["id"],
            "expected_target_hash": element_sha256(fact, collection="material_objects"),
            "reason": "当前元素修改需要同步此依赖的定义或引用",
        }
    ]
    assert impact["current_version_id"] == body["expected_current_version_id"]
    assert impact["session_revision"] == session["revision"]
    assert client.get(ROOT + f"/sessions/{session['id']}").json() == before
    confirmations = [
        {k: v for k, v in entry.items() if k != "reason"}
        for entry in impact["affected_items"]
    ]
    # The endpoint does not silently approve the returned dependencies.
    refused = client.post(ROOT + "/element-saves", json=body)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    stale = client.post(
        ROOT + "/element-saves",
        json={
            **body,
            "affected_items": [{**confirmations[0], "expected_target_hash": "0" * 64}],
        },
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CHANGED"
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    for raw in (result["draft"], result["session"]["draft"]):
        validate_core_graph(CoreDraft.model_validate(raw))
        updated = next(f for f in raw["material_objects"] if f["id"] == fact["id"])
        assert updated["values"]["customer_code"] == "C001"
        assert "customer_no" not in updated["values"]
    assert result["draft"]["object_types"][1]["description"] != "不相关的会话修改"
    assert (
        result["session"]["draft"]["object_types"][1]["description"] == "不相关的会话修改"
    )
    assert preview(client, result["session"]).json()["validation"]["publishable"]
    outdated = client.post(ROOT + "/element-saves/preview", json=body)
    assert (
        outdated.status_code == 409
        and outdated.json()["error"]["code"] == "VERSION_CHANGED"
    )


def test_preflight_rejects_unrelated_edits_and_stale_session(client):
    session = create_session(client)
    edited = deepcopy(session["draft"])
    edited["object_types"][1]["description"] = "越界修改"
    body = {
        "target_kind": "object_type",
        "target_id": edited["object_types"][0]["id"],
        "expected_current_version_id": session["base_version_id"],
        "session_id": session["id"],
        "expected_session_revision": session["revision"],
        "draft": edited,
    }
    response = client.post(ROOT + "/element-saves/preview", json=body)
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    )
    newer = save(client, session, session["draft"]).json()
    assert newer["revision"] == session["revision"] + 1
    response = client.post(ROOT + "/element-saves/preview", json=body)
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
        ROOT + "/element-saves/preview",
        json={
            "target_kind": "dataset",
            "target_id": dataset["id"],
            "expected_current_version_id": session["base_version_id"],
            "session_id": session["id"],
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
        "expected_current_version_id": client.get(ONTOLOGY + "/version").json()[
            "version_id"
        ],
        "session_id": session["id"],
        "expected_session_revision": session["revision"],
        "draft": candidate,
    }


def preflight_confirmations(client, body):
    response = client.post(ROOT + "/element-saves/preview", json=body)
    assert response.status_code == 200, response.text
    return [
        {k: v for k, v in item.items() if k != "reason"}
        for item in response.json()["affected_items"]
    ]


@pytest.mark.parametrize("staged", [False, True])
def test_dataset_save_requires_exact_confirmation_set_and_is_atomic(client, staged):
    from pr23_fixtures import example_session

    session = example_session(client, "13-dataset-metrics", published=True)
    candidate = deepcopy(session["draft"])
    dataset = candidate["datasets"][0]
    dataset["snapshot_date_column"] = "stat_date"
    if staged:
        response = save(client, session, candidate)
        assert response.status_code == 200, response.text
        session = response.json()
    body = save_body(client, session, candidate, kind="dataset", target_id=dataset["id"])
    confirmations = preflight_confirmations(client, body)
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
            ROOT + "/element-saves", json={**body, "affected_items": items}
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
        assert client.get(ONTOLOGY + "/version").json() == before_version
        assert client.get(ROOT + f"/sessions/{session['id']}").json() == before_session
    response = client.post(
        ROOT + "/element-saves",
        json={**body, "affected_items": list(reversed(confirmations))},
    )
    assert response.status_code == 200, response.text
    for raw in (response.json()["draft"], response.json()["session"]["draft"]):
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
    customer = next(
        o for o in candidate["object_types"] if o["technical_name"] == "customer"
    )
    customer["description"] = "客户说明修正"
    relation = next(
        r
        for r in candidate["link_types"]
        if customer["id"] in (r["source_type_id"], r["target_type_id"])
    )
    relation["description"] = "夹带的关系修改"
    body = save_body(client, session, candidate, target_id=customer["id"])
    for suffix in ("/preview", ""):
        response = client.post(ROOT + "/element-saves" + suffix, json=body)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    assert client.get(ROOT + "/published-snapshot").json() == session["draft"]
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == session["revision"]
    )


def rename_customer(client, session):
    candidate = deepcopy(session["draft"])
    prop = next(p for p in candidate["properties"] if p["technical_name"] == "customer_no")
    prop["technical_name"] = "customer_code"
    body = save_body(client, session, candidate, target_id=prop["owner_type_id"])
    confirmations = preflight_confirmations(client, body)
    assert len(confirmations) == 1
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    return response.json()["session"], prop["owner_type_id"]


def assert_customer_code_graphs(result, customer_id):
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.validation import validate_core_graph

    for raw in (result["draft"], result["session"]["draft"]):
        validate_core_graph(CoreDraft.model_validate(raw))
        fact = next(f for f in raw["material_objects"] if f["type_id"] == customer_id)
        assert fact["values"]["customer_code"] == "C001"
        assert "customer_no" not in fact["values"]
        customer = next(o for o in raw["object_types"] if o["id"] == customer_id)
        assert customer["description"] == "改名后的第二次描述"


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
    assert preflight_confirmations(client, body) == []
    assert client.get(ROOT + f"/sessions/{session['id']}").json() == before
    response = client.post(ROOT + "/element-saves", json=body)
    assert response.status_code == 200, response.text
    assert_customer_code_graphs(response.json(), customer_id)


def test_old_session_synchronizes_latest_rename_and_keeps_unrelated_edits(client):
    from pr23_fixtures import example_session
    from test_modeling import preview

    session = example_session(client, "07-instances-and-evidence", published=True)
    old_session = create_session(client)
    _, customer_id = rename_customer(client, session)
    other = next(o for o in old_session["draft"]["object_types"] if o["id"] != customer_id)
    other["description"] = "保留的其他会话修改"
    old_session = save(client, old_session, old_session["draft"]).json()
    candidate = deepcopy(old_session["draft"])
    next(o for o in candidate["object_types"] if o["id"] == customer_id)["description"] = (
        "改名后的第二次描述"
    )
    body = save_body(client, old_session, candidate, target_id=customer_id)
    before = client.get(ROOT + f"/sessions/{old_session['id']}").json()
    confirmations = preflight_confirmations(client, body)
    assert len(confirmations) == 1
    assert confirmations[0]["target_kind"] == "material_object"
    assert client.get(ROOT + f"/sessions/{old_session['id']}").json() == before
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert_customer_code_graphs(result, customer_id)
    assert (
        next(
            o for o in result["session"]["draft"]["object_types"] if o["id"] == other["id"]
        )["description"]
        == "保留的其他会话修改"
    )
    assert (
        next(o for o in result["draft"]["object_types"] if o["id"] == other["id"])[
            "description"
        ]
        != "保留的其他会话修改"
    )
    assert preview(client, result["session"]).json()["validation"]["publishable"]


def test_necessary_fact_rename_does_not_authorize_other_fact_values(client):
    from pr23_fixtures import example_session

    session = example_session(client, "07-instances-and-evidence", published=True)
    candidate = deepcopy(session["draft"])
    prop = next(p for p in candidate["properties"] if p["technical_name"] == "customer_no")
    prop["technical_name"] = "customer_code"
    fact = next(f for f in candidate["material_objects"] if "customer_no" in f["values"])
    fact["values"]["customer_code"] = fact["values"].pop("customer_no")
    body = save_body(client, session, candidate, target_id=prop["owner_type_id"])
    confirmations = preflight_confirmations(client, body)
    assert len(confirmations) == 1
    fact["values"]["customer_code"] = "C999"
    for suffix in ("/preview", ""):
        response = client.post(
            ROOT + "/element-saves" + suffix,
            json={**body, "affected_items": confirmations},
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    fact["values"]["customer_code"] = "C001"
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    assert (
        next(
            f for f in response.json()["draft"]["material_objects"] if f["id"] == fact["id"]
        )["values"]
        == fact["values"]
    )


def test_dataset_confirms_metrics_added_since_old_session_baseline(client):
    from uuid import uuid4

    from pr23_fixtures import example_session

    from ontofoundry_api.domain.canonical import element_sha256

    session = example_session(client, "13-dataset-metrics", published=True)
    current = deepcopy(session["draft"])
    metric = deepcopy(next(m for m in current["metrics"] if m["kind"] == "simple"))
    metric.update(
        id=str(uuid4()), name="新增提交数", technical_name="additional_submissions"
    )
    current["metrics"].append(metric)
    response = submit(client, current, kind="metric", target_id=metric["id"])
    assert response.status_code == 200, response.text
    candidate = deepcopy(session["draft"])
    candidate["datasets"][0]["snapshot_date_column"] = "stat_date"
    body = save_body(
        client, session, candidate, kind="dataset", target_id=candidate["datasets"][0]["id"]
    )
    confirmations = preflight_confirmations(client, body)
    assert len(confirmations) == 7
    assert next(c for c in confirmations if c["target_id"] == metric["id"])[
        "expected_target_hash"
    ] == element_sha256(metric, collection="metrics")
    response = client.post(
        ROOT + "/element-saves",
        json={
            **body,
            "affected_items": [c for c in confirmations if c["target_id"] != metric["id"]],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["draft"]["metrics"]) == 7


def test_rename_rewrites_newly_published_facts_against_latest(client):
    from uuid import uuid4

    from pr23_fixtures import example_session
    from test_modeling import publish

    session = example_session(client, "07-instances-and-evidence", published=True)
    newer = create_session(client)
    customer_fact = next(
        f for f in newer["draft"]["material_objects"] if "customer_no" in f["values"]
    )
    extra = deepcopy(customer_fact)
    extra["id"] = str(uuid4())
    extra["values"]["customer_no"] = "C002"
    newer["draft"]["material_objects"].append(extra)
    response = save(client, newer, newer["draft"])
    assert response.status_code == 200, response.text
    response = publish(client, response.json())
    assert response.status_code == 200, response.text
    candidate = deepcopy(session["draft"])
    prop = next(p for p in candidate["properties"] if p["technical_name"] == "customer_no")
    prop["technical_name"] = "customer_code"
    body = save_body(client, session, candidate, target_id=prop["owner_type_id"])
    confirmations = preflight_confirmations(client, body)
    assert {c["target_id"] for c in confirmations} == {customer_fact["id"], extra["id"]}
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    facts = [
        f
        for f in response.json()["draft"]["material_objects"]
        if f["type_id"] == prop["owner_type_id"]
    ]
    assert {f["values"]["customer_code"] for f in facts} == {"C001", "C002"}
    assert all("customer_no" not in f["values"] for f in facts)
