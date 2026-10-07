from copy import deepcopy
from uuid import uuid4

from test_modeling import ONTOLOGY, ROOT, create_session, save


def submit(client, draft, *, kind="object_type", target_id=None, session=None, version=None):
    return client.post(ROOT + "/element-saves", json={
        "target_kind": kind,
        "target_id": target_id or draft["object_types"][0]["id"],
        "expected_current_version_id": version or client.get(ONTOLOGY + "/version").json()["version_id"],
        "session_id": session["id"] if session else None,
        "expected_session_revision": session["revision"] if session else None,
        "draft": draft,
    })


def test_save_immediately_creates_version_and_preserves_history(client):
    old = client.get(ONTOLOGY + "/version").json()
    draft = client.get(ROOT + "/published-snapshot").json()
    draft["object_types"][0]["description"] = "当前弹窗修改"
    response = submit(client, draft)
    assert response.status_code == 200, response.text
    assert response.json()["version"]["version"] == 2
    assert client.get(ROOT + "/published-snapshot").json() == response.json()["draft"]
    historical = client.get(ROOT + f"/versions/{old['version_id']}/presentation").json()["model"]
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
    assert client.get(ROOT + "/published-snapshot").json()["object_types"][0]["description"] == "第一次"


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
    assert client.get(ROOT + f"/sessions/{session['id']}").json()["revision"] == newer["revision"]


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
    assert client.get(ROOT + f"/sessions/{session['id']}").json()["revision"] == session["revision"]


def test_action_owned_rules_and_parameters_survive_object_save(client):
    draft = client.get(ROOT + "/published-snapshot").json()
    action_id, rule_id, param_id = (str(uuid4()) for _ in range(3))
    draft["actions"].append({
        "id": action_id, "name": "批准供应商", "technical_name": "approve_supplier",
        "description": "审批", "input_type_id": draft["object_types"][0]["id"],
        "parameters": [{"id": param_id, "name": "备注", "technical_name": "note",
                        "value_kind": "string", "required": True}],
        "precondition_rule_ids": [rule_id], "effects": [], "evidence": [],
    })
    draft["rules"].append({
        "id": rule_id, "name": "审批前置", "technical_name": "approval_check",
        "description": "", "owner_kind": "action", "owner_id": action_id,
        "rule_kind": "constraint", "expression": "TRUE", "verbalizes": [], "evidence": [],
    })
    response = submit(client, draft)
    assert response.status_code == 200, response.text
    session = create_session(client)
    edited = deepcopy(session["draft"])
    edited["object_types"][0]["description"] = "仅修改对象描述"
    response = submit(client, edited, session=session)
    assert response.status_code == 200, response.text
    current = client.get(ROOT + "/published-snapshot").json()
    assert current["actions"] == draft["actions"]
    assert current["rules"] == draft["rules"]
    preview = client.post(ROOT + f"/sessions/{session['id']}/preview", json={"expected_session_revision": response.json()["session"]["revision"]})
    assert preview.status_code == 200, preview.text
    assert preview.json()["merged_model"]["actions"] == draft["actions"]
    assert preview.json()["merged_model"]["rules"] == draft["rules"]


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
