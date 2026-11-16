"""Session-scoped human writes exercise the public API and transaction guards."""

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from jsonschema import Draft202012Validator
from test_element_save import save_body, submit
from test_modeling import ONTOLOGY, ROOT, create_session, publish, published_snapshot
from test_t4_proposal_decisions import decide, seed_batch, update

from ontofoundry_api.contracts.session_writes import session_writes_schema
from ontofoundry_api.db_models import (
    ElementSaveRequestRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
    UserRecord,
)
from ontofoundry_api.services.workspaces import DEV_USER_ID


def edited(session, description):
    draft = deepcopy(session["draft"])
    draft["object_types"][0]["description"] = description
    return draft


def human_rows(client, session):
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session["id"])
        return list(db.scalars(sa.select(ProposalItemRecord).where(
            ProposalItemRecord.batch_id == item.human_batch_id,
        ).order_by(ProposalItemRecord.ordinal)))


def test_save_auto_accepts_keeps_uuid_and_never_publishes(client):
    session = create_session(client)
    before = client.get(ONTOLOGY + "/version").json()
    draft = edited(session, "人工修改")
    response = submit(client, draft, session=session)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["revision"] == session["revision"] + 1
    assert saved["unpublished_change_count"] == 1
    assert saved["base_version_id"] == session["base_version_id"]
    assert saved["pending_proposal_count"] == 0
    assert client.get(ONTOLOGY + "/version").json() == before
    [row] = human_rows(client, saved)
    assert row.status == "accepted" and row.decided_by == DEV_USER_ID
    assert row.target_id == draft["object_types"][0]["id"]
    assert row.before_json == session["draft"]["object_types"][0]
    assert row.after_json == saved["draft"]["object_types"][0]
    assert row.accepted_revision == saved["revision"]


def test_repeated_save_folds_and_return_to_original_removes_count(client):
    initial = create_session(client)
    first = submit(client, edited(initial, "第一次"), session=initial).json()
    [original_row] = human_rows(client, first)
    second = submit(client, edited(first, "第二次"), session=first).json()
    [row] = human_rows(client, second)
    assert row.id == original_row.id
    assert row.before_json == initial["draft"]["object_types"][0]
    assert row.after_json["description"] == "第二次"
    assert second["unpublished_change_count"] == 1
    reverted = submit(client, initial["draft"], session=second).json()
    assert reverted["unpublished_change_count"] == 0
    assert reverted["draft"] == initial["draft"]
    assert human_rows(client, reverted)[0].status == "rejected"


def test_intervening_agent_change_starts_another_human_proposal(client):
    initial = create_session(client)
    first = submit(client, edited(initial, "人工甲"), session=initial).json()
    [old] = human_rows(client, first)
    batch = seed_batch(client, first, [update("object_type", first["draft"]["object_types"][0], description="智能体乙")])
    response = decide(client, first, [(batch["items"][0]["id"], "accept")])
    assert response.status_code == 200, response.text
    accepted = response.json()["session"]
    response = submit(client, edited(accepted, "人工甲"), session=accepted)
    assert response.status_code == 200, response.text
    rows = human_rows(client, response.json())
    assert len(rows) == 2
    assert rows[0].id == old.id
    assert rows[1].before_json["description"] == "智能体乙"
    assert rows[1].after_json["description"] == "人工甲"
    assert rows[0].batch_id == rows[1].batch_id


def test_agent_change_then_undo_still_breaks_human_coalescing(client):
    initial = create_session(client)
    first = submit(client, edited(initial, "人工甲"), session=initial).json()
    batch = seed_batch(client, first, [update("object_type", first["draft"]["object_types"][0], description="智能体乙")])
    identity = batch["items"][0]["id"]
    accepted = decide(client, first, [(identity, "accept")]).json()["session"]
    restored = decide(client, accepted, [(identity, "reject")]).json()["session"]
    response = submit(client, edited(restored, "人工丙"), session=restored)
    assert response.status_code == 200, response.text
    assert len(human_rows(client, response.json())) == 2


