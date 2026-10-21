from copy import deepcopy

import pytest
from dataset_binding import bind_datasets
from test_modeling import ONTOLOGY, ROOT, create_session, save


def submit(
    client, draft, *, kind="object_type", target_id=None, session=None, version=None
):
    bind_datasets(client, draft)
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
    invalid["object_types"][0]["name"] = "bad name"
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
    current["object_types"][0]["display_name"] = "新的供应商名称"
    assert submit(client, current).status_code == 200
    response = submit(client, session["draft"], session=session)
    assert response.status_code == 200, response.text
    published = response.json()["draft"]["object_types"][0]
    assert published["display_name"] == "新的供应商名称"
    assert published["description"] == "会话中的描述"
    assert response.json()["session"]["draft"]["object_types"][0] == published




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
    prop = next(p for p in candidate["properties"] if p["name"] == "customer_no")
    prop["name"] = "customer_code"
    body = save_body(client, session, candidate, target_id=prop["owner_type_id"])
    confirmations = preflight_confirmations(client, body)
    assert confirmations == []
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    return response.json()["session"], prop["owner_type_id"]




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
    assert confirmations == []
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




def test_dataset_confirms_metrics_added_since_old_session_baseline(client):
    from uuid import uuid4

    from pr23_fixtures import example_session

    from ontofoundry_api.domain.canonical import element_sha256

    session = example_session(client, "13-dataset-metrics", published=True)
    current = deepcopy(session["draft"])
    metric = deepcopy(next(m for m in current["metrics"] if m["kind"] == "simple"))
    metric.update(id=str(uuid4()), display_name="新增提交数", name="additional_submissions")
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




