"""Batch reads and instance lists share per-request work instead of repeating it per item."""

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, event, select, update
from test_modeling import ROOT, create_session
from test_t4_proposal_decisions import chain, seed_batch

from ontofoundry_api.db_models import (
    DocumentInstanceRecord,
    InstanceLinkRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    ProposalItemRecord,
    WorkspaceRecord,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services import instance_store
from ontofoundry_api.services.instance_duplicates import DuplicateCandidates
from ontofoundry_api.services.read_cache import session_reads
from ontofoundry_api.services.workspaces import DEV_USER_ID


def two_types(workspace_id):
    data = empty_snapshot(workspace_id)
    for name in ("order", "invoice"):
        type_id = str(uuid4())
        data["object_types"].append({"id": type_id, "name": name})
        data["properties"] += [
            {"id": str(uuid4()), "owner_type_id": type_id, "name": "code",
             "value_kind": "string", "identifier": True, "unique": True},
            {"id": str(uuid4()), "owner_type_id": type_id, "name": "title", "value_kind": "string"},
        ]
    order = data["object_types"][0]["id"]
    data["link_types"].append({"id": str(uuid4()), "name": "follows", "source_type_id": order,
                               "target_type_id": order, "multiplicity": "many_to_many"})
    return CoreDraft.model_validate(data).model_dump(mode="json")


def identifier_kinds(workspace_id):
    """门店订单 identified by two properties; 采购单 inherits 单据号 from 单据."""
    data = empty_snapshot(workspace_id)
    store_order, document, purchase = str(uuid4()), str(uuid4()), str(uuid4())
    data["object_types"] += [
        {"id": store_order, "name": "store_order"},
        {"id": document, "name": "document"},
        {"id": purchase, "name": "purchase", "extends": document},
    ]
    data["properties"] += [
        {"id": str(uuid4()), "owner_type_id": store_order, "name": name,
         "value_kind": "string", "identifier": True}
        for name in ("store_no", "order_no")
    ] + [{"id": str(uuid4()), "owner_type_id": document, "name": "doc_no",
          "value_kind": "string", "identifier": True, "unique": True}]
    return CoreDraft.model_validate(data).model_dump(mode="json")


def install(client, objects, links=(), make_draft=None):
    """A session and published version on `two_types`, with the given active instances."""
    session = create_session(client)
    draft = (make_draft or two_types)(session["workspace_id"])
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.draft_json, record.draft_sha256 = draft, snapshot_sha256(draft)
        version = db.get(OntologyVersionRecord, db.get(WorkspaceRecord, session["workspace_id"]).current_version_id)
        version.snapshot_json, version.sha256 = draft, snapshot_sha256(draft)
        for record_type in (InstanceLinkRecord, DocumentInstanceRecord):  # the fixture's sample data
            db.execute(delete(record_type).where(record_type.workspace_id == session["workspace_id"]))
        types = {t["name"]: t["id"] for t in draft["object_types"]}
        ids = []
        for type_name, values in objects:
            ids.append(str(uuid4()))
            db.add(DocumentInstanceRecord(
                id=ids[-1], workspace_id=session["workspace_id"], state="active", revision=1,
                created_by=DEV_USER_ID, updated_by=DEV_USER_ID, type_id=types[type_name], values=values))
        db.flush()
        for source, target in links:
            db.add(InstanceLinkRecord(
                id=str(uuid4()), workspace_id=session["workspace_id"], state="active", revision=1,
                created_by=DEV_USER_ID, updated_by=DEV_USER_ID, link_type_id=draft["link_types"][0]["id"],
                source_instance_id=ids[source], target_instance_id=ids[target]))
        db.commit()
    session_reads.clear()
    return session, types, ids


def proposed(type_id, values, operation="create"):
    return SimpleNamespace(target_kind="material_object", operation=operation,
                           after_json={"id": str(uuid4()), "type_id": type_id, "values": values})


def test_duplicates_match_by_type_and_identity_and_read_instances_once(client, monkeypatch):
    session, types, ids = install(client, [
        ("order", {"code": "A-1", "title": "第一单"}),
        ("order", {"code": "A-2"}),
        ("order", {"title": "没有编号"}),
        ("invoice", {"code": "A-1"}),
    ])
    reads = []
    original = instance_store.baseline
    monkeypatch.setattr(instance_store, "baseline", lambda *a, **k: reads.append(1) or original(*a, **k))
    with client.app.state.session_factory() as db:
        duplicates = DuplicateCandidates(db, session["workspace_id"], db.get(ModelingSessionRecord, session["id"]))
        assert duplicates(proposed(types["order"], {"code": "A-1"}, operation="update")) == []
        assert reads == []  # nothing to match yet, nothing read
        [match] = duplicates(proposed(types["order"], {"code": "A-1"}))
        assert match["id"] == ids[0] and match["type_id"] == types["order"]
        assert match["display_text"] == "A-1" and match["revision"] == 1 and match["expected_target_hash"]
        assert [m["id"] for m in duplicates(proposed(types["invoice"], {"code": "A-1"}))] == [ids[3]]
        assert duplicates(proposed(types["order"], {"code": "A-9"})) == []
        assert duplicates(proposed(types["order"], {"title": "没有编号"})) == []
    assert reads == [1]


def test_duplicates_use_composite_and_inherited_identifiers(client):
    session, types, ids = install(client, [
        ("store_order", {"store_no": "S01", "order_no": "1001"}),
        ("purchase", {"doc_no": "P-7"}),
    ], make_draft=identifier_kinds)
    with client.app.state.session_factory() as db:
        duplicates = DuplicateCandidates(db, session["workspace_id"], db.get(ModelingSessionRecord, session["id"]))
        order = types["store_order"]
        assert [m["id"] for m in duplicates(proposed(order, {"store_no": "S01", "order_no": "1001"}))] == [ids[0]]
        assert duplicates(proposed(order, {"store_no": "S02", "order_no": "1001"})) == []
        assert duplicates(proposed(order, {"order_no": "1001"})) == []  # incomplete identifier
        assert [m["id"] for m in duplicates(proposed(types["purchase"], {"doc_no": "P-7"}))] == [ids[1]]


def test_duplicates_stay_in_their_workspace_and_session(client):
    session, types, ids = install(client, [("order", {"code": "A-1"})])
    other_session = create_session(client)
    with client.app.state.session_factory() as db:
        other_space = WorkspaceRecord(id=str(uuid4()), slug="fiction-other", name="虚构白鹭空间", created_by=DEV_USER_ID)
        db.add(other_space)
        db.flush()
        for workspace_id, state, session_id in (
            (other_space.id, "active", None),  # same type and code, another workspace
            (session["workspace_id"], "staged", other_session["id"]),  # staged by another session
        ):
            db.add(DocumentInstanceRecord(
                id=str(uuid4()), workspace_id=workspace_id, state=state, session_id=session_id, revision=1,
                created_by=DEV_USER_ID, updated_by=DEV_USER_ID, type_id=types["order"], values={"code": "A-1"}))
        db.commit()
        session_reads.clear()
        duplicates = DuplicateCandidates(db, session["workspace_id"], db.get(ModelingSessionRecord, session["id"]))
        assert [m["id"] for m in duplicates(proposed(types["order"], {"code": "A-1"}))] == [ids[0]]


def test_visible_checks_each_link_against_its_endpoints(client):
    # Object 2 has a value of the wrong type and is filtered, so the link that ends at it is too.
    session, _, ids = install(
        client,
        [("order", {"code": "A-1"}), ("order", {"code": "A-2"}), ("order", {"code": 3})],
        links=[(0, 1), (1, 2), (0, 0)],
    )
    with client.app.state.session_factory() as db:
        model = instance_store.published_model(db, session["workspace_id"])
        result = instance_store.visible(db, session["workspace_id"], model)
    assert [o["target_id"] for o in result["objects"]] == sorted(ids[:2])
    ends = {(link["element"]["source_id"], link["element"]["target_id"]) for link in result["links"]}
    assert ends == {(ids[0], ids[1]), (ids[0], ids[0])}
    assert result["filtered_count"] == 2


def test_batch_read_reads_atomic_peers_in_one_query(client):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session))
    with client.app.state.session_factory() as db:
        items = {i.client_ref: i.id for i in db.scalars(
            select(ProposalItemRecord).where(ProposalItemRecord.batch_id == batch["id"]))}
        db.execute(update(ProposalItemRecord).where(ProposalItemRecord.batch_id == batch["id"])
                   .values(atomic_group_id=None))
        db.execute(update(ProposalItemRecord).where(ProposalItemRecord.id.in_([items["po"], items["po-no"]]))
                   .values(atomic_group_id="g1"))
        db.commit()
    statements = []
    engine = client.app.state.engine
    listen = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listen)
    try:
        read = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()
    finally:
        event.remove(engine, "before_cursor_execute", listen)
    # The same group id in another session never joins this batch's groups.
    other = create_session(client)
    other_batch = seed_batch(client, other, chain(other))
    with client.app.state.session_factory() as db:
        db.execute(update(ProposalItemRecord).where(ProposalItemRecord.batch_id == other_batch["id"])
                   .values(atomic_group_id="g1"))
        db.commit()
        foreign = set(db.scalars(select(ProposalItemRecord.id).where(ProposalItemRecord.batch_id == other_batch["id"])))
    again = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()
    assert not foreign & {d for i in again["items"] for d in i["dependency_group"]}
    peer_queries = [s for s in statements if "atomic_group_id IN" in s or "atomic_group_id =" in s]
    assert len(peer_queries) == 1
    by_ref = {i["client_ref"]: i for i in read["items"]}
    assert items["po-no"] in by_ref["po"]["dependency_group"]
    assert set(by_ref["po-no"]["dependency_group"]) >= {items["po"], items["po-no"]}