def test_save_idempotency_replays_exact_response_and_rejects_mismatch(client):
    session = create_session(client)
    candidate = edited(session, "幂等保存")
    body = save_body(client, session, candidate, target_id=candidate["object_types"][0]["id"])
    endpoint = ROOT + f"/sessions/{session['id']}/element-saves"
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    first = response.json()
    assert submit(client, edited(first, "后来修改"), session=first).status_code == 200
    assert client.post(endpoint, json=body).json() == first
    different = deepcopy(body)
    different["draft"]["object_types"][0]["description"] = "不同内容"
    rejected = client.post(endpoint, json=different)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    assert len(human_rows(client, first)) == 1


def test_failed_accept_is_atomic_and_key_can_be_reused_after_correction(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales", published=True)
    draft = deepcopy(session["draft"])
    owner = draft["object_types"][0]["id"]
    prop = {"id": str(uuid4()), "owner_type_id": owner, "name": "fiction_grade", "value_kind": "string"}
    draft["properties"].append(prop)
    body = save_body(client, session, draft, target_id=owner)
    endpoint = ROOT + f"/sessions/{session['id']}/element-saves"
    response = client.post(endpoint, json=body)
    assert response.status_code == 422, response.text
    assert "未绑定" in response.text
    with client.app.state.session_factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(ElementSaveRequestRecord)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(ProposalBatchRecord)) == 0
    current = client.get(ROOT + f"/sessions/{session['id']}").json()
    assert current["draft"] == session["draft"] and current["revision"] == session["revision"]
    mapping = next(m for m in draft["mappings"] if m["type_id"] == owner)
    mapping["fields"][prop["name"]] = {"kind": "column", "source_id": "main", "column": "region"}
    corrected = client.post(endpoint, json=body)
    assert corrected.status_code == 200, corrected.text
    assert any(p["id"] == prop["id"] for p in corrected.json()["draft"]["properties"])
    assert {r.target_kind for r in human_rows(client, corrected.json())} == {"property", "mapping"}


