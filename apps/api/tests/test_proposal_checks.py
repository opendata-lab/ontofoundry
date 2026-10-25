"""Partial proposal ingestion and run-scoped checks share the same diagnostics."""

import json
from pathlib import Path

import pytest
from run_helpers import install_download, reconcile
from sqlalchemy import select
from test_modeling import ROOT
from test_t1_proposal_contract import context, create, parse
from test_t1_proposal_contract import result as contract_result
from test_t3_proposal_results import proposals_run, result, some_items, stored

from ontofoundry_api.contracts.proposal_checks import (
    ProposalCheckResponse,
    ProposalRunNotice,
)
from ontofoundry_api.db_models import ModelingSessionRecord, ProposalBatchRecord
from ontofoundry_api.services.run_credentials import RunGrant, issue


def mixed_items(draft):
    items = some_items(draft)[:2]
    items[0]["after"]["name"] = draft["object_types"][0]["name"]
    items += [create("independent", "object_type", {"name": "fictional_shipment"})]
    # Dependents appear before their prerequisites in the submitted file.
    return [items[1], items[0], items[2]]


def test_invalid_group_and_transitive_dependents_do_not_poison_independent_items():
    ctx = context()
    items = mixed_items(ctx.draft)
    items.insert(
        0,
        {
            **create("leaf", "object_type", {"name": "fictional_leaf"}),
            "depends_on": ["po-no"],
        },
    )
    parsed = parse(contract_result(ctx, items), ctx)
    assert [i.status for i in parsed.items] == ["unacceptable"] * 3 + ["pending"]
    assert all(i.status_reason for i in parsed.items[:3])
    assert "依赖不可接受" in parsed.items[0].status_reason
    assert not parsed.items[-1].status_reason


