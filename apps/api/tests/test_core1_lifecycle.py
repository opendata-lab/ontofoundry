"""All thirteen shared core examples publish without an exchange-format compiler."""

from uuid import uuid4

import pytest
from core1_fixtures import example_draft_json, example_names
from dataset_binding import bind_datasets
from test_modeling import create_session
from test_t4_proposal_decisions import decide, seed_batch, update


@pytest.mark.parametrize("name", example_names())
def test_all_examples_save_publish_read(client, name):
    wid = client.post(
        "/api/v1/workspaces",
        json={"name": "虚构验收" + uuid4().hex[:8], "slug": "fixture-" + uuid4().hex[:8]},
    ).json()["id"]
    root = f"/api/v1/workspaces/{wid}"
    session = client.post(root + "/sessions", json={}).json()
    draft = example_draft_json(name)
    draft["workspace_id"] = wid
    # Design-only evidence has no source files. This lifecycle test does not
    # claim evidence validation; dedicated tests create actual materials.
    for collection in (
        "object_types",
        "properties",
        "link_types",
        "rules",
        "metrics",
        "material_objects",
        "material_links",
    ):
        for e in draft[collection]:
            e["evidence"] = []
    bind_datasets(client, draft, session["workspace_id"])
    saved = client.put(
        root + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": draft},
    )
    assert saved.status_code == 200, saved.text
    session = saved.json()
    preview = client.post(
        root + f"/sessions/{session['id']}/preview",
        json={"expected_session_revision": session["revision"]},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["validation"]["publishable"], body
    response = client.post(
        root + f"/sessions/{session['id']}/publish",
        json={
            "expected_session_revision": session["revision"],
            "expected_current_version_id": body["current_version_id"],
            "expected_merged_snapshot_sha256": body["merged_snapshot_sha256"],
        },
    )
    assert response.status_code == 200, response.text
    assert (
        client.get(root + "/published-snapshot").json()
        == response.json()["session"]["draft"]
    )


def test_atomic_name_swap_expands_and_undo_restores(client):
    s = create_session(client)
    a, b = s["draft"]["object_types"][:2]
    batch = seed_batch(
        client,
        s,
        [
            update("object_type", a, display_name=b["name"], name=b["name"]),
            update("object_type", b, display_name=a["name"], name=a["name"]),
        ],
    )
    first, second = batch["items"]
    assert (
        first["atomic_group_id"] == second["atomic_group_id"] and first["atomic_group_id"]
    )
    response = decide(client, s, [(first["id"], "accept")])
    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == 2
    accepted = response.json()["session"]
    undo = decide(client, accepted, [(first["id"], "reject")])
    assert undo.status_code == 200, undo.text
    assert undo.json()["session"]["draft"] == s["draft"]


@pytest.mark.parametrize("kind", ["material_object", "mapping"])
def test_unnamed_independent_proposals_do_not_share_atomic_decisions(client, kind):
    from copy import deepcopy

    from pr23_fixtures import example_session
    from test_modeling import ROOT

    session = example_session(
        client,
        "07-instances-and-evidence" if kind == "material_object" else "01-basic-sales",
    )
    if kind == "material_object":
        a, b = session["draft"]["material_objects"][:2]
        edits = [
            update(kind, a, values={**a["values"], "name": "星海贸易新名称"}),
            update(kind, b, values={**b["values"], "refund": 200}),
        ]
    else:
        a, b = session["draft"]["mappings"][:2]
        edits = []
        for mapping in (a, b):
            fields = deepcopy(mapping["fields"])
            # Clearing a non-key field is an independent incomplete binding.
            field = next(name for name in fields if name in {"name", "amount"})
            fields.pop(field)
            edits.append(update(kind, mapping, fields=fields, inherited_link_bindings=[]))
    batch = seed_batch(client, session, edits)
    assert len(batch["items"]) == 2
    first, second = batch["items"]
    assert first["atomic_group_id"] is None and second["atomic_group_id"] is None
    response = decide(client, session, [(first["id"], "accept")])
    assert response.status_code == 200, response.text
    assert [r["proposal_id"] for r in response.json()["results"]] == [first["id"]]
    accepted = response.json()["session"]
    collection = "material_objects" if kind == "material_object" else "mappings"
    assert next(e for e in accepted["draft"][collection] if e["id"] == b["id"]) == b
    undone = decide(client, accepted, [(first["id"], "reject")])
    assert undone.status_code == 200, undone.text
    assert undone.json()["session"]["draft"] == session["draft"]
    statuses = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}"
    ).json()["items"]
    assert statuses[1]["status"] == "pending"
