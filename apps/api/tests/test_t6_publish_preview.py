"""T6: preview is exactly what publish produces; publish refuses anything else."""

from __future__ import annotations

from test_modeling import ONTOLOGY, ROOT, create_session, save

from ontofoundry_api.db_models import OntologyVersionRecord, WorkspaceRecord
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID


def preview(client, session):
    return client.post(
        ROOT + f"/sessions/{session['id']}/preview",
        json={"expected_session_revision": session["revision"]},
    )


def publish(client, session, body):
    return client.post(
        ROOT + f"/sessions/{session['id']}/publish",
        json={
            "expected_session_revision": session["revision"],
            "expected_current_version_id": body["current_version_id"],
            "expected_merged_snapshot_sha256": body["merged_snapshot_sha256"],
            "message": "T6",
        },
    )


def edited(client, description, index=0):
    session = create_session(client)
    session["draft"]["object_types"][index]["description"] = description
    return save(client, session, session["draft"]).json()


def published_snapshot(client):
    with client.app.state.session_factory() as db:
        space = db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
        return db.get(OntologyVersionRecord, space.current_version_id).snapshot_json


def test_preview_is_what_gets_published(client):
    session = edited(client, "预览即发布")
    body = preview(client, session).json()
    assert body["current_version_number"] == 1 and body["next_version_number"] == 2
    assert body["current_version_sha256"] == client.get(ONTOLOGY + "/version").json()[
        "normalized_snapshot_sha256"
    ]
    assert [c["change"] for c in body["changes"]] == ["updated"]

    response = publish(client, session, body)

    assert response.status_code == 200, response.text
    assert response.json()["version"]["version"] == 2
    assert snapshot_sha256(published_snapshot(client)) == body["merged_snapshot_sha256"]


def test_a_new_version_after_preview_forces_a_new_preview_even_if_it_merges(client):
    mine = edited(client, "我的修改", 0)
    body = preview(client, mine).json()
    other = edited(client, "别人的修改", 1)
    assert publish(client, other, preview(client, other).json()).status_code == 200

    refused = publish(client, mine, body)

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PREVIEW_OUTDATED"
    assert client.get(ONTOLOGY + "/version").json()["version"] == 2
    again = preview(client, mine).json()
    assert [c["element_id"] for c in again["auto_merged"]] == [other["draft"]["object_types"][1]["id"]]
    assert publish(client, mine, again).status_code == 200


def test_revision_or_merged_hash_drift_is_refused(client):
    session = edited(client, "一")
    body = preview(client, session).json()
    wrong_hash = {**body, "merged_snapshot_sha256": "0" * 64}
    assert publish(client, session, wrong_hash).json()["error"]["code"] == "PREVIEW_OUTDATED"

    session["draft"]["object_types"][0]["description"] = "二"
    newer = save(client, session, session["draft"]).json()
    stale = publish(client, {**newer, "revision": newer["revision"] - 1}, body)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "PREVIEW_OUTDATED"
    assert preview(client, {**newer, "revision": newer["revision"] - 1}).json()["error"][
        "code"
    ] == "SESSION_REVISION_CHANGED"


def test_field_conflicts_are_structured_and_resolved_with_a_custom_value(client):
    a, b = edited(client, "A 的描述"), edited(client, "B 的描述")
    assert publish(client, a, preview(client, a).json()).status_code == 200

    response = preview(client, b)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "MERGE_CONFLICTS"
    (conflict,) = error["conflicts"]
    assert conflict["element_kind"] == "object_type"
    assert conflict["element_id"] == b["draft"]["object_types"][0]["id"]
    assert conflict["path"] == "description" and conflict["kind"] == "field"
    assert (conflict["latest"], conflict["draft"]) == ("A 的描述", "B 的描述")
    assert set(conflict["allowed"]) >= {"latest", "draft", "custom"}

    resolved = client.post(
        ROOT + f"/sessions/{b['id']}/resolve-merge",
        json={
            "expected_session_revision": b["revision"],
            "expected_current_version_id": error["current_version_id"],
            "resolutions": {conflict["key"]: {"choice": "custom", "value": "合并后的描述"}},
        },
    )
    assert resolved.status_code == 200, resolved.text
    session = resolved.json()
    assert session["base_version_id"] == error["current_version_id"]
    body = preview(client, session).json()
    assert publish(client, session, body).status_code == 200
    descriptions = {t["description"] for t in published_snapshot(client)["object_types"]}
    assert "合并后的描述" in descriptions


def test_set_fields_can_keep_both_sides(client):
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["tags"] = ["甲"]
    b["draft"]["object_types"][0]["tags"] = ["乙"]
    a, b = save(client, a, a["draft"]).json(), save(client, b, b["draft"]).json()
    assert publish(client, a, preview(client, a).json()).status_code == 200
    error = preview(client, b).json()["error"]
    (conflict,) = error["conflicts"]
    assert "both" in conflict["allowed"]
    resolved = client.post(
        ROOT + f"/sessions/{b['id']}/resolve-merge",
        json={
            "expected_session_revision": b["revision"],
            "expected_current_version_id": error["current_version_id"],
            "resolutions": {conflict["key"]: {"choice": "both"}},
        },
    ).json()
    assert resolved["draft"]["object_types"][0]["tags"] == ["甲", "乙"]


def test_deleting_what_another_session_changed_is_a_whole_element_conflict(client):
    a, b = create_session(client), create_session(client)
    link = a["draft"]["link_types"][0]
    a["draft"]["link_types"][0]["description"] = "改了关系"
    b["draft"]["link_types"] = [x for x in b["draft"]["link_types"] if x["id"] != link["id"]]
    a, b = save(client, a, a["draft"]).json(), save(client, b, b["draft"]).json()
    assert publish(client, a, preview(client, a).json()).status_code == 200
    (conflict,) = preview(client, b).json()["error"]["conflicts"]
    assert conflict["kind"] == "delete_modify"
    assert conflict["element_id"] == link["id"]
    assert conflict["allowed"] == ["latest", "draft"]


def test_resolving_against_a_moved_version_is_refused(client):
    a, b = edited(client, "A"), edited(client, "B")
    assert publish(client, a, preview(client, a).json()).status_code == 200
    error = preview(client, b).json()["error"]
    response = client.post(
        ROOT + f"/sessions/{b['id']}/resolve-merge",
        json={
            "expected_session_revision": b["revision"],
            "expected_current_version_id": "not-the-current",
            "resolutions": {error["conflicts"][0]["key"]: {"choice": "draft"}},
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PREVIEW_OUTDATED"
