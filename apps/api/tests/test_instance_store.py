"""IS-01–12: independent persistence, optimistic decisions and publication."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_core1_mcp import call
from test_element_save import submit
from test_modeling import ONTOLOGY, ROOT, create_session, preview, publish, save
from test_t4_proposal_decisions import create, decide, seed_batch

from ontofoundry_api.contracts.instances import InstanceBaseline
from ontofoundry_api.contracts.proposals import (
    ParsedBatch,
    ProposalContractError,
    RunContext,
    parse_result,
)
from ontofoundry_api.db_models import (
    DocumentInstanceRecord,
    InstanceHistoryRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.instances import instance_hash
from ontofoundry_api.services import instance_store
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposals import proposal_context, store_batch
from ontofoundry_api.services.workspaces import DEV_USER_ID


def baseline(client, session):
    response = client.get(ROOT + f"/sessions/{session['id']}/instance-baseline")
    assert response.status_code == 200, response.text
    InstanceBaseline.model_validate(response.json())
    return response.json()


def instance_update(entry, **changes):
    return {
        "operation": "update",
        "target_kind": entry["target_kind"],
        "target_id": entry["target_id"],
        "expected_target_hash": entry["hash"],
        "before": entry["element"],
        "after": {**{k: v for k, v in entry["element"].items() if k != "id"}, **changes},
    }


def accept_all(client, session, items):
    batch = seed_batch(client, session, items)
    response = decide(client, session, [(i["id"], "accept") for i in batch["items"]])
    assert response.status_code == 200, response.text
    return response.json()["session"], batch


def create_instance(session, name="月湾客户"):
    typ = next(o for o in session["draft"]["object_types"] if o["name"] == "customer")
    return create(
        "customer-" + uuid4().hex[:8],
        "material_object",
        {"type_id": typ["id"], "values": {"label": name}, "evidence": []},
    )


def test_instance_only_accept_is_live_without_ontology_version(client):
    session = create_session(client)
    original = client.get(ONTOLOGY + "/version").json()
    session, batch = accept_all(client, session, [create_instance(session)])
    assert (
        "material_objects" not in session["draft"]
        and "material_links" not in session["draft"]
    )
    assert client.get(ONTOLOGY + "/version").json() == original
    entry = next(
        i
        for i in baseline(client, session)["items"]
        if i["target_id"] == batch["items"][0]["target_id"]
    )
    assert entry["state"] == "active" and entry["revision"] == 1
    live = client.get(ROOT + "/instances").json()
    InstanceBaseline.model_validate(live)
    assert entry["target_id"] in {i["target_id"] for i in live["items"]}
    assert all(i["state"] == "active" for i in live["items"])
    rows = client.get(ONTOLOGY + "/objects", params={"q": "月湾客户"}).json()
    assert rows["items"][0]["id"] == entry["target_id"] and rows["data_mode"] == "live"
    assert (
        call(client, "search_objects", {"q": "月湾客户"})["structuredContent"]["items"][0][
            "id"
        ]
        == entry["target_id"]
    )
    assert (
        call(
            client,
            "get_object",
            {"id": entry["target_id"], "include": ["properties", "evidence"]},
        )["structuredContent"]["item"]["id"]
        == entry["target_id"]
    )


def test_update_undo_history_and_revision_aba_protection(client):
    session = create_session(client)
    entry = baseline(client, session)["items"][0]
    old_hash = entry["hash"]
    session, batch = accept_all(
        client, session, [instance_update(entry, values={"label": "新名称"})]
    )
    newer = baseline(client, session)["items"][0]
    assert newer["revision"] == entry["revision"] + 1
    response = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    final = baseline(client, response.json()["session"])["items"][0]
    assert final["element"] == entry["element"] and final["hash"] != old_hash
    history = client.get(
        ROOT + f"/instances/material_object/{entry['target_id']}/history"
    ).json()["items"]
    assert [i["operation"] for i in history] == ["create", "update", "undo"]
    assert [i["revision"] for i in history] == [1, 2, 3]
    assert history[1]["proposal_item_id"] == batch["items"][0]["id"]
    assert history[-1]["after"]["element"] == entry["element"]


def test_two_sessions_cannot_overwrite_or_undo_each_other(client):
    first, other = create_session(client), create_session(client)
    entry = baseline(client, first)["items"][0]
    one = seed_batch(
        client, first, [instance_update(entry, values={"label": "第一位修改"})]
    )
    two = seed_batch(
        client, other, [instance_update(entry, values={"label": "另一位修改"})]
    )
    response = decide(client, first, [(one["items"][0]["id"], "accept")])
    assert response.status_code == 200, response.text
    first = response.json()["session"]
    refused = decide(client, other, [(two["items"][0]["id"], "accept")])
    assert (
        refused.status_code == 409 and refused.json()["error"]["code"] == "PROPOSAL_TARGET_CHANGED"
    )
    assert decide(client, other, [(two["items"][0]["id"], "reject")]).status_code == 200
    current = baseline(client, other)["items"][0]
    other, _ = accept_all(
        client, other, [instance_update(current, values={"label": "重新审阅后修改"})]
    )
    refused = decide(client, first, [(one["items"][0]["id"], "reject")])
    assert (
        refused.status_code == 409
        and refused.json()["error"]["code"] == "PROPOSAL_UNDO_CONFLICT"
    )
    assert (
        baseline(client, other)["items"][0]["element"]["values"]["label"]
        == "重新审阅后修改"
    )


def staged_batch(client, session):
    return accept_all(
        client,
        session,
        [
            create(
                "warehouse",
                "object_type",
                {"name": "fictional_warehouse", "display_name": "虚构仓库"},
            ),
            create(
                "code",
                "property",
                {
                    "owner_type_id": {"client_ref": "warehouse"},
                    "name": "code",
                    "value_kind": "string",
                },
            ),
            create(
                "warehouse-one",
                "material_object",
                {"type_id": {"client_ref": "warehouse"}, "values": {"code": "WH-A"}},
            ),
        ],
    )


def test_mixed_accept_stages_and_publish_activates_atomically(client):
    session, batch = staged_batch(client, create_session(client))
    entry = next(
        e
        for e in baseline(client, session)["items"]
        if e["target_id"] == batch["items"][-1]["target_id"]
    )
    assert entry["state"] == "staged"
    assert client.get(ONTOLOGY + f"/objects/doc.{entry['target_id']}").status_code == 404
    staged = client.get(ROOT + f"/sessions/{session['id']}/instances").json()
    assert [i["target_id"] for i in staged["items"]] == [entry["target_id"]]
    assert not any(
        i["target_id"] == entry["target_id"]
        for i in baseline(client, create_session(client))["items"]
    )
    published = publish(client, session)
    assert published.status_code == 200, published.text
    updated = baseline(client, published.json()["session"])
    assert (
        next(e for e in updated["items"] if e["target_id"] == entry["target_id"])["state"]
        == "active"
    )
    assert client.get(ONTOLOGY + f"/objects/doc.{entry['target_id']}").status_code == 200


@pytest.mark.parametrize("change", ["new_property", "changed_property", "changed_relation"])
def test_existing_type_definition_changes_stage_instances_and_both_link_ends(
    client, change
):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    customer = next(t for t in draft["object_types"] if t["name"] == "customer")
    if change == "new_property":
        draft["properties"].append(
            {
                "id": str(uuid4()),
                "owner_type_id": customer["id"],
                "name": "region",
                "value_kind": "string",
            }
        )
        values = {"label": "试验客户", "region": "北湾"}
    elif change == "changed_property":
        next(p for p in draft["properties"] if p["name"] == "label")["value_kind"] = (
            "integer"
        )
        values = {"label": 100}
    else:
        draft["link_types"][0]["source_type_id"] = customer["id"]
        values = {"label": "关系试验客户"}
    session = save(client, session, draft).json()
    proposals = [
        create(
            "new-customer", "material_object", {"type_id": customer["id"], "values": values}
        )
    ]
    if change == "changed_relation":
        proposals.append(
            create(
                "new-link",
                "material_link",
                {
                    "type_id": draft["link_types"][0]["id"],
                    "source_id": {"client_ref": "new-customer"},
                    "target_id": baseline(client, session)["items"][0]["target_id"],
                },
            )
        )
    session, batch = accept_all(client, session, proposals)
    targets = {i["target_id"] for i in batch["items"]}
    entries = [i for i in baseline(client, session)["items"] if i["target_id"] in targets]
    assert entries[-1]["state"] == "staged"


def test_abandon_is_explicit_idempotent_and_audited(client):
    session, batch = staged_batch(client, create_session(client))
    assert client.get(ROOT + f"/sessions/{session['id']}/instances").json()["items"]
    other = create_session(client)
    # A different session can publish descriptions while this session stays staged.
    other["draft"]["object_types"][0]["description"] = "另一会话的说明"
    other = save(client, other, other["draft"]).json()
    assert publish(client, other).status_code == 200
    response = client.post(ROOT + f"/sessions/{session['id']}/abandon")
    assert response.status_code == 200, response.text
    assert (
        client.post(ROOT + f"/sessions/{session['id']}/abandon").json() == response.json()
    )
    assert not client.get(ROOT + f"/sessions/{session['id']}/instances").json()["items"]
    with client.app.state.session_factory() as db:
        assert (
            db.get(DocumentInstanceRecord, batch["items"][-1]["target_id"]).state
            == "deleted"
        )
        rows = instance_store.history(
            db,
            session["workspace_id"],
            "material_object",
            batch["items"][-1]["target_id"],
            session_id=session["id"],
        )
        assert rows[-1].operation == "abandon_session" and rows[-1].actor == DEV_USER_ID
    assert client.get(ONTOLOGY + "/objects").json()["items"]  # Active instances survive.


@pytest.mark.parametrize("change", ["rename", "type", "delete_property", "delete_type"])
@pytest.mark.parametrize("route", ["session", "element"])
def test_shared_publish_blocks_interpreting_definition_changes(client, change, route):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    customer = next(o for o in draft["object_types"] if o["name"] == "customer")
    prop = next(p for p in draft["properties"] if p["name"] == "label")
    if change == "rename":
        prop["name"] = "customer_label"
    elif change == "type":
        prop["value_kind"] = "integer"
    else:
        draft["properties"] = [p for p in draft["properties"] if p["id"] != prop["id"]]
        customer["title_property_id"] = None
        if change == "delete_type":
            draft["object_types"] = [
                o for o in draft["object_types"] if o["id"] != customer["id"]
            ]
            draft["link_types"] = []
    if route == "session":
        session = save(client, session, draft).json()
        body = preview(client, session).json()
        assert body["affected_instances"] and not body["validation"]["publishable"]
        response = publish(client, session)
    else:
        response = submit(client, draft, target_id=customer["id"])
    expected = (
        "ELEMENT_NOT_FOUND"
        if route == "element" and change == "delete_type"
        else "INSTANCE_REFERENCES_BLOCK_PUBLISH"
    )
    assert response.status_code == (422 if expected == "ELEMENT_NOT_FOUND" else 409), (
        response.text
    )
    assert response.json()["error"]["code"] == expected
    assert client.get(ONTOLOGY + "/version").json()["version"] == 1


@pytest.mark.parametrize("route", ["session", "element"])
def test_description_display_name_and_synonyms_do_not_block(client, route):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    draft["properties"][0].update(
        description="只改说明", display_name="客户称呼", synonyms=["称谓"]
    )
    if route == "session":
        response = publish(client, save(client, session, draft).json())
    else:
        response = submit(client, draft)
    assert response.status_code == 200, response.text


def test_new_instance_invalidates_preview_and_rest_mcp_cursor(client):
    session = create_session(client)
    accept_all(client, create_session(client), [create_instance(session, "翻页客户")])
    previous_preview = preview(client, session).json()
    rest = client.get(ONTOLOGY + "/objects", params={"limit": 1}).json()
    mcp = call(client, "search_objects", {"limit": 1})["structuredContent"]
    assert rest["next_cursor"] and mcp["next_cursor"]
    accept_all(client, create_session(client), [create_instance(session, "又一位客户")])
    response = client.post(
        ROOT + f"/sessions/{session['id']}/publish",
        json={
            "expected_session_revision": session["revision"],
            "expected_current_version_id": previous_preview["current_version_id"],
            "expected_merged_snapshot_sha256": previous_preview["merged_snapshot_sha256"],
            "expected_instance_change_sequence": previous_preview[
                "instance_change_sequence"
            ],
        },
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "PREVIEW_OUTDATED"
    )
    assert (
        client.get(
            ONTOLOGY + "/objects", params={"limit": 1, "cursor": rest["next_cursor"]}
        ).status_code
        == 422
    )
    assert call(client, "search_objects", {"limit": 1, "cursor": mcp["next_cursor"]})[
        "isError"
    ]


def test_fixed_version_filters_new_values_and_relations(client):
    old_version = client.get(ONTOLOGY + "/version").json()["version_id"]
    session = create_session(client)
    customer = next(o for o in session["draft"]["object_types"] if o["name"] == "customer")
    session["draft"]["properties"].append(
        {
            "id": str(uuid4()),
            "owner_type_id": customer["id"],
            "name": "region",
            "value_kind": "string",
        }
    )
    session = publish(client, save(client, session, session["draft"]).json()).json()[
        "session"
    ]
    session, _ = accept_all(
        client,
        session,
        [
            create(
                "new-fields",
                "material_object",
                {"type_id": customer["id"], "values": {"region": "月湾"}},
            )
        ],
    )
    live = client.get(ONTOLOGY + "/objects").json()
    historical = client.get(
        ONTOLOGY + "/objects", params={"version_id": old_version}
    ).json()
    assert len(live["items"]) == 2 and len(historical["items"]) == 1
    assert historical["filtered_count"] == 1 and "已过滤 1 条" in historical["warnings"][0]
    from dataclasses import replace

    from ontofoundry_api.api.auth import Principal
    from ontofoundry_api.services.mcp_ontology import invoke

    principal = Principal(DEV_USER_ID, "dev:admin", "admin", None)
    with client.app.state.session_factory() as db:
        result = invoke(
            db,
            session["workspace_id"],
            replace(principal, pinned_version_id=old_version),
            "search_objects",
            {},
            client.app.state.settings,
        )
    assert result["filtered_count"] == 1 and len(result["items"]) == 1


def test_material_evidence_deleted_instances_and_history_prevent_deletion(client):
    session = create_session(client)
    material = client.post(
        ROOT + "/materials",
        params={"name": "月湾客户说明.md"},
        content="月湾客户已登记".encode(),
    ).json()
    evidence = {
        "id": str(uuid4()),
        "kind": "material",
        "material_id": material["id"],
        "material_sha256": material["sha256"],
        "locator": {"line_start": 1, "line_end": 1},
        "quote": "月湾客户",
    }
    proposal = create_instance(session)
    proposal["after"]["evidence"] = [evidence]
    session, batch = accept_all(client, session, [proposal])
    entry = next(
        i
        for i in baseline(client, session)["items"]
        if i["target_id"] == batch["items"][0]["target_id"]
    )
    from ontofoundry_api.services.material_usage import material_usage

    with client.app.state.session_factory() as db:
        usage = material_usage(db, session["workspace_id"], {material["id"]})[
            material["id"]
        ]
        assert usage.material_objects == 1 and "实例证据" in usage.references
        instance_store.write(
            db,
            session["workspace_id"],
            session["id"],
            "material_object",
            entry["target_id"],
            None,
            expected_revision=entry["revision"],
            actor=DEV_USER_ID,
        )
        db.commit()
        usage = material_usage(db, session["workspace_id"], {material["id"]})[
            material["id"]
        ]
        assert not usage.can_delete and "实例历史" in usage.references
    assert client.delete(ROOT + f"/materials/{material['id']}").status_code == 409


def test_direct_store_rejects_stale_revision_and_preserves_manual_evidence(client):
    session = create_session(client)
    entry = baseline(client, session)["items"][0]
    after = deepcopy(entry["element"])
    after["evidence"] = [
        {
            "id": str(uuid4()),
            "kind": "manual",
            "note": "人工核对",
            "created_by": "forged-author",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]
    with client.app.state.session_factory() as db:
        instance_store.write(
            db,
            session["workspace_id"],
            session["id"],
            "material_object",
            entry["target_id"],
            after,
            expected_revision=entry["revision"],
            actor=DEV_USER_ID,
        )
        db.commit()
        stored = instance_store.baseline(db, session["workspace_id"], session["id"])[
            "items"
        ][0]
        assert stored["element"]["evidence"][0]["created_by"] == DEV_USER_ID
        assert (
            stored["element"]["evidence"][0]["created_at"]
            != after["evidence"][0]["created_at"]
        )
        with pytest.raises(ServiceError, match="其他操作修改") as error:
            instance_store.write(
                db,
                session["workspace_id"],
                session["id"],
                "material_object",
                entry["target_id"],
                after,
                expected_revision=entry["revision"],
                actor=DEV_USER_ID,
            )
        assert error.value.code == "INSTANCE_REVISION_CHANGED"
        db.rollback()
        amended = deepcopy(stored["element"])
        amended["evidence"][0]["note"] = "试图改写"
        with pytest.raises(ServiceError) as error:
            instance_store.write(
                db,
                session["workspace_id"],
                session["id"],
                "material_object",
                entry["target_id"],
                amended,
                expected_revision=stored["revision"],
                actor=DEV_USER_ID,
            )
        assert error.value.code == "MANUAL_EVIDENCE_IMMUTABLE"


def test_invalidated_run_cannot_store_results(client):
    session = create_session(client)
    with client.app.state.session_factory() as db:
        with pytest.raises(ServiceError) as error:
            store_batch(
                db,
                workspace_id=session["workspace_id"],
                session_id=session["id"],
                task_id="old-run",
                manifest={"invalidated": "INSTANCE_STORE_CUTOVER"},
                parsed=ParsedBatch(str(uuid4()), "a" * 64, []),
                settings=client.app.state.settings,
            )
        assert error.value.code == "RUN_CONTEXT_INVALIDATED"


def test_baseline_context_and_parser_enforce_revision_hash(client):
    from ontofoundry_api.services.proposals import proposal_header

    session = create_session(client)
    b = baseline(client, session)
    manifest = {
        "run_token": "fictional-run",
        "workspace_id": session["workspace_id"],
        "session_id": session["id"],
        "base_version_id": session["base_version_id"],
        "base_version_sha256": session["base_version_sha256"],
        "source_session_revision": session["revision"],
        "source_draft_sha256": session["draft_sha256"],
        "instance_baseline": b,
    }
    context = proposal_context(manifest, session["draft"])
    assert context["instance_baseline"] == b
    assert b["items"][0]["target_id"] not in context["element_hashes"]
    run = RunContext(
        **{k: v for k, v in context["run"].items() if k != "schema_version"},
        draft=session["draft"],
        instance_baseline=b,
    )
    payload = {
        **proposal_header(manifest),
        "items": [instance_update(b["items"][0], values={"label": "解析更新"})],
    }
    parsed = parse_result(json.dumps(payload).encode(), run, lambda _: None)
    assert parsed.items[0].expected_instance_revision == b["items"][0]["revision"]
    payload["items"][0]["expected_target_hash"] = instance_hash(
        b["items"][0]["element"], b["items"][0]["revision"] + 1
    )
    with pytest.raises(ProposalContractError) as error:
        parse_result(json.dumps(payload).encode(), run, lambda _: None)
    assert error.value.code == "TARGET_HASH_MISMATCH"


def test_run_credentials_have_all_fixed_read_scopes(client):
    from starlette.requests import Request

    from ontofoundry_api.api.auth import _run_principal
    from ontofoundry_api.services.run_credentials import RunGrant, issue

    session = create_session(client)
    token = issue(
        client.app.state.settings.session_secret,
        RunGrant(
            session["workspace_id"],
            session["id"],
            "fictional-token",
            session["base_version_id"],
            DEV_USER_ID,
        ),
    )
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        row.dataagent_run_token, row.task_status = "fictional-token", "running"
        db.commit()
        principal = _run_principal(
            Request({"type": "http", "app": client.app}), db, token, session["workspace_id"]
        )
    assert principal.scopes == {"ontology:read", "instances:read", "mappings:read"}


def test_instance_migration_strips_content_rehashes_and_invalidates_old_context(client):
    session = create_session(client)
    from core1_fixtures import EXAMPLES_DIR
    from test_core1_import_flow import confirm as import_confirm
    from test_core1_import_flow import preview as import_preview

    from ontofoundry_api.db_models import ImportRecord

    pending_import = import_preview(
        client, session["workspace_id"], (EXAMPLES_DIR / "09-empty.json").read_bytes()
    )
    with client.app.state.session_factory() as db:
        original_report = deepcopy(
            db.get(ImportRecord, pending_import["import_id"]).report_json
        )
    path = (
        Path(__file__).parents[1]
        / "src/ontofoundry_api/alembic/versions/20261021_000002_instance_store.py"
    )
    spec = importlib.util.spec_from_file_location("instance_cutover", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        legacy = {
            **row.draft_json,
            "material_objects": [{"id": str(uuid4())}],
            "material_links": [],
        }
        row.draft_json = legacy
        row.run_manifest_json = {"pinned_draft": legacy, "result_contract": "proposals"}
        row.task_status, row.dataagent_run_token = "running", "old-run"
        version = db.get(OntologyVersionRecord, session["base_version_id"])
        version.snapshot_json = legacy
        db.commit()
    with client.app.state.engine.begin() as connection:
        # Reconstruct the immediately preceding schema, then run the actual DDL.
        for table in (
            "instance_history",
            "instance_evidence",
            "instance_links",
            "document_instances",
        ):
            connection.exec_driver_sql(f"DROP TABLE {table}")
        for table, columns in {
            "workspaces": ["instance_change_sequence"],
            "modeling_sessions": ["abandoned_at", "abandoned_by"],
            "proposal_items": ["expected_instance_revision", "accepted_instance_revision"],
        }.items():
            for column in columns:
                connection.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {column}")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        imported = db.get(ImportRecord, pending_import["import_id"])
        assert imported.converted_json == {}
        assert imported.preview_json["invalidated"] == "INSTANCE_STORE_CUTOVER"
        assert imported.report_json == original_report
        assert (
            "material_objects" not in row.draft_json
            and "material_links" not in row.draft_json
        )
        assert row.draft_sha256 == snapshot_sha256(row.draft_json)
        assert row.base_version_sha256 == snapshot_sha256(row.draft_json)
        assert (
            "pinned_draft" not in row.run_manifest_json
            and row.run_manifest_json["invalidated"] == "INSTANCE_STORE_CUTOVER"
        )
        assert row.task_status == "cancelled" and row.dataagent_run_token is None
        assert (
            db.scalar(sa.select(sa.func.count()).select_from(DocumentInstanceRecord)) == 0
        )
        version = db.get(OntologyVersionRecord, row.base_version_id)
        assert "material_objects" not in version.snapshot_json
        assert version.sha256 != session["base_version_sha256"]
    assert {
        "document_instances",
        "instance_links",
        "instance_evidence",
        "instance_history",
    } <= set(sa.inspect(client.app.state.engine).get_table_names())
    refused = import_confirm(client, session["workspace_id"], pending_import)
    assert (
        refused.status_code == 409
        and refused.json()["error"]["code"] == "IMPORT_INVALIDATED"
    )


def test_relation_reads_and_endpoint_delete_preserve_evidence_and_history(client):
    session = create_session(client)
    customer = baseline(client, session)["items"][0]
    order = next(t for t in session["draft"]["object_types"] if t["name"] == "order")
    link = session["draft"]["link_types"][0]
    session, batch = accept_all(
        client,
        session,
        [
            create(
                "order-one",
                "material_object",
                {"type_id": order["id"], "values": {"order_no": "O-001"}},
            ),
            create(
                "buyer-one",
                "material_link",
                {
                    "type_id": link["id"],
                    "source_id": {"client_ref": "order-one"},
                    "target_id": customer["target_id"],
                },
            ),
        ],
    )
    result = client.get(
        ONTOLOGY + f"/objects/doc.{customer['target_id']}/neighborhood"
    ).json()
    assert len(result["links"]) == 1 and len(result["objects"]) == 2
    assert (
        call(client, "get_object", {"id": customer["target_id"], "include": ["adjacency"]})[
            "structuredContent"
        ]["item"]["adjacency"]["total"]
        == 1
    )
    with client.app.state.session_factory() as db:
        instance_store.write(
            db,
            session["workspace_id"],
            session["id"],
            "material_object",
            customer["target_id"],
            None,
            expected_revision=customer["revision"],
            actor=DEV_USER_ID,
        )
        db.commit()
        history = instance_store.history(
            db, session["workspace_id"], "material_link", batch["items"][1]["target_id"]
        )
        assert history[-1].operation == "endpoint_deleted"
        assert history[-1].after["state"] == "deleted"
    assert client.get(ONTOLOGY + f"/objects/doc.{customer['target_id']}").status_code == 404


def test_mixed_batch_failure_rolls_back_definition_instances_history_and_decision(client):
    session = create_session(client)
    batch = seed_batch(
        client,
        session,
        [
            create("warehouse", "object_type", {"name": "fictional_warehouse"}),
            create("one", "material_object", {"type_id": {"client_ref": "warehouse"}}),
        ],
    )
    from ontofoundry_api.db_models import ProposalItemRecord

    with client.app.state.session_factory() as db:
        # Simulate an intervening semantic edit after result validation.
        item = db.get(ProposalItemRecord, batch["items"][1]["id"])
        item.after_json = {**item.after_json, "values": {"unknown": "值"}}
        db.commit()
        before_history = db.scalar(
            sa.select(sa.func.count()).select_from(InstanceHistoryRecord)
        )
    response = decide(client, session, [(i["id"], "accept") for i in batch["items"]])
    assert response.status_code == 422, response.text
    with client.app.state.session_factory() as db:
        assert db.get(ModelingSessionRecord, session["id"]).draft_json == session["draft"]
        assert db.get(DocumentInstanceRecord, batch["items"][1]["target_id"]) is None
        assert (
            db.scalar(sa.select(sa.func.count()).select_from(InstanceHistoryRecord))
            == before_history
        )
        assert {db.get(ProposalItemRecord, i["id"]).status for i in batch["items"]} == {
            "pending"
        }


def test_parallel_sessions_compare_and_set_on_postgres(pg_client):
    from concurrent.futures import ThreadPoolExecutor

    first, second = create_session(pg_client), create_session(pg_client)
    entry = baseline(pg_client, first)["items"][0]
    batches = [
        seed_batch(pg_client, s, [instance_update(entry, values={"label": str(index)})])
        for index, s in enumerate((first, second))
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda pair: decide(
                    pg_client, pair[0], [(pair[1]["items"][0]["id"], "accept")]
                ),
                zip((first, second), batches, strict=True),
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert baseline(pg_client, first)["items"][0]["revision"] == entry["revision"] + 1


def test_delete_proposal_cascades_relations_and_undo_restores_them(client):
    session = create_session(client)
    customer = baseline(client, session)["items"][0]
    order = next(t for t in session["draft"]["object_types"] if t["name"] == "order")
    session, relation_batch = accept_all(
        client,
        session,
        [
            create(
                "order-to-delete",
                "material_object",
                {"type_id": order["id"], "values": {"order_no": "O-DEL"}},
            ),
            create(
                "relation-to-delete",
                "material_link",
                {
                    "type_id": session["draft"]["link_types"][0]["id"],
                    "source_id": {"client_ref": "order-to-delete"},
                    "target_id": customer["target_id"],
                },
            ),
        ],
    )
    deletion = {**instance_update(customer), "operation": "delete", "after": None}
    session, batch = accept_all(client, session, [deletion])
    assert not any(
        i["target_kind"] == "material_link" for i in baseline(client, session)["items"]
    )
    undone = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert undone.status_code == 200, undone.text
    result = baseline(client, undone.json()["session"])
    assert any(
        i["target_id"] == relation_batch["items"][1]["target_id"] for i in result["items"]
    )
    assert client.get(
        ONTOLOGY + f"/objects/doc.{customer['target_id']}/neighborhood"
    ).json()["links"]


def test_relation_endpoint_definition_change_blocks_both_publish_paths(client):
    session = create_session(client)
    customer = baseline(client, session)["items"][0]
    order = next(t for t in session["draft"]["object_types"] if t["name"] == "order")
    session, _ = accept_all(
        client,
        session,
        [
            create(
                "order-linked", "material_object", {"type_id": order["id"], "values": {}}
            ),
            create(
                "buyer-linked",
                "material_link",
                {
                    "type_id": session["draft"]["link_types"][0]["id"],
                    "source_id": {"client_ref": "order-linked"},
                    "target_id": customer["target_id"],
                },
            ),
        ],
    )
    draft = deepcopy(session["draft"])
    draft["link_types"][0]["source_type_id"] = customer["element"]["type_id"]
    direct = submit(client, draft, kind="link_type", target_id=draft["link_types"][0]["id"])
    assert (
        direct.status_code == 409
        and direct.json()["error"]["code"] == "INSTANCE_REFERENCES_BLOCK_PUBLISH"
    )
    session = save(client, session, draft).json()
    assert (
        publish(client, session).json()["error"]["code"]
        == "INSTANCE_REFERENCES_BLOCK_PUBLISH"
    )


def test_element_save_preview_lists_instances_and_checks_sequence(client):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    next(p for p in draft["properties"] if p["name"] == "label")["name"] = "customer_name"
    body = {
        "target_kind": "object_type",
        "target_id": draft["object_types"][0]["id"],
        "expected_current_version_id": session["base_version_id"],
        "draft": draft,
    }
    response = client.post(ROOT + "/element-saves/preview", json=body)
    assert response.status_code == 200, response.text
    impact = response.json()
    assert impact["affected_instances"]
    accept_all(client, session, [create_instance(session)])
    refused = client.post(
        ROOT + "/element-saves",
        json={
            **body,
            "expected_instance_change_sequence": impact["instance_change_sequence"],
        },
    )
    assert (
        refused.status_code == 409 and refused.json()["error"]["code"] == "PREVIEW_OUTDATED"
    )


def test_abandoned_session_cannot_write_and_staged_history_is_scoped(client):
    session, batch = staged_batch(client, create_session(client))
    target_id = batch["items"][-1]["target_id"]
    endpoint = ROOT + f"/instances/material_object/{target_id}/history"
    assert client.get(endpoint).json()["items"] == []
    assert client.get(endpoint, params={"session_id": session["id"]}).json()["items"]
    assert client.post(ROOT + f"/sessions/{session['id']}/abandon").status_code == 200
    current = client.get(ROOT + f"/sessions/{session['id']}").json()
    candidate = deepcopy(current["draft"])
    candidate["object_types"][0]["description"] = "放弃后的写入"
    response = submit(client, candidate, session=current)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "SESSION_ABANDONED"
    )