def test_invalid_condition_is_rejected_without_records(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales", published=True)
    draft = deepcopy(session["draft"])
    rule = draft["rules"][0]
    rule["expression"] = "1 + 2"
    owner_id = rule["owner_id"]
    if rule["owner_kind"] == "property":
        owner_id = next(p for p in draft["properties"] if p["id"] == owner_id)["owner_type_id"]
    owner = next(o for o in draft["object_types"] if o["id"] == owner_id)
    response = submit(client, draft, session=session, target_id=owner["id"])
    assert response.status_code == 422, response.text
    assert "条件" in response.text
    assert human_rows(client, session) == []


def test_other_session_publication_is_not_imported_by_save(client):
    old, other = create_session(client), create_session(client)
    current = submit(client, edited(other, "另一会话发布"), session=other).json()
    assert publish(client, current).status_code == 200
    draft = deepcopy(old["draft"])
    draft["object_types"][0]["display_name"] = "旧会话标题"
    saved = submit(client, draft, session=old)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    [row] = human_rows(client, result)
    assert row.before_json == old["draft"]["object_types"][0]
    assert row.after_json["description"] == row.before_json["description"]
    assert result["base_version_id"] == old["base_version_id"]
    assert published_snapshot(client)["object_types"][0]["description"] == "另一会话发布"


def test_publish_then_save_starts_new_human_batch_and_resets_count(client):
    initial = create_session(client)
    first = submit(client, edited(initial, "待发布"), session=initial).json()
    [old] = human_rows(client, first)
    published = publish(client, first)
    assert published.status_code == 200, published.text
    current = published.json()["session"]
    assert current["unpublished_change_count"] == 0
    second = submit(client, edited(current, "新的修改"), session=current).json()
    [row] = human_rows(client, second)
    assert row.batch_id != old.batch_id
    assert row.before_json == current["draft"]["object_types"][0]


def test_patch_settings_rejects_draft_and_put_is_removed(client):
    session = create_session(client)
    endpoint = ROOT + f"/sessions/{session['id']}"
    body = {"revision": session["revision"], "draft": session["draft"]}
    assert client.put(endpoint, json=body).status_code == 405
    assert client.patch(endpoint, json=body).status_code == 422
    response = client.patch(endpoint, json={"revision": session["revision"], "title": "仅改设置", "mode": "chat"})
    assert response.status_code == 200, response.text
    assert response.json()["draft"] == session["draft"]
    assert response.json()["title"] == "仅改设置" and response.json()["mode"] == "chat"
    assert client.post(ROOT + "/element-saves", json={}).status_code == 404
    assert client.post(ROOT + "/element-saves/preview", json={}).status_code == 404


def test_personal_session_unique_visible_and_concurrent_creation(client):
    with ThreadPoolExecutor(max_workers=3) as workers:
        responses = list(workers.map(lambda _: client.get(ROOT + "/sessions/personal"), range(3)))
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    session = responses[0].json()
    assert session["unpublished_change_count"] == 0
    assert session["id"] in {s["id"] for s in client.get(ROOT + "/sessions").json()["items"]}
    assert submit(client, edited(session, "会话外编辑"), session=session).status_code == 200


def test_personal_session_unique_per_workspace_and_user(client):
    from types import SimpleNamespace

    from ontofoundry_api.services.sessions import personal_session

    wid = client.post("/api/v1/workspaces", json={"name": "虚构协作空间", "slug": "fiction-personal"}).json()["id"]
    first = client.get(ROOT + "/sessions/personal").json()
    other_space = client.get(f"/api/v1/workspaces/{wid}/sessions/personal").json()
    assert first["id"] != other_space["id"]
    with client.app.state.session_factory() as db:
        user_id = str(uuid4())
        db.add(UserRecord(id=user_id, username="fiction-personal", display_name="虚构协作者"))
        db.commit()
        other_user = personal_session(first["workspace_id"], db, SimpleNamespace(id=user_id))
        assert other_user["id"] != first["id"]
        assert other_user["workspace_id"] == first["workspace_id"]


def test_session_contract_artifact_matches_actual_responses(client):
    schema = session_writes_schema()
    path = Path(__file__).parents[1] / "src/ontofoundry_api/contracts/ontofoundry.session-writes.v1.schema.json"
    assert json.loads(path.read_text()) == schema
    Draft202012Validator.check_schema(schema)
    session = client.get(ROOT + "/sessions/personal").json()
    validator = Draft202012Validator({"$ref": "#/$defs/SessionRead", "$defs": schema["$defs"]})
    validator.validate(session)
    saved = submit(client, edited(session, "契约校验"), session=session)
    assert saved.status_code == 200, saved.text
    validator.validate(saved.json())


def test_migration_preserves_existing_sessions_and_enforces_personal_uniqueness():
    path = Path(__file__).parents[1] / "src/ontofoundry_api/alembic/versions/20261116_000001_human_saves.py"
    spec = importlib.util.spec_from_file_location("human_saves", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20261113_000001"
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(36), primary_key=True))
    sa.Table("modeling_sessions", metadata,
             sa.Column("id", sa.String(36), primary_key=True),
             sa.Column("workspace_id", sa.String(36), nullable=False),
             sa.UniqueConstraint("workspace_id", "id", name="uq_modeling_sessions_ws_id"))
    metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(sa.text("INSERT INTO users (id) VALUES ('fiction-user')"))
        db.execute(sa.text("INSERT INTO modeling_sessions (id, workspace_id) VALUES ('old', 'fiction-space')"))
        migration.op = Operations(MigrationContext.configure(db))
        migration.upgrade()
        assert db.execute(sa.text("SELECT personal_owner_id, human_batch_id FROM modeling_sessions WHERE id = 'old'")).one() == (None, None)
        db.execute(sa.text("INSERT INTO modeling_sessions (id, workspace_id, personal_owner_id) VALUES ('personal', 'fiction-space', 'fiction-user')"))
        with db.begin_nested(), pytest.raises(sa.exc.IntegrityError):
            db.execute(sa.text("INSERT INTO modeling_sessions (id, workspace_id, personal_owner_id) VALUES ('duplicate', 'fiction-space', 'fiction-user')"))
        assert "element_save_requests" in sa.inspect(db).get_table_names()
        migration.downgrade()
        assert "element_save_requests" not in sa.inspect(db).get_table_names()
        assert {c["name"] for c in sa.inspect(db).get_columns("modeling_sessions")} == {"id", "workspace_id"}
    engine.dispose()


def test_concurrent_same_save_key_returns_one_result(client):
    session = create_session(client)
    candidate = edited(session, "并发幂等保存")
    body = save_body(client, session, candidate, target_id=candidate["object_types"][0]["id"])
    endpoint = ROOT + f"/sessions/{session['id']}/element-saves"
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: client.post(endpoint, json=body), range(2)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert results[0].json() == results[1].json()
    assert len(human_rows(client, session)) == 1
    with client.app.state.session_factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(ElementSaveRequestRecord)) == 1


