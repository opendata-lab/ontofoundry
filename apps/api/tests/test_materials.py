"""Uploaded source durability and release of session upload bookkeeping."""

from test_modeling import ROOT, create_session

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

CONTENT = "# 虚构材料\n\n客户编号与订单金额。"


def upload(client, name="虚构材料.md"):
    response = client.post(ROOT + "/materials", params={"name": name}, content=CONTENT)
    assert response.status_code == 201, response.text
    return response.json()


def overview(client):
    items = client.get(ROOT + "/materials/overview").json()["items"]
    return {material["id"]: material for material in items}


def save_materials(client, session, material_ids):
    return client.put(
        ROOT + f"/sessions/{session['id']}",
        json={
            "revision": session["revision"],
            "draft": session["draft"],
            "material_ids": material_ids,
        },
    )


def source_path(client, material):
    root = client.app.state.settings.data_dir.resolve()
    return root / str(DEMO_WORKSPACE_ID) / (material["sha256"] + ".md")


def test_download_rebuilds_lost_source_and_reupload_restores_it(client):
    material = upload(client)
    path = source_path(client, material)
    assert path.is_file()

    path.unlink()
    download = client.get(ROOT + f"/materials/{material['id']}")
    assert download.status_code == 200
    assert download.text == CONTENT
    assert path.read_text(encoding="utf-8") == CONTENT

    path.unlink()
    again = upload(client)
    assert again["id"] == material["id"]
    assert path.read_text(encoding="utf-8") == CONTENT


def test_unchecking_materials_releases_stale_upload_bookkeeping(client):
    material = upload(client)
    session = create_session(client)
    material_id = material["id"]

    saved = save_materials(client, session, [material_id])
    assert saved.status_code == 200, saved.text
    assert overview(client)[material_id]["usage"]["can_delete"] is False

    # A settled run leaves these rows behind; they must not keep blocking deletion.
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        row.uploaded_material_ids = [material_id]
        row.run_manifest_json = {
            "materials": [{"id": material_id, "sha256": material["sha256"]}]
        }
        db.commit()

    saved = save_materials(client, saved.json(), [])
    assert saved.status_code == 200, saved.text
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        assert row.uploaded_material_ids == []
        assert row.run_manifest_json["materials"] == []
    assert overview(client)[material_id]["usage"]["can_delete"] is True
    assert client.delete(ROOT + f"/materials/{material_id}").status_code == 204


def test_active_run_keeps_upload_bookkeeping(client):
    material = upload(client)
    session = create_session(client)
    material_id = material["id"]
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        row.task_status = "running"
        row.uploaded_material_ids = [material_id]
        row.run_manifest_json = {
            "materials": [{"id": material_id, "sha256": material["sha256"]}]
        }
        db.commit()

    saved = save_materials(client, session, [])
    assert saved.status_code == 200, saved.text
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        assert row.uploaded_material_ids == [material_id]
    assert overview(client)[material_id]["usage"]["can_delete"] is False
