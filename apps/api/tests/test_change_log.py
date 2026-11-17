"""Append-only change log tests across all write paths, read endpoint, and migration."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from jsonschema import Draft202012Validator
from test_element_save import submit as submit_element_save
from test_instance_store import baseline, create_instance
from test_modeling import ROOT, create_session, publish
from test_t4_proposal_decisions import chain, current, decide, seed_batch, update

from ontofoundry_api.contracts.session_writes import session_writes_schema
from ontofoundry_api.services.workspaces import DEV_USER_ID


def events_for(client, session_id: str, *, target_id: str | None = None, limit: int = 100, cursor: str | None = None):
    params = {"limit": limit}
    if target_id is not None:
        params["target_id"] = target_id
    if cursor is not None:
        params["cursor"] = cursor
    return client.get(ROOT + f"/sessions/{session_id}/change-events", params=params)


def test_migration_creates_and_drops_change_events_with_constraints():
    path = (
        Path(__file__).parents[1]
        / "src/ontofoundry_api/alembic/versions/20261116_000002_change_events.py"
    )
    spec = importlib.util.spec_from_file_location("change_events", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20261116_000001"

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(36), primary_key=True))
    sa.Table("workspaces", metadata, sa.Column("id", sa.String(36), primary_key=True))
    sa.Table(
        "modeling_sessions",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_modeling_sessions_ws_id"),
    )
    metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(sa.text("INSERT INTO users (id) VALUES ('u1')"))
        db.execute(sa.text("INSERT INTO workspaces (id) VALUES ('w1')"))
        db.execute(sa.text("INSERT INTO modeling_sessions (id, workspace_id) VALUES ('s1', 'w1')"))
        migration.op = Operations(MigrationContext.configure(db))
        migration.upgrade()
        assert "change_events" in sa.inspect(db).get_table_names()

        db.execute(
            sa.text(
                "INSERT INTO change_events (id, workspace_id, session_id, at, seq, actor_id, actor_kind, subject, action, target_kind, target_id) "
                "VALUES ('e1', 'w1', 's1', '2026-11-16T00:00:00Z', 1, 'u1', 'human', 'draft', 'updated', 'object_type', 'obj-1')"
            )
        )
        # Version event requires null target and non-null version_id.
        with db.begin_nested(), pytest.raises(sa.exc.IntegrityError):
            db.execute(
                sa.text(
                    "INSERT INTO change_events (id, workspace_id, session_id, at, seq, actor_id, actor_kind, subject, action, target_kind, target_id, version_id) "
                    "VALUES ('bad1', 'w1', 's1', '2026-11-16T00:00:00Z', 2, 'u1', 'human', 'version', 'published', 'object_type', 'obj-1', 'v1')"
                )
            )
        # Invalid action for subject fails constraint.
        with db.begin_nested(), pytest.raises(sa.exc.IntegrityError):
            db.execute(
                sa.text(
                    "INSERT INTO change_events (id, workspace_id, session_id, at, seq, actor_id, actor_kind, subject, action, target_kind, target_id) "
                    "VALUES ('bad2', 'w1', 's1', '2026-11-16T00:00:00Z', 3, 'u1', 'human', 'draft', 'accepted', 'object_type', 'obj-1')"
                )
            )

        migration.downgrade()
        assert "change_events" not in sa.inspect(db).get_table_names()
    engine.dispose()


def test_no_update_or_delete_path_exists_for_change_events(client):
    src_root = Path(__file__).parents[1] / "src/ontofoundry_api"
    writer_path = (src_root / "services/change_log.py").resolve()
    migration_dir = (src_root / "alembic/versions").resolve()

    for py_file in src_root.rglob("*.py"):
        resolved = py_file.resolve()
        source = py_file.read_text()
        if resolved != writer_path and not resolved.is_relative_to(migration_dir):
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id == "ChangeEventRecord":
                        raise AssertionError(f"Only services/change_log.py may instantiate ChangeEventRecord: {py_file}")
        if not resolved.is_relative_to(migration_dir):
            assert not re.search(r"\b(?:update|delete)\(\s*ChangeEventRecord\b", source), py_file
            assert not re.search(r"\b(?:UPDATE|DELETE\s+FROM)\s+change_events\b", source, re.IGNORECASE), py_file

    # Check change_log.py itself exposes no update/delete mutations.
    writer_source = writer_path.read_text()
    assert ".delete(" not in writer_source
    assert "sa.update" not in writer_source and "update(" not in writer_source

    # Verify HTTP surface only exposes GET for change-events.
    paths = client.app.openapi()["paths"]
    change_paths = {p: set(ops.keys()) for p, ops in paths.items() if "change-events" in p}
    assert change_paths == {
        "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/change-events": {"get"}
    }


def test_human_save_coalesce_revert_and_rollback_record_two_layers(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    target_id = target["id"]

    # 1. First human save -> proposal:created (accepted) + draft:updated (cause_id -> proposal event)
    d1 = deepcopy(session["draft"])
    d1["object_types"][0]["description"] = "第一次人工修改"
    s1 = submit_element_save(client, d1, session=session).json()

    page1 = events_for(client, s1["id"], target_id=target_id).json()
    assert len(page1["items"]) == 2
    draft_ev1, prop_ev1 = page1["items"]
    assert prop_ev1["subject"] == "proposal"
    assert prop_ev1["action"] == "created"
    assert prop_ev1["actor_kind"] == "human"
    assert prop_ev1["actor_id"] == DEV_USER_ID
    assert prop_ev1["run_token"] is None
    assert prop_ev1["before"] is None
    assert prop_ev1["after"]["status"] == "accepted"
    assert prop_ev1["after"]["after"]["description"] == "第一次人工修改"

    assert draft_ev1["subject"] == "draft"
    assert draft_ev1["action"] == "updated"
    assert draft_ev1["cause_id"] == prop_ev1["id"]
    assert draft_ev1["proposal_id"] == prop_ev1["proposal_id"]
    assert draft_ev1["before"]["description"] == target["description"]
    assert draft_ev1["after"]["description"] == "第一次人工修改"

    # 2. Repeated save folds -> proposal:revised + draft:updated
    d2 = deepcopy(s1["draft"])
    d2["object_types"][0]["description"] = "第二次人工修改"
    s2 = submit_element_save(client, d2, session=s1).json()
    page2 = events_for(client, s2["id"], target_id=target_id).json()
    assert len(page2["items"]) == 4
    draft_ev2, prop_ev2 = page2["items"][:2]
    assert prop_ev2["subject"] == "proposal"
    assert prop_ev2["action"] == "revised"
    assert prop_ev2["before"]["after"]["description"] == "第一次人工修改"
    assert prop_ev2["after"]["after"]["description"] == "第二次人工修改"
    assert draft_ev2["cause_id"] == prop_ev2["id"]
    assert draft_ev2["before"]["description"] == "第一次人工修改"
    assert draft_ev2["after"]["description"] == "第二次人工修改"

    # 3. Saving back to original value -> proposal:rejected + draft:updated
    s3 = submit_element_save(client, session["draft"], session=s2).json()
    page3 = events_for(client, s3["id"], target_id=target_id).json()
    assert len(page3["items"]) == 6
    draft_ev3, prop_ev3 = page3["items"][:2]
    assert prop_ev3["subject"] == "proposal"
    assert prop_ev3["action"] == "rejected"
    assert prop_ev3["before"]["status"] == "accepted"
    assert prop_ev3["after"]["status"] == "rejected"
    assert draft_ev3["cause_id"] == prop_ev3["id"]
    assert draft_ev3["before"]["description"] == "第二次人工修改"
    assert draft_ev3["after"]["description"] == target["description"]

    # 4. Failed human save (stale revision) writes no change events.
    before_count = len(events_for(client, s3["id"]).json()["items"])
    bad_save = submit_element_save(client, d2, session=s1)
    assert bad_save.status_code == 409
    assert len(events_for(client, s3["id"]).json()["items"]) == before_count

    # 5. Validate against session-writes JSON schema.
    schema = session_writes_schema()
    Draft202012Validator({"$ref": "#/$defs/ChangeEventPageRead", "$defs": schema["$defs"]}).validate(page3)


def test_agent_submit_and_rollback_record_actor_and_run_token(client):
    from test_proposal_submit import running_submit
    from test_t3_proposal_results import result, some_items

    session, manifest, endpoint, headers = running_submit(client)

    # Failed submission writes no change events.
    bad = client.post(endpoint, headers=headers, json={"items": [{"invalid": True}]})
    assert bad.status_code == 200 and bad.json()["passed"] is False
    assert events_for(client, session["id"]).json()["items"] == []

    # Valid submission records proposal:created with actor_kind=agent, actor_id, run_token.
    payload = result(manifest, some_items(session["draft"])[:1])
    ok = client.post(endpoint, headers=headers, json=payload)
    assert ok.status_code == 200 and ok.json()["passed"] is True, ok.json()

    # Duplicate retry writes no extra events.
    replay = client.post(endpoint, headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json()["passed"] is True

    evs = events_for(client, session["id"]).json()["items"]
    assert len(evs) == 1
    ev = evs[0]
    assert ev["subject"] == "proposal"
    assert ev["action"] == "created"
    assert ev["actor_kind"] == "agent"
    assert ev["actor_id"] == DEV_USER_ID
    assert ev["run_token"] == manifest["run_token"]
    assert ev["after"]["status"] == "pending"


def test_decisions_cascading_undo_and_restore_record_causal_links(client):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session)[:2])
    po, prop = batch["items"]

    # Accept property (cascades to parent object_type)
    accepted = decide(client, session, [(prop["id"], "accept")])
    assert accepted.status_code == 200, accepted.text
    s_after_accept = accepted.json()["session"]

    evs_after_accept = events_for(client, s_after_accept["id"]).json()["items"]
    # 2 proposals created (from seed_batch) + 2 proposals accepted + 2 drafts added = 6
    assert len(evs_after_accept) == 6
    draft_adds = [e for e in evs_after_accept if e["subject"] == "draft" and e["action"] == "added"]
    prop_accepts = [e for e in evs_after_accept if e["subject"] == "proposal" and e["action"] == "accepted"]
    assert len(draft_adds) == 2 and len(prop_accepts) == 2
    accept_by_prop_id = {e["proposal_id"]: e for e in prop_accepts}
    # Explicit decision was prop; po was pulled in as dependency so po's proposal event links to prop's.
    assert accept_by_prop_id[prop["id"]]["cause_id"] is None
    assert accept_by_prop_id[po["id"]]["cause_id"] == accept_by_prop_id[prop["id"]]["id"]
    for d in draft_adds:
        assert d["cause_id"] == accept_by_prop_id[d["proposal_id"]]["id"]

    # Reject po -> cascades to prop; both proposals rejected & both drafts removed.
    undone = decide(client, s_after_accept, [(po["id"], "reject")])
    assert undone.status_code == 200, undone.text
    s_after_undo = undone.json()["session"]
    evs_after_undo = events_for(client, s_after_undo["id"]).json()["items"]
    assert len(evs_after_undo) == 10
    recent = evs_after_undo[:4]
    undo_proposals = [e for e in recent if e["subject"] == "proposal" and e["action"] == "rejected"]
    undo_drafts = [e for e in recent if e["subject"] == "draft" and e["action"] == "removed"]
    assert len(undo_proposals) == 2 and len(undo_drafts) == 2
    rej_by_prop_id = {e["proposal_id"]: e for e in undo_proposals}
    assert rej_by_prop_id[po["id"]]["cause_id"] is None
    assert rej_by_prop_id[prop["id"]]["cause_id"] == rej_by_prop_id[po["id"]]["id"]
    for d in undo_drafts:
        assert d["cause_id"] == rej_by_prop_id[d["proposal_id"]]["id"]

    # Restore prop (cascades to po) -> only proposal events, zero new draft events.
    restored = decide(client, s_after_undo, [(prop["id"], "restore")])
    assert restored.status_code == 200, restored.text
    evs_after_restore = events_for(client, s_after_undo["id"]).json()["items"]
    assert len(evs_after_restore) == 12
    assert all(e["subject"] == "proposal" and e["action"] == "restored" for e in evs_after_restore[:2])


def test_proposal_edits_do_not_touch_draft_layer(client):
    session = create_session(client)
    obj = session["draft"]["object_types"][0]
    ds = session["draft"]["datasets"][0]
    [item_obj] = seed_batch(client, session, [update("object_type", obj, description="原提议")])["items"]
    # 1. PATCH /proposals/{p}/after
    r1 = client.patch(
        ROOT + f"/sessions/{session['id']}/proposals/{item_obj['id']}/after",
        json={"fields": {"description": "修订后描述"}, "expected_session_revision": session["revision"]},
    )
    assert r1.status_code == 200, r1.text
    session = current(client, session)

    # 2. Reject obj proposal, seed dataset proposal, PUT /proposals/{p}/dataset
    assert decide(client, session, [(item_obj["id"], "reject")]).status_code == 200
    session = current(client, session)
    [item_ds] = seed_batch(client, session, [update("dataset", ds, description="数据集提议")])["items"]
    edited_ds = deepcopy(ds)
    edited_ds["description"] = "修订后数据集"
    r2 = client.put(
        ROOT + f"/sessions/{session['id']}/proposals/{item_ds['id']}/dataset",
        json={"dataset": edited_ds, "expected_session_revision": session["revision"]},
    )
    assert r2.status_code == 200, r2.text
    session = current(client, session)

    # 3. Reject ds proposal, seed duplicate fact proposal, POST /proposals/{p}/fact-revision
    assert decide(client, session, [(item_ds["id"], "reject")]).status_code == 200
    session = current(client, session)
    target_fact = baseline(client, session)["items"][0]
    [item_fact] = seed_batch(client, session, [create_instance(session, target_fact["element"]["values"]["label"])])["items"]
    revised_fact = deepcopy(target_fact["element"])
    revised_fact["values"]["label"] = "事实修订后标签"
    r3 = client.post(
        ROOT + f"/sessions/{session['id']}/proposals/{item_fact['id']}/fact-revision",
        json={
            "expected_session_revision": session["revision"],
            "target_id": target_fact["target_id"],
            "expected_target_hash": target_fact["hash"],
            "after": revised_fact,
        },
    )
    assert r3.status_code == 200, r3.text

    all_events = events_for(client, session["id"]).json()["items"]
    # None of the 3 proposal revision actions created a draft event.
    assert [e for e in all_events if e["subject"] == "draft"] == []
    revised_events = [e for e in all_events if e["action"] == "revised"]
    assert len(revised_events) == 3
    assert {e["target_id"] for e in revised_events} == {obj["id"], ds["id"], target_fact["target_id"]}


def test_import_confirm_and_completion_record_import_and_human_events(client):
    from test_core1_import_flow import count_document, import_root, preview

    wid = client.post(
        "/api/v1/workspaces",
        json={"name": "虚构导入记录" + uuid4().hex[:6], "slug": "fiction-imp-log-" + uuid4().hex[:6]},
    ).json()["id"]
    raw = json.dumps(count_document(), ensure_ascii=False).encode()
    prev = preview(client, wid, raw, adapter="ossie-0.2")
    confirmed = client.post(
        import_root(wid, "ossie-0.2") + f"/{prev['import_id']}/confirm",
        json={
            "idempotency_key": "confirm-" + uuid4().hex[:8],
            "content_sha256": prev["content_sha256"],
            "expected_current_version_id": prev["base_version_id"],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    sid = confirmed.json()["session_id"]

    evs = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}/change-events").json()["items"]
    assert len(evs) > 0
    assert all(e["actor_kind"] == "import" and e["subject"] == "proposal" and e["action"] == "created" and e["run_token"] is None for e in evs)

    # Complete the blocked count metric using the import completion endpoint.
    report = client.get(import_root(wid, "ossie-0.2") + f"/{prev['import_id']}").json()
    issue = next(c for c in report["completion"] if c["kind"] == "count_dataset")
    session = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}").json()
    comp = client.post(
        import_root(wid, "ossie-0.2") + f"/{prev['import_id']}/completions",
        json={
            "idempotency_key": "complete-" + uuid4().hex[:8],
            "issue_id": issue["issue_id"],
            "expected_session_revision": session["revision"],
            "expected_draft_sha256": session["draft_sha256"],
            "dataset_id": issue["datasets"][0]["id"],
        },
    )
    assert comp.status_code == 200, comp.text
    evs_after = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}/change-events").json()["items"]
    assert len(evs_after) == len(evs) + 1
    newest = evs_after[0]
    assert newest["actor_kind"] == "human"
    assert newest["subject"] == "proposal"
    assert newest["action"] == "created"


def test_resolve_merge_and_publish_record_draft_and_version_events(client):
    session_a = create_session(client)
    session_b = create_session(client)
    target_id = session_a["draft"]["object_types"][0]["id"]

    # Session A modifies description and publishes -> version:published event on session A.
    d_a = deepcopy(session_a["draft"])
    d_a["object_types"][0]["description"] = "会话A发布描述"
    s_a = submit_element_save(client, d_a, session=session_a).json()
    pub_a = publish(client, s_a)
    assert pub_a.status_code == 200, pub_a.text
    version_id = pub_a.json()["version"]["version_id"]

    a_events = events_for(client, s_a["id"]).json()["items"]
    assert a_events[0]["subject"] == "version"
    assert a_events[0]["action"] == "published"
    assert a_events[0]["target_kind"] is None and a_events[0]["target_id"] is None
    assert a_events[0]["version_id"] == version_id
    # Filtering by target_id excludes session-level version event.
    a_target_events = events_for(client, s_a["id"], target_id=target_id).json()["items"]
    assert all(e["target_id"] == target_id for e in a_target_events)

    # Session B modifies same description -> merge conflict -> resolve_merge records draft:updated.
    d_b = deepcopy(session_b["draft"])
    d_b["object_types"][0]["description"] = "会话B冲突描述"
    s_b = submit_element_save(client, d_b, session=session_b).json()
    preview_err = client.post(
        ROOT + f"/sessions/{s_b['id']}/publish-preview",
        json={"expected_session_revision": s_b["revision"]},
    )
    assert preview_err.status_code == 409
    conflicts = preview_err.json()["error"]["conflicts"]
    resolutions = {c["key"]: {"choice": "custom", "value": "人工合并描述"} for c in conflicts}
    resolved = client.post(
        ROOT + f"/sessions/{s_b['id']}/resolve-merge",
        json={
            "expected_session_revision": s_b["revision"],
            "expected_current_version_id": version_id,
            "resolutions": resolutions,
        },
    )
    assert resolved.status_code == 200, resolved.text
    b_events = events_for(client, s_b["id"], target_id=target_id).json()["items"]
    draft_row = next(e for e in b_events if e["subject"] == "draft" and e["after"] and e["after"].get("description") == "人工合并描述")
    assert draft_row["action"] == "updated"
    assert draft_row["before"]["description"] == "会话B冲突描述"
    # A value typed while resolving is the user's own edit: an accepted human proposal (§4.3).
    proposal_row = next(e for e in b_events if e["id"] == draft_row["cause_id"])
    assert proposal_row["subject"] == "proposal" and proposal_row["actor_kind"] == "human"
    assert proposal_row["after"]["after"]["description"] == "人工合并描述"


def test_resolving_with_the_latest_version_only_moves_the_base(client):
    session_a = create_session(client)
    session_b = create_session(client)
    target_id = session_a["draft"]["object_types"][0]["id"]
    d_a = deepcopy(session_a["draft"])
    d_a["object_types"][0]["description"] = "会话A发布描述"
    s_a = submit_element_save(client, d_a, session=session_a).json()
    version_id = publish(client, s_a).json()["version"]["version_id"]
    d_b = deepcopy(session_b["draft"])
    d_b["object_types"][0]["description"] = "会话B冲突描述"
    s_b = submit_element_save(client, d_b, session=session_b).json()
    proposals_before = [e for e in events_for(client, s_b["id"], target_id=target_id).json()["items"] if e["subject"] == "proposal"]
    conflicts = client.post(ROOT + f"/sessions/{s_b['id']}/publish-preview",
                            json={"expected_session_revision": s_b["revision"]}).json()["error"]["conflicts"]
    resolved = client.post(ROOT + f"/sessions/{s_b['id']}/resolve-merge", json={
        "expected_session_revision": s_b["revision"], "expected_current_version_id": version_id,
        "resolutions": {c["key"]: {"choice": "latest"} for c in conflicts},
    })
    assert resolved.status_code == 200, resolved.text
    events = events_for(client, s_b["id"], target_id=target_id).json()["items"]
    assert [e for e in events if e["subject"] == "proposal"] == proposals_before
    assert events[0]["subject"] == "draft" and events[0]["after"]["description"] == "会话A发布描述"


def test_change_events_pagination_and_cursor_validation(client):
    session = create_session(client)
    s = session
    target_id = s["draft"]["object_types"][0]["id"]
    for idx in range(5):
        d = deepcopy(s["draft"])
        d["object_types"][0]["description"] = f"第{idx + 1}次"
        s = submit_element_save(client, d, session=s).json()

    full = events_for(client, s["id"], target_id=target_id, limit=50).json()
    assert len(full["items"]) == 10
    assert full["next_cursor"] is None

    collected = []
    cursor = None
    while True:
        page = events_for(client, s["id"], target_id=target_id, limit=3, cursor=cursor).json()
        collected.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert [e["id"] for e in collected] == [e["id"] for e in full["items"]]

    bad_cursor = events_for(client, s["id"], cursor="non-existent-cursor")
    assert bad_cursor.status_code == 422
    assert bad_cursor.json()["error"]["code"] == "INVALID_CURSOR"


def test_publish_auto_merge_records_per_element_draft_events(client):
    session_a = create_session(client)
    session_b = create_session(client)

    # Session A modifies object_types[1] and publishes.
    a_target = session_a["draft"]["object_types"][1]
    d_a = deepcopy(session_a["draft"])
    d_a["object_types"][1]["description"] = "会话A无冲突发布描述"
    s_a = submit_element_save(client, d_a, target_id=a_target["id"], session=session_a).json()
    pub_a = publish(client, s_a)
    assert pub_a.status_code == 200, pub_a.text

    # Session B modifies a different element (object_types[0]), then publishes without conflict.
    d_b = deepcopy(session_b["draft"])
    d_b["object_types"][0]["description"] = "会话B独立修改描述"
    s_b = submit_element_save(client, d_b, session=session_b).json()
    pub_b = publish(client, s_b)
    assert pub_b.status_code == 200, pub_b.text
    version_b_id = pub_b.json()["version"]["version_id"]

    # Session B's version event is newest, and the auto-merged element from A gets a draft:updated event.
    b_all = events_for(client, s_b["id"]).json()["items"]
    assert b_all[0]["subject"] == "version"
    assert b_all[0]["version_id"] == version_b_id

    merged_events = events_for(client, s_b["id"], target_id=a_target["id"]).json()["items"]
    assert len(merged_events) == 1
    ev = merged_events[0]
    assert ev["subject"] == "draft"
    assert ev["action"] == "updated"
    assert ev["before"]["description"] == a_target["description"]
    assert ev["after"]["description"] == "会话A无冲突发布描述"


def test_instance_relation_cascade_delete_and_restore_record_draft_events(client):
    from test_instance_store import accept_all, instance_update

    session = create_session(client)
    customer = baseline(client, session)["items"][0]
    order = next(t for t in session["draft"]["object_types"] if t["name"] == "order")
    link_type = session["draft"]["link_types"][0]

    session, create_batch = accept_all(
        client,
        session,
        [
            {
                "client_ref": "order-cascade",
                "operation": "create",
                "target_kind": "material_object",
                "after": {"type_id": order["id"], "values": {"order_no": "O-CASCADE"}},
            },
            {
                "client_ref": "link-cascade",
                "operation": "create",
                "target_kind": "material_link",
                "after": {
                    "type_id": link_type["id"],
                    "source_id": {"client_ref": "order-cascade"},
                    "target_id": customer["target_id"],
                },
            },
        ],
    )
    link_id = next(
        i["target_id"] for i in create_batch["items"] if i["target_kind"] == "material_link"
    )

    # Accepting deletion of customer cascades to delete the relation.
    deletion = {**instance_update(customer), "operation": "delete", "after": None}
    session, del_batch = accept_all(client, session, [deletion])
    del_prop_id = del_batch["items"][0]["id"]

    link_events_after_delete = events_for(client, session["id"], target_id=link_id).json()["items"]
    cascade_del = link_events_after_delete[0]
    assert cascade_del["subject"] == "draft"
    assert cascade_del["action"] == "removed"
    assert cascade_del["target_kind"] == "material_link"
    assert cascade_del["target_id"] == link_id
    assert cascade_del["proposal_id"] == del_prop_id
    assert cascade_del["before"] is not None
    assert cascade_del["before"]["id"] == link_id
    assert cascade_del["after"] is None

    customer_accept_event = next(
        e
        for e in events_for(client, session["id"], target_id=customer["target_id"]).json()["items"]
        if e["subject"] == "proposal" and e["action"] == "accepted"
    )
    assert cascade_del["cause_id"] == customer_accept_event["id"]

    # Undoing the deletion cascades to restore the relation.
    undone = decide(client, session, [(del_prop_id, "reject")])
    assert undone.status_code == 200, undone.text

    link_events_after_undo = events_for(client, session["id"], target_id=link_id).json()["items"]
    cascade_restore = link_events_after_undo[0]
    assert cascade_restore["subject"] == "draft"
    assert cascade_restore["action"] == "added"
    assert cascade_restore["target_kind"] == "material_link"
    assert cascade_restore["target_id"] == link_id
    assert cascade_restore["proposal_id"] == del_prop_id
    assert cascade_restore["before"] is None
    assert cascade_restore["after"] is not None
    assert cascade_restore["after"]["id"] == link_id

    customer_reject_event = next(
        e
        for e in events_for(client, session["id"], target_id=customer["target_id"]).json()["items"]
        if e["subject"] == "proposal" and e["action"] == "rejected"
    )
    assert cascade_restore["cause_id"] == customer_reject_event["id"]