def test_manual_evidence_author_is_stamped_and_immutable(client):
    session = create_session(client)
    candidate = edited(session, "人工证据")
    candidate["object_types"][0]["evidence"].append({
        "kind": "manual", "id": str(uuid4()), "note": "虚构业务说明",
        "created_by": "fiction-forged-user", "created_at": "2000-01-01T00:00:00Z",
    })
    response = submit(client, candidate, session=session)
    assert response.status_code == 200, response.text
    saved = response.json()
    evidence = saved["draft"]["object_types"][0]["evidence"][-1]
    assert evidence["created_by"] == DEV_USER_ID and not evidence["created_at"].startswith("2000-")
    revised = deepcopy(saved["draft"])
    revised["object_types"][0]["evidence"][-1]["note"] = "修改原证据"
    rejected = submit(client, revised, session=saved)
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "MANUAL_EVIDENCE_IMMUTABLE"


def test_human_proposal_undo_restores_first_before_image(client):
    initial = create_session(client)
    first = submit(client, edited(initial, "第一次修改"), session=initial).json()
    second = submit(client, edited(first, "第二次修改"), session=first).json()
    [row] = human_rows(client, second)
    response = decide(client, second, [(row.id, "reject")])
    assert response.status_code == 200, response.text
    restored = response.json()["session"]
    assert restored["draft"] == initial["draft"]
    assert restored["unpublished_change_count"] == 0


def test_failure_after_proposal_write_rolls_everything_back(client, monkeypatch):
    from ontofoundry_api.services import changes
    from ontofoundry_api.services.errors import ServiceError

    session = create_session(client)
    record_changes = changes._record_human_changes

    def interrupted(*args):
        record_changes(*args)
        raise ServiceError("虚构事务中断", code="FICTION_INTERRUPTED", status_code=422)

    monkeypatch.setattr(changes, "_record_human_changes", interrupted)
    rejected = submit(client, edited(session, "应回滚的修改"), session=session)
    assert rejected.status_code == 422 and rejected.json()["error"]["code"] == "FICTION_INTERRUPTED"
    with client.app.state.session_factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(ProposalBatchRecord)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(ProposalItemRecord)) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(ElementSaveRequestRecord)) == 0
        item = db.get(ModelingSessionRecord, session["id"])
        assert item.human_batch_id is None and item.revision == session["revision"]
        assert item.draft_json == session["draft"]


def test_concurrent_distinct_keys_have_one_revision_winner(client):
    session = create_session(client)
    candidates = [edited(session, value) for value in ("并发甲", "并发乙")]
    bodies = [save_body(client, session, draft, target_id=draft["object_types"][0]["id"]) for draft in candidates]
    endpoint = ROOT + f"/sessions/{session['id']}/element-saves"
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda body: client.post(endpoint, json=body), bodies))
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert len(human_rows(client, session)) == 1
    with client.app.state.session_factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(ElementSaveRequestRecord)) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(ProposalBatchRecord)) == 1


def test_successful_save_receipt_survives_session_abandon(client):
    session = create_session(client)
    candidate = edited(session, "已保存后放弃")
    body = save_body(client, session, candidate, target_id=candidate["object_types"][0]["id"])
    endpoint = ROOT + f"/sessions/{session['id']}/element-saves"
    saved = client.post(endpoint, json=body)
    assert saved.status_code == 200, saved.text
    assert client.post(ROOT + f"/sessions/{session['id']}/abandon").status_code == 200
    replay = client.post(endpoint, json=body)
    assert replay.status_code == 200 and replay.json() == saved.json()
    abandoned = client.get(ROOT + f"/sessions/{session['id']}").json()
    rejected = submit(client, edited(abandoned, "放弃后的新修改"), session=abandoned)
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "SESSION_ABANDONED"


def test_partial_resave_preserves_human_atomic_group(client):
    initial = create_session(client)
    candidate = edited(initial, "整组修改")
    candidate["properties"][0]["description"] = "属性修改"
    response = submit(client, candidate, session=initial)
    assert response.status_code == 200, response.text
    first = response.json()
    rows = human_rows(client, first)
    assert len(rows) == 2 and rows[0].atomic_group_id == rows[1].atomic_group_id
    group = rows[0].atomic_group_id
    assert group is not None

    response = submit(client, edited(first, "再次修改对象"), session=first)
    assert response.status_code == 200, response.text
    second = response.json()
    assert {row.atomic_group_id for row in human_rows(client, second)} == {group}
    undone = decide(client, second, [(rows[0].id, "reject")])
    assert undone.status_code == 200, undone.text
    assert len(undone.json()["results"]) == 2
    assert undone.json()["session"]["draft"] == initial["draft"]


