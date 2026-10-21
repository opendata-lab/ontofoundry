"""API setup for result regressions using the shared fictional design examples."""

from core1_fixtures import example_draft_json, example_instances
from test_modeling import ROOT, create_session, publish, save


def example_session(client, name, *, published=False, with_instances=False):
    session = create_session(client)
    raw = example_draft_json(name)
    raw["workspace_id"] = session["workspace_id"]
    for elements in raw.values():
        if isinstance(elements, list):
            for element in elements:
                if "evidence" in element:
                    element["evidence"] = []
    from ontofoundry_api.services import instance_store

    with client.app.state.session_factory() as db:
        current = instance_store.baseline(db, session["workspace_id"], session["id"])
        for entry in sorted(
            current["items"], key=lambda i: i["target_kind"] == "material_object"
        ):
            instance_store.write(
                db,
                session["workspace_id"],
                session["id"],
                entry["target_kind"],
                entry["target_id"],
                None,
                expected_revision=entry["revision"],
                actor="00000000-0000-0000-0000-000000000001",
            )
        db.commit()
    response = save(client, session, raw)
    assert response.status_code == 200, response.text
    session = response.json()
    if published:
        response = publish(client, session)
        assert response.status_code == 200, response.text
        session = create_session(client)
    if with_instances:
        seed_instances(
            client, session, example_instances(name), "active" if published else "staged"
        )
    return session


def seed_instances(client, session, values, state="active"):
    from ontofoundry_api.domain.core import MaterialLink, MaterialObject
    from ontofoundry_api.services import instance_store

    with client.app.state.session_factory() as db:
        for kind, collection, shape in [
            ("material_object", "material_objects", MaterialObject),
            ("material_link", "material_links", MaterialLink),
        ]:
            for element in values.get(collection, []):
                element = shape.model_validate({**element, "evidence": []}).model_dump(
                    mode="json"
                )
                row = db.get(instance_store.RECORDS[kind], element["id"])
                instance_store.write(
                    db,
                    session["workspace_id"],
                    session["id"],
                    kind,
                    element["id"],
                    element,
                    expected_revision=row.revision if row else None,
                    actor="00000000-0000-0000-0000-000000000001",
                    state=state,
                )
        db.commit()


def instances(client, session):
    result = client.get(ROOT + f"/sessions/{session['id']}/instance-baseline").json()
    return {
        c: [i["element"] for i in result["items"] if i["target_kind"] == k]
        for k, c in [
            ("material_object", "material_objects"),
            ("material_link", "material_links"),
        ]
    }


def typed_fact_swap(left_kind, left, right_kind, right):
    """A definition-only rename fixture; instances never get rewritten by core."""
    from copy import deepcopy

    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.validation import validate_core_graph

    before = example_draft_json("07-instances-and-evidence")
    for collection in before.values():
        if isinstance(collection, list):
            for element in collection:
                if "evidence" in element:
                    element["evidence"] = []
    first, second = [
        next(p for p in before["properties"] if p["name"] == n) for n in ("name", "is_vip")
    ]
    first["value_kind"], second["value_kind"] = left_kind, right_kind
    before = validate_core_graph(CoreDraft.model_validate(before)).model_dump(mode="json")
    candidate = deepcopy(before)
    for prop in candidate["properties"]:
        if prop["id"] == first["id"]:
            prop["name"] = "is_vip"
        elif prop["id"] == second["id"]:
            prop["name"] = "name"
    return before, candidate, first["owner_type_id"]


def clear_instances(client, workspace_id):
    from ontofoundry_api.services import instance_store
    from ontofoundry_api.services.workspaces import DEV_USER_ID

    with client.app.state.session_factory() as db:
        entries = instance_store.baseline(db, workspace_id)["items"]
        for entry in sorted(entries, key=lambda i: i["target_kind"] == "material_object"):
            instance_store.write(
                db,
                workspace_id,
                None,
                entry["target_kind"],
                entry["target_id"],
                None,
                expected_revision=entry["revision"],
                actor=DEV_USER_ID,
            )
        db.commit()