@pytest.mark.parametrize("member_kind", ["property", "rule", "mapping"])
@pytest.mark.parametrize("direction", ["in", "out"])
@pytest.mark.parametrize("staged", [False, True])
def test_existing_members_cannot_cross_aggregate_boundaries(
    client, member_kind, direction, staged
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
    if staged:
        if member_kind == "mapping":
            # Keep physical columns applicable so staging reaches the scope guard.
            member["fields"] = deepcopy(candidate["mappings"][1]["fields"])
            member["sources"] = deepcopy(candidate["mappings"][1]["sources"])
        response = save(client, session, candidate)
        assert response.status_code == 200, response.text
        session = response.json()
    body = save_body(client, session, candidate, target_id=target["id"])
    before_session = client.get(ROOT + f"/sessions/{session['id']}").json()
    before_published = client.get(ROOT + "/published-snapshot").json()
    for suffix in ("/preview", ""):
        response = client.post(ROOT + "/element-saves" + suffix, json=body)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    assert client.get(ROOT + "/published-snapshot").json() == before_published
    assert client.get(ROOT + f"/sessions/{session['id']}").json() == before_session


def test_customer_property_can_be_deleted_without_moving_it(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales", published=True)
    candidate = deepcopy(session["draft"])
    prop = next(p for p in candidate["properties"] if p["name"] == "region")
    candidate["properties"].remove(prop)
    candidate["mappings"][0]["fields"].pop("region")
    body = save_body(client, session, candidate, target_id=prop["owner_type_id"])
    assert preflight_confirmations(client, body) == []
    response = client.post(ROOT + "/element-saves", json=body)
    assert response.status_code == 200, response.text
    for raw in (response.json()["draft"], response.json()["session"]["draft"]):
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
        original, original, original, candidate, "object_type", customer_id
    )
    rewritten = calculate_element_save(
        original, original, original, final, "object_type", customer_id
    )
    assert unrewritten == rewritten
    assert (original, candidate, final) == before_inputs
    body = save_body(
        client, session, final if already_rewritten else candidate, target_id=customer_id
    )
    assert preflight_confirmations(client, body) == []
    response = client.post(ROOT + "/element-saves", json=body)
    assert response.status_code == 200, response.text
    original_fields = original["mappings"][0]["fields"]
    bindings_by_uuid = {
        p["id"]: original_fields[p["name"]]
        for p in original["properties"]
        if p["owner_type_id"] == customer_id
    }
    for raw in (response.json()["draft"], response.json()["session"]["draft"]):
        mapping = next(m for m in raw["mappings"] if m["type_id"] == customer_id)
        assert {
            p["id"]: mapping["fields"][p["name"]]
            for p in raw["properties"]
            if p["owner_type_id"] == customer_id
        } == bindings_by_uuid


@pytest.mark.parametrize("new_dataset", [False, True])
def test_old_ratio_session_imports_missing_upstream_closure(client, new_dataset):
    from uuid import uuid4

    from pr23_fixtures import example_session
    from test_modeling import publish

    from ontofoundry_api.domain.canonical import element_sha256
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.validation import validate_core_graph

    old = example_session(client, "13-dataset-metrics", published=True)
    newer = create_session(client)
    latest = newer["draft"]
    ratio = next(m for m in latest["metrics"] if m["kind"] == "ratio")
    component = deepcopy(
        next(m for m in latest["metrics"] if m["id"] == ratio["numerator_id"])
    )
    component.update(id=str(uuid4()), name="new_core_commits", display_name="新核心提交数")
    latest["metrics"].append(component)
    ratio["numerator_id"] = component["id"]
    imported = [component]
    if new_dataset:
        dataset = deepcopy(latest["datasets"][0])
        dataset.update(id=str(uuid4()), name="new_code_daily", table_name="new_code_daily")
        latest["datasets"].append(dataset)
        denominator = deepcopy(
            next(m for m in latest["metrics"] if m["id"] == ratio["denominator_id"])
        )
        denominator.update(
            id=str(uuid4()), name="new_all_commits", display_name="新全部提交数"
        )
        latest["metrics"].append(denominator)
        ratio["denominator_id"] = denominator["id"]
        for metric in (component, denominator):
            metric["dataset_id"] = dataset["id"]
            metric["measure"]["dataset_id"] = dataset["id"]
            metric["time_field"]["dataset_id"] = dataset["id"]
            for condition in metric["filters"]:
                condition["column"]["dataset_id"] = dataset["id"]
        imported += [denominator, dataset]
    response = save(client, newer, latest)
    assert response.status_code == 200, response.text
    response = publish(client, response.json())
    assert response.status_code == 200, response.text
    unrelated = next(m for m in old["draft"]["metrics"] if m["kind"] == "expression")
    unrelated["description"] = "保留的无关指标草稿"
    response = save(client, old, old["draft"])
    assert response.status_code == 200, response.text
    old = response.json()
    candidate = deepcopy(old["draft"])
    next(m for m in candidate["metrics"] if m["id"] == ratio["id"])["description"] = (
        "旧会话只修改占比说明"
    )
    body = save_body(client, old, candidate, kind="metric", target_id=ratio["id"])
    confirmations = preflight_confirmations(client, body)
    assert {c["target_id"] for c in confirmations} == {e["id"] for e in imported}
    for element in imported:
        collection = "datasets" if "table_name" in element else "metrics"
        assert next(c for c in confirmations if c["target_id"] == element["id"])[
            "expected_target_hash"
        ] == element_sha256(element, collection=collection)
    before_version = client.get(ONTOLOGY + "/version").json()
    before_session = client.get(ROOT + f"/sessions/{old['id']}").json()
    for items, status, code in [
        (confirmations[:-1], 422, "ELEMENT_SCOPE_INVALID"),
        (
            [{**confirmations[0], "expected_target_hash": "0" * 64}, *confirmations[1:]],
            409,
            "VERSION_CHANGED",
        ),
    ]:
        response = client.post(
            ROOT + "/element-saves", json={**body, "affected_items": items}
        )
        assert response.status_code == status, response.text
        assert response.json()["error"]["code"] == code
        assert client.get(ONTOLOGY + "/version").json() == before_version
        assert client.get(ROOT + f"/sessions/{old['id']}").json() == before_session
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    for raw in (result["draft"], result["session"]["draft"]):
        validate_core_graph(CoreDraft.model_validate(raw))
        synced_ratio = next(m for m in raw["metrics"] if m["id"] == ratio["id"])
        assert synced_ratio["numerator_id"] == component["id"]
        assert synced_ratio["description"] == "旧会话只修改占比说明"
        assert all(
            e in raw["datasets" if "table_name" in e else "metrics"] for e in imported
        )
    assert (
        next(
            m for m in result["session"]["draft"]["metrics"] if m["id"] == unrelated["id"]
        )["description"]
        == unrelated["description"]
    )
    assert (
        next(m for m in result["draft"]["metrics"] if m["id"] == unrelated["id"])[
            "description"
        ]
        != unrelated["description"]
    )


def test_old_mapping_session_imports_new_dataset_and_preserves_other_drafts(client):
    from uuid import uuid4

    from pr23_fixtures import example_session
    from test_modeling import publish

    from ontofoundry_api.domain.canonical import element_sha256
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.validation import validate_core_graph

    old = example_session(client, "01-basic-sales", published=True)
    newer = create_session(client)
    dataset = deepcopy(newer["draft"]["datasets"][0])
    dataset.update(id=str(uuid4()), name="new_customers", table_name="new_customers")
    newer["draft"]["datasets"].append(dataset)
    newer["draft"]["mappings"][0]["sources"][0]["dataset_id"] = dataset["id"]
    response = save(client, newer, newer["draft"])
    assert response.status_code == 200, response.text
    response = publish(client, response.json())
    assert response.status_code == 200, response.text
    old["draft"]["datasets"][1]["description"] = "保留订单数据集草稿"
    old = save(client, old, old["draft"]).json()
    candidate = deepcopy(old["draft"])
    customer = candidate["object_types"][0]
    customer["description"] = "旧会话客户说明"
    body = save_body(client, old, candidate, target_id=customer["id"])
    confirmations = preflight_confirmations(client, body)
    assert confirmations == [
        {
            "target_kind": "dataset",
            "target_id": dataset["id"],
            "expected_target_hash": element_sha256(dataset, collection="datasets"),
        }
    ]
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    for raw in (response.json()["draft"], response.json()["session"]["draft"]):
        validate_core_graph(CoreDraft.model_validate(raw))
        assert dataset in raw["datasets"]
        assert raw["mappings"][0]["sources"][0]["dataset_id"] == dataset["id"]
    assert (
        response.json()["session"]["draft"]["datasets"][1]["description"]
        == "保留订单数据集草稿"
    )


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
    confirmations = preflight_confirmations(client, body)
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
            ROOT + "/element-saves", json={**body, "affected_items": items}
        )
        assert response.status_code == (409 if defect == "hash" else 422), response.text
        assert response.json()["error"]["code"] == (
            "VERSION_CHANGED" if defect == "hash" else "ELEMENT_SCOPE_INVALID"
        )
        assert client.get(ONTOLOGY + "/version").json() == before_version
        assert client.get(ROOT + f"/sessions/{session['id']}").json() == before_session