def test_overlapping_human_saves_merge_existing_atomic_groups(client):
    initial = create_session(client)
    candidate = edited(initial, "第一组对象")
    candidate["properties"][0]["description"] = "第一组属性"
    response = submit(client, candidate, session=initial)
    assert response.status_code == 200, response.text
    first = response.json()
    candidate = deepcopy(first["draft"])
    for name in ("fiction_grade", "fiction_note"):
        candidate["properties"].append({
            "id": str(uuid4()), "owner_type_id": candidate["object_types"][0]["id"],
            "name": name, "value_kind": "string",
        })
    response = submit(client, candidate, session=first)
    assert response.status_code == 200, response.text
    second = response.json()
    assert len({row.atomic_group_id for row in human_rows(client, second)}) == 2

    candidate = deepcopy(second["draft"])
    for prop in candidate["properties"]:
        if prop["name"] in {"label", "fiction_grade"}:
            prop["description"] = "合并两组的修改"
    response = submit(client, candidate, session=second)
    assert response.status_code == 200, response.text
    third = response.json()
    rows = human_rows(client, third)
    assert len(rows) == 4 and len({row.atomic_group_id for row in rows}) == 1
    assert rows[0].atomic_group_id is not None
    undone = decide(client, third, [(rows[0].id, "reject")])
    assert undone.status_code == 200, undone.text
    assert len(undone.json()["results"]) == 4
    assert undone.json()["session"]["draft"] == initial["draft"]


def test_partial_return_to_original_detaches_rejected_member_and_dependencies(client):
    initial = create_session(client)
    candidate = edited(initial, "临时对象描述")
    candidate["properties"][0]["description"] = "保留的属性修改"
    response = submit(client, candidate, session=initial)
    assert response.status_code == 200, response.text
    first = response.json()
    rows = human_rows(client, first)
    obj = next(row for row in rows if row.target_kind == "object_type")
    prop = next(row for row in rows if row.target_kind == "property")
    # Cover dependency edges retained by an earlier stored proposal revision.
    with client.app.state.session_factory() as db:
        db.add(ProposalItemDependencyRecord(
            workspace_id=first["workspace_id"], session_id=first["id"],
            batch_id=obj.batch_id, item_id=prop.id, depends_on_item_id=obj.id,
        ))
        db.commit()
    candidate = deepcopy(first["draft"])
    candidate["object_types"][0] = deepcopy(initial["draft"]["object_types"][0])
    response = submit(client, candidate, session=first)
    assert response.status_code == 200, response.text
    second = response.json()
    rows = {row.id: row for row in human_rows(client, second)}
    assert rows[obj.id].status == "rejected" and rows[obj.id].atomic_group_id is None
    assert rows[prop.id].status == "accepted"
    with client.app.state.session_factory() as db:
        assert db.scalar(sa.select(ProposalItemDependencyRecord.item_id).where(
            sa.or_(ProposalItemDependencyRecord.item_id == obj.id,
                   ProposalItemDependencyRecord.depends_on_item_id == obj.id),
        )) is None
    undone = decide(client, second, [(prop.id, "reject")])
    assert undone.status_code == 200, undone.text
    assert len(undone.json()["results"]) == 1
    assert undone.json()["session"]["draft"] == initial["draft"]