def test_partial_ingestion_persists_diagnostics_and_refuses_acceptance(client, monkeypatch):
    session, manifest = proposals_run(client)
    install_download(monkeypatch, [result(manifest, mixed_items(session["draft"]))])
    assert reconcile(client, session["id"]) == "done"
    batches, items, _ = stored(client, session["id"])
    assert [i.status for i in items] == ["unacceptable", "unacceptable", "pending"]
    path = ROOT + f"/sessions/{session['id']}"
    detail = client.get(path + f"/proposal-batches/{batches[0].id}").json()
    assert detail["counts"]["unacceptable"] == 2
    assert detail["items"][0]["status_reason"] == items[0].status_reason
    notice = client.get(path).json()["proposal_notice"]
    assert notice["affected_count"] == 2 and notice["reviewable_count"] == 1
    refused = client.post(
        path + "/proposal-decisions",
        json={
            "idempotency_key": "blocked-check",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": items[0].id, "decision": "accept"}],
        },
    )
    assert refused.status_code == 409
    accepted = client.post(
        path + "/proposal-decisions",
        json={
            "idempotency_key": "independent-check",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": items[2].id, "decision": "accept"}],
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert any(
        o["name"] == "fictional_shipment"
        for o in accepted.json()["session"]["draft"]["object_types"]
    )


def running_check(client):
    session, manifest = proposals_run(client)
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        row.task_status = "running"
        credential = issue(
            client.app.state.settings.session_secret,
            RunGrant(
                session["workspace_id"],
                session["id"],
                manifest["run_token"],
                session["base_version_id"],
                row.created_by,
            ),
        )
        db.commit()
    url = f"/api/v1/ontology/workspaces/{session['workspace_id']}/runs/{manifest['run_token']}/proposal-check"
    return session, manifest, url, {"Authorization": "Bearer " + credential}


def test_check_is_read_only_and_reports_the_same_groups_as_ingestion(client, monkeypatch):
    session, manifest, url, headers = running_check(client)
    payload = result(manifest, mixed_items(session["draft"]))
    response = client.post(url, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    report = ProposalCheckResponse.model_validate(response.json())
    assert not report.passed and not report.contract_errors
    assert report.unacceptable_count == 2 and report.reviewable_count == 1
    assert {r for g in report.unacceptable_groups for r in g.client_refs} == {"po", "po-no"}
    assert all(
        g.reason.startswith("错误 [PROPOSAL_GROUP_UNACCEPTABLE]") and "下一步" in g.reason
        for g in report.unacceptable_groups
    )
    with client.app.state.session_factory() as db:
        assert not list(db.scalars(select(ProposalBatchRecord)))
        assert db.get(ModelingSessionRecord, session["id"]).draft_json == session["draft"]
        db.get(ModelingSessionRecord, session["id"]).task_status = "finished"
        db.commit()
    install_download(monkeypatch, [payload])
    assert reconcile(client, session["id"]) == "done"
    assert (
        sum(i.status == "unacceptable" for i in stored(client, session["id"])[1])
        == report.unacceptable_count
    )


def test_check_contract_errors_and_pass(client):
    session, manifest, url, headers = running_check(client)
    payload = result(manifest, some_items(session["draft"]))
    assert client.post(url, json=payload, headers=headers).json()["passed"]
    payload["run_token"] = "different-run"
    report = client.post(url, json=payload, headers=headers).json()
    assert not report["passed"] and not report["unacceptable_groups"]
    assert report["contract_errors"][0]["code"] == "RESULT_CONTEXT_MISMATCH"
    assert report["contract_errors"][0]["message"].startswith(
        "错误 [RESULT_CONTEXT_MISMATCH]"
    )
    assert (
        client.post(url, content=b"{", headers=headers).json()["contract_errors"][0]["code"]
        == "RESULT_JSON_INVALID"
    )


@pytest.mark.parametrize(
    "scope", ["different-run", "different-space", "expired", "no-token"]
)
def test_check_honors_run_mcp_authorization(client, scope):
    session, manifest, url, headers = running_check(client)
    if scope == "different-run":
        url = url.replace(manifest["run_token"], "other")
    elif scope == "different-space":
        url = url.replace(session["workspace_id"], "00000000-0000-4000-8000-000000000000")
    elif scope == "expired":
        with client.app.state.session_factory() as db:
            db.get(ModelingSessionRecord, session["id"]).task_status = "finished"
            db.commit()
    else:
        headers = {}
    assert client.post(url, json=result(manifest, []), headers=headers).status_code == 401


def test_check_schemas_are_generated_from_models():
    root = Path(__file__).resolve().parents[1] / "src/ontofoundry_api/contracts"
    for model, name in [
        (ProposalCheckResponse, "proposal-check"),
        (ProposalRunNotice, "proposal-run-notice"),
    ]:
        schema = json.loads((root / f"ontofoundry.{name}.v1.schema.json").read_text())
        schema.pop("$schema")
        assert schema == model.model_json_schema()


def test_invalid_join_group_is_isolated_from_other_groups():
    from uuid import uuid4

    from ontofoundry_api.domain.snapshot import empty_snapshot

    ctx = context(empty_snapshot(uuid4()))
    items = [
        create("source", "object_type", {"name": "fictional_source"}),
        create("target", "object_type", {"name": "fictional_target"}),
        create(
            "source_key",
            "property",
            {
                "name": "code",
                "owner_type_id": {"client_ref": "source"},
                "value_kind": "string",
            },
        ),
        create(
            "target_key",
            "property",
            {
                "name": "code",
                "owner_type_id": {"client_ref": "target"},
                "value_kind": "string",
            },
        ),
        create(
            "invalid_join",
            "link_type",
            {
                "name": "belongs_to",
                "source_type_id": {"client_ref": "source"},
                "target_type_id": {"client_ref": "target"},
                "multiplicity": "many_to_one",
                "data_join": {
                    "kind": "direct",
                    "source_property_ids": [{"client_ref": "source_key"}],
                    "target_property_ids": [{"client_ref": "target_key"}],
                },
            },
        ),
        {
            **create("downstream", "object_type", {"name": "fictional_downstream"}),
            "depends_on": ["invalid_join"],
        },
    ]
    parsed = parse(contract_result(ctx, list(reversed(items))), ctx)
    by_ref = {i.client_ref: i for i in parsed.items}
    assert by_ref["invalid_join"].status == by_ref["downstream"].status == "unacceptable"
    assert (
        "唯一" in by_ref["invalid_join"].status_reason
        or "标识" in by_ref["invalid_join"].status_reason
    )
    assert all(
        by_ref[ref].status == "pending"
        for ref in ("source", "target", "source_key", "target_key")
    )


def test_composite_identity_changes_are_atomic_and_reviewable():
    from uuid import uuid4

    from ontofoundry_api.domain.snapshot import empty_snapshot

    ctx = context(empty_snapshot(uuid4()))
    items = [create("fictional_line", "object_type", {"name": "fictional_line"})]
    for ref in ("order_code", "line_code"):
        items.append(
            create(
                ref,
                "property",
                {
                    "name": ref,
                    "owner_type_id": {"client_ref": "fictional_line"},
                    "value_kind": "string",
                    "identifier": True,
                    "required": True,
                    "unique": False,
                },
            )
        )
    parsed = parse(contract_result(ctx, list(reversed(items))), ctx)
    assert all(i.status == "pending" for i in parsed.items)
    assert parsed.items[0].atomic_group_id == parsed.items[1].atomic_group_id
    assert parsed.items[0].atomic_group_id is not None


def test_proposal_reason_migration_preserves_existing_items():
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    path = (
        Path(__file__).resolve().parents[1]
        / "src/ontofoundry_api/alembic/versions/20261023_000001_proposal_check_reason.py"
    )
    spec = importlib.util.spec_from_file_location("proposal_check_reason", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE proposal_items (id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO proposal_items VALUES ('fictional-proposal', 'pending')")
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(
                text("SELECT status, status_reason FROM proposal_items")
            ).one() == ("pending", None)
            migration.downgrade()
        assert {c["name"] for c in inspect(connection).get_columns("proposal_items")} == {
            "id",
            "status",
        }
        assert (
            connection.execute(text("SELECT status FROM proposal_items")).scalar_one()
            == "pending"
        )
    engine.dispose()


def test_failed_run_without_a_batch_still_has_a_conversation_notice(client):
    session, manifest = proposals_run(client)
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.task_status = "failed"
        record.task_detail = "本轮没有写出结果文件"
        db.commit()
    notice = client.get(ROOT + f"/sessions/{session['id']}").json()["proposal_notice"]
    assert notice == {
        "run_token": manifest["run_token"],
        "summary": "本轮没有写出结果文件",
        "affected_count": 0,
        "reviewable_count": 0,
    }