@pytest.mark.parametrize("existing_parent", [False, True])
@pytest.mark.parametrize("target_name", ["person", "vip_party", "device"])
def test_example06_old_session_imports_effective_inheritance_and_bindings(
    client, target_name, existing_parent
):
    from core1_fixtures import example_draft_json
    from test_modeling import publish

    from ontofoundry_api.domain.bindings import resolve_binding
    from ontofoundry_api.domain.canonical import element_sha256
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.graph import DraftIndex
    from ontofoundry_api.domain.models import COLLECTIONS
    from ontofoundry_api.domain.validation import validate_core_graph
    from ontofoundry_api.services.element_save import calculate_element_save, element_scope

    initial = create_session(client)
    from pr23_fixtures import clear_instances
    clear_instances(client, initial["workspace_id"])
    latest = example_draft_json("06-inheritance")
    latest["workspace_id"] = initial["workspace_id"]
    for collection in COLLECTIONS.values():
        for element in latest[collection]:
            if "evidence" in element:
                element["evidence"] = []
    if target_name == "vip_party" and not existing_parent:
        from uuid import uuid4

        root = next(o for o in latest["object_types"] if o["name"] == "party")
        middle = {
            **deepcopy(root),
            "id": str(uuid4()),
            "display_name": "登记参与方",
            "name": "registered_party",
            "extends": root["id"],
            "title_property_id": None,
        }
        latest["object_types"].append(middle)
        next(o for o in latest["object_types"] if o["name"] == target_name)["extends"] = (
            middle["id"]
        )
    target = next(o for o in latest["object_types"] if o["name"] == target_name)
    unrelated = next(o for o in latest["object_types"] if o["name"] == "supplier")
    base = {**latest, **{c: [] for c in COLLECTIONS.values()}}
    base["object_types"] = [
        {**o, "extends": None, "derived_by": [], "title_property_id": None}
        for o in (target, unrelated)
    ]
    parent = next(o for o in latest["object_types"] if o["id"] == target["extends"])
    if existing_parent:
        base["object_types"].append(
            {
                **parent,
                "extends": None,
                "derived_by": [],
                "title_property_id": None,
                "description": "保留已有父类型草稿",
            }
        )
    response = save(client, initial, base)
    assert response.status_code == 200, response.text
    assert publish(client, response.json()).status_code == 200
    old, newer = create_session(client), create_session(client)
    base = deepcopy(old["draft"])
    response = save(client, newer, latest)
    assert response.status_code == 200, response.text
    assert publish(client, response.json()).status_code == 200
    old["draft"]["object_types"][1]["description"] = "保留供应商草稿"
    response = save(client, old, old["draft"])
    assert response.status_code == 200, response.text
    old = response.json()
    candidate = deepcopy(old["draft"])
    candidate["object_types"][0]["description"] = "仅修改当前对象说明"
    body = save_body(client, old, candidate, target_id=target["id"])
    confirmations = preflight_confirmations(client, body)
    current = client.get(ROOT + "/published-snapshot").json()
    calculation = calculate_element_save(
        base, current, old["draft"], candidate, "object_type", target["id"]
    )
    assert {c["target_id"] for c in confirmations} == {
        c["target_id"] for c in calculation.affected_items
    }
    local_scope = element_scope(calculation.session_draft, "object_type", target["id"])
    imported = {
        e["id"]: (collection, e)
        for collection in COLLECTIONS.values()
        for e in calculation.session_draft[collection]
        if e["id"] not in {old_e["id"] for old_e in old["draft"][collection]}
        and e["id"] not in local_scope[collection]
    }
    assert imported
    assert set(imported) == {c["target_id"] for c in confirmations}
    for entry in confirmations:
        collection, element = imported[entry["target_id"]]
        published = next(e for e in current[collection] if e["id"] == element["id"])
        assert entry["expected_target_hash"] == element_sha256(
            published, collection=collection
        )
    for items, status, code in [
        (confirmations[:-1], 422, "ELEMENT_SCOPE_INVALID"),
        (
            [{**confirmations[0], "expected_target_hash": "0" * 64}, *confirmations[1:]],
            409,
            "VERSION_CHANGED",
        ),
    ]:
        response = client.post(
            ROOT + "/element-saves", json={**body, "affected_items": items}
        )
        assert response.status_code == status, response.text
        assert response.json()["error"]["code"] == code
    response = client.post(
        ROOT + "/element-saves", json={**body, "affected_items": confirmations}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    expected = CoreDraft.model_validate(result["draft"])
    synced = validate_core_graph(CoreDraft.model_validate(result["session"]["draft"]))
    target_id = next(o.id for o in expected.object_types if str(o.id) == target["id"])
    for graph in (expected, synced):
        index = DraftIndex(graph)
        expected_index = DraftIndex(expected)
        for definitions in (
            "effective_properties",
            "effective_links",
            "effective_rules",
            "identifier",
        ):
            assert {item.id: item for item in getattr(index, definitions)(target_id)} == {
                item.id: item for item in getattr(expected_index, definitions)(target_id)
            }
        assert resolve_binding(graph, target_id) == resolve_binding(expected, target_id)
    assert not synced.metrics
    assert not {"organization", "vehicle", "channel_partner"} & {
        o.name for o in synced.object_types
    }
    assert (
        next(o for o in synced.object_types if str(o.id) == unrelated["id"]).description
        == "保留供应商草稿"
    )
    assert (
        next(o for o in expected.object_types if str(o.id) == unrelated["id"]).description
        != "保留供应商草稿"
    )
    if existing_parent:
        assert (
            next(o for o in synced.object_types if str(o.id) == parent["id"]).description
            == "保留已有父类型草稿"
        )


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
    assert preflight_confirmations(client, body) == []
    response = client.post(ROOT + "/element-saves", json=body)
    assert response.status_code == 200, response.text
    for raw in (response.json()["draft"], response.json()["session"]["draft"]):
        graph = CoreDraft.model_validate(raw)
        obj = next(o for o in graph.object_types if str(o.id) == vip["id"])
        binding = resolve_binding(graph, obj.id)
        assert binding.fields["note2"].model_dump(mode="json") == mapping["fields"]["note2"]
        assert "note" not in binding.fields
        assert binding_readiness(graph, obj.id).status == "bound"






def assert_customer_code_graphs(result, customer_id):
    from ontofoundry_api.domain.models import OntologyDraft
    for raw in (result["draft"], result["session"]["draft"]):
        model = OntologyDraft.model_validate(raw)
        customer = next(o for o in model.object_types if str(o.id) == customer_id)
        assert customer.description == "改名后的第二次描述"
        assert "customer_code" in {p.name for p in model.properties if p.owner_type_id == customer.id}
        assert "material_objects" not in raw