@pytest.mark.parametrize("legacy_owner", [False, True])
def test_abandoned_personal_session_is_replaced_and_old_receipt_replays(client, legacy_owner):
    initial = client.get(ROOT + "/sessions/personal").json()
    candidate = edited(initial, "放弃前保存")
    body = save_body(client, initial, candidate, target_id=candidate["object_types"][0]["id"])
    endpoint = ROOT + f"/sessions/{initial['id']}/element-saves"
    saved = client.post(endpoint, json=body)
    assert saved.status_code == 200, saved.text
    assert client.post(ROOT + f"/sessions/{initial['id']}/abandon").status_code == 200
    if legacy_owner:
        with client.app.state.session_factory() as db:
            db.get(ModelingSessionRecord, initial["id"]).personal_owner_id = DEV_USER_ID
            db.commit()
    with ThreadPoolExecutor(max_workers=3) as workers:
        responses = list(workers.map(lambda _: client.get(ROOT + "/sessions/personal"), range(3)))
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    replacement = responses[0].json()
    assert replacement["id"] != initial["id"] and replacement["abandoned_at"] is None
    assert submit(client, edited(replacement, "新个人会话修改"), session=replacement).status_code == 200
    replay = client.post(endpoint, json=body)
    assert replay.status_code == 200 and replay.json() == saved.json()
    with client.app.state.session_factory() as db:
        assert db.get(ModelingSessionRecord, initial["id"]).personal_owner_id is None
        assert db.get(ModelingSessionRecord, initial["id"]).abandoned_at is not None


def test_new_conversation_keeps_human_batch_decidable(client, monkeypatch):
    from test_agent_conversation_bff import _configure, _install_transport

    initial = create_session(client)
    response = client.patch(ROOT + f"/sessions/{initial['id']}", json={"revision": initial["revision"], "mode": "chat"})
    assert response.status_code == 200, response.text
    initial = response.json()
    agent = seed_batch(client, initial, [update("object_type", initial["draft"]["object_types"][1], description="智能体修改")])
    response = decide(client, initial, [(agent["items"][0]["id"], "accept")])
    assert response.status_code == 200, response.text
    initial = response.json()["session"]
    response = submit(client, edited(initial, "人工修改"), session=initial)
    assert response.status_code == 200, response.text
    saved = response.json()
    [row] = human_rows(client, saved)
    _configure(client)

    def handler(request):
        if request.url.path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "fiction-topic"})
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/fiction-context.json"})
        return httpx.Response(200, json={"task_id": "fiction-task", "task_status": "finished"})

    _install_transport(monkeypatch, handler)
    response = client.post(ROOT + f"/sessions/{saved['id']}/agent-conversation/messages", json={"content": "检查已有修改", "metadata": {}})
    assert response.status_code == 202, response.text
    with client.app.state.session_factory() as db:
        session = db.get(ModelingSessionRecord, saved["id"])
        assert session.run_manifest_json["source_session_revision"] > saved["revision"]
    human_detail = client.get(ROOT + f"/sessions/{saved['id']}/proposal-batches/{row.batch_id}").json()
    assert human_detail["read_only"] is False
    agent_detail = client.get(ROOT + f"/sessions/{saved['id']}/proposal-batches/{agent['id']}").json()
    assert agent_detail["read_only"] is True
    current = client.get(ROOT + f"/sessions/{saved['id']}").json()
    response = decide(client, current, [(row.id, "reject")])
    assert response.status_code == 200, response.text
    assert response.json()["session"]["draft"] == initial["draft"]


def test_human_save_runs_candidate_validation_once(client, monkeypatch):
    from ontofoundry_api.services import changes

    initial = create_session(client)
    trial_apply = changes.trial_apply
    calls = []

    def counted(*args, **kwargs):
        calls.append(kwargs.get("accepting", False))
        return trial_apply(*args, **kwargs)

    monkeypatch.setattr(changes, "trial_apply", counted)
    response = submit(client, edited(initial, "一次检查"), session=initial)
    assert response.status_code == 200, response.text
    assert calls == [True]


def test_noop_save_keeps_revision_and_caches_idempotent_response(client):
    initial = create_session(client)
    stored = client.get(ROOT + f"/sessions/{initial['id']}").json()
    body = save_body(client, initial, initial["draft"], target_id=initial["draft"]["object_types"][0]["id"])
    endpoint = ROOT + f"/sessions/{initial['id']}/element-saves"
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["revision"] == initial["revision"] and first["draft"] == initial["draft"]
    assert first["updated_at"] == stored["updated_at"]
    assert human_rows(client, initial) == []
    # The editor opened before the no-op can still save using its original revision.
    saved = submit(client, edited(initial, "之后的修改"), session=initial)
    assert saved.status_code == 200, saved.text
    replay = client.post(endpoint, json=body)
    assert replay.status_code == 200 and replay.json() == first
    mismatch = client.post(endpoint, json={**body, "draft": edited(initial, "不同内容")})
    assert mismatch.status_code == 409 and mismatch.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
