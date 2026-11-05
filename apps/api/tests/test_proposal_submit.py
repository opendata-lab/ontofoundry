"""Submitting a run's result checks and stores it in one step (SC-05)."""

import json
from pathlib import Path

import pytest
from run_helpers import install_download, reconcile, submit
from sqlalchemy import select
from test_modeling import ROOT
from test_t1_proposal_contract import context, create, parse
from test_t1_proposal_contract import result as contract_result
from test_t3_proposal_results import proposals_run, result, some_items, stored

from ontofoundry_api.contracts.proposal_submit import ProposalSubmitResponse
from ontofoundry_api.contracts.proposals import ProposalContractError
from ontofoundry_api.db_models import ModelingSessionRecord, ProposalBatchRecord
from ontofoundry_api.services.run_credentials import RunGrant, issue


def mixed_items(draft):
    items = some_items(draft)[:2]
    items[0]["after"]["name"] = draft["object_types"][0]["name"]
    items += [create("independent", "object_type", {"name": "fictional_shipment"})]
    # Dependents appear before their prerequisites in the submitted file.
    return [items[1], items[0], items[2]]


def test_invalid_group_rejects_the_entire_batch():
    ctx = context()
    with pytest.raises(ProposalContractError, match="候选图校验未通过"):
        parse(contract_result(ctx, mixed_items(ctx.draft)), ctx)


def test_invalid_batch_creates_no_proposals(client, monkeypatch):
    session, manifest = proposals_run(client)
    install_download(monkeypatch)
    submit(client, session["id"], result(manifest, mixed_items(session["draft"])))
    assert reconcile(client, session["id"]) == "failed_permanent"
    batches, items, _ = stored(client, session["id"])
    assert batches == [] and items == []


def running_submit(client):
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
    url = f"/api/v1/ontology/workspaces/{session['workspace_id']}/runs/{manifest['run_token']}/proposals"
    return session, manifest, url, {"Authorization": "Bearer " + credential}


def finish(client, session_id, status="finished"):
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session_id).task_status = status
        db.commit()


def test_failed_submit_stores_nothing_and_the_run_settles_without_a_batch(client, monkeypatch):
    session, manifest, url, headers = running_submit(client)
    payload = result(manifest, mixed_items(session["draft"]))
    response = client.post(url, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    report = ProposalSubmitResponse.model_validate(response.json())
    assert not report.passed and report.errors and report.reviewable_count == 0
    with client.app.state.session_factory() as db:
        assert not list(db.scalars(select(ProposalBatchRecord)))
        assert db.get(ModelingSessionRecord, session["id"]).draft_json == session["draft"]
    finish(client, session["id"])
    install_download(monkeypatch)
    assert reconcile(client, session["id"]) == "failed_permanent"
    assert stored(client, session["id"])[0] == []


def test_passed_submit_is_stored_and_the_run_settles_done(client, monkeypatch):
    session, manifest, url, headers = running_submit(client)
    payload = result(manifest, some_items(session["draft"]))
    report = client.post(url, json=payload, headers=headers).json()
    count = len(payload["items"])
    assert report["passed"] and report["batch_id"] and report["reviewable_count"] == count
    batches, items, _ = stored(client, session["id"])
    assert len(batches) == 1 and len(items) == count
    finish(client, session["id"])
    install_download(monkeypatch)
    assert reconcile(client, session["id"]) == "done"
    # A retry after a lost response gets the receipt, even once the run ended.
    again = client.post(url, json=payload, headers=headers).json()
    assert again["passed"] and again["batch_id"] == report["batch_id"]
    payload["items"] = payload["items"][:1]
    other = client.post(url, json=payload, headers=headers).json()
    assert not other["passed"] and other["errors"][0]["code"] == "RUN_ALREADY_SUBMITTED"


def test_stopping_after_submit_keeps_the_batch(client):
    from ontofoundry_api.services.modeling_runs import _persist_task_projection

    session, manifest, url, headers = running_submit(client)
    payload = result(manifest, some_items(session["draft"]))
    assert client.post(url, json=payload, headers=headers).json()["passed"]
    _persist_task_projection(
        client.app.state.session_factory, session["id"],
        task_id="task-model-1", upstream_status="suspended", detail="已停止",
    )
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        assert row.task_status == "cancelled" and row.result_state == "done"
        assert not (row.run_manifest_json or {}).get("invalidated")
    assert len(stored(client, session["id"])[1]) == len(payload["items"])


def test_platform_counts_repair_rounds_on_rejected_submissions(client):
    session, manifest, url, headers = running_submit(client)
    bad = result(manifest, mixed_items(session["draft"]))

    def post(payload):
        return client.post(url, json=payload, headers=headers).json()

    first = post(bad)
    assert not first["passed"] and first["repair_used"] == 0 and first["repair_limit"] == 2
    assert post(bad)["repair_used"] == 0  # the same content again is not a repair
    for expected in (1, 2):
        bad["items"][0]["reason"] = f"fictional repair {expected}"
        assert post(bad)["repair_used"] == expected
    bad["items"][0]["reason"] = "fictional repair 3"
    exhausted = post(bad)
    assert exhausted["errors"][0]["code"] == "REPAIR_BUDGET_EXHAUSTED"
    assert exhausted["repair_used"] == 2
    assert stored(client, session["id"])[0] == []


def test_a_passing_submission_after_repairs_is_stored(client):
    session, manifest, url, headers = running_submit(client)
    assert not client.post(url, json=result(manifest, mixed_items(session["draft"])), headers=headers).json()["passed"]
    report = client.post(url, json=result(manifest, some_items(session["draft"])), headers=headers).json()
    assert report["passed"] and report["repair_used"] == 0
    assert len(stored(client, session["id"])[0]) == 1


def test_rejection_carries_the_structured_diagnostics():
    from ontofoundry_api.services.errors import DatasetSourceError
    from ontofoundry_api.services.proposal_submit import _reason

    exc = DatasetSourceError("数据集来源未就绪", details={"diagnostics": [
        {"code": "SOURCE_NOT_REGISTERED", "path": "/query_sql", "message": "来源不在连接允许的业务范围"}]})
    assert _reason(exc) == "数据集来源未就绪；[SOURCE_NOT_REGISTERED] /query_sql 来源不在连接允许的业务范围"


def test_an_invalidated_run_cannot_submit(client):
    session, manifest, url, headers = running_submit(client)
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        row.run_manifest_json = {**row.run_manifest_json, "invalidated": True}
        db.commit()
    report = client.post(url, json=result(manifest, some_items(session["draft"])), headers=headers).json()
    assert report["errors"][0]["code"] == "RUN_CONTEXT_INVALIDATED"
    assert stored(client, session["id"])[0] == []


def test_submit_contract_errors_then_pass(client):
    session, manifest, url, headers = running_submit(client)
    payload = result(manifest, some_items(session["draft"]))
    mismatched = {**payload, "run_token": "different-run"}
    report = client.post(url, json=mismatched, headers=headers).json()
    assert not report["passed"] and report["reviewable_count"] == 0
    assert report["errors"][0]["code"] == "RESULT_CONTEXT_MISMATCH"
    assert report["errors"][0]["message"].startswith("错误 [RESULT_CONTEXT_MISMATCH]")
    assert (
        client.post(url, content=b"{", headers=headers).json()["errors"][0]["code"]
        == "RESULT_JSON_INVALID"
    )
    assert client.post(url, json=payload, headers=headers).json()["passed"]


@pytest.mark.parametrize("uses_current_value", [False, True])
def test_value_type_expression_submit_outcome(
    client, monkeypatch, uses_current_value
):
    session, manifest, url, headers = running_submit(client)
    variable = "member_level" if uses_current_value else "level"
    payload = result(manifest, [
        create("level_type", "value_type", {"name": "member_level", "value_kind": "string"}),
        create("level_constraint", "rule", {
            "name": "member_level_constraint", "owner_kind": "value_type",
            "owner_id": {"client_ref": "level_type"}, "rule_kind": "constraint",
            "expression": f"{variable} IN ('普通', '金卡')",
        }),
    ])
    response = client.post(url, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["passed"] is uses_current_value
    if not uses_current_value:
        assert "值类型约束必须引用当前值 member_level" in report["errors"][0]["message"]
    finish(client, session["id"])
    install_download(monkeypatch)
    assert reconcile(client, session["id"]) == ("done" if uses_current_value else "failed_permanent")
    batches, items, _ = stored(client, session["id"])
    assert len(batches) == int(uses_current_value)
    assert len(items) == (2 if uses_current_value else 0)


@pytest.mark.parametrize(
    "scope", ["different-run", "different-space", "expired", "no-token"]
)
def test_submit_honors_run_authorization(client, scope):
    session, manifest, url, headers = running_submit(client)
    if scope == "different-run":
        url = url.replace(manifest["run_token"], "other")
    elif scope == "different-space":
        url = url.replace(session["workspace_id"], "00000000-0000-4000-8000-000000000000")
    elif scope == "expired":
        finish(client, session["id"])
        report = client.post(url, json=result(manifest, []), headers=headers).json()
        assert report["errors"][0]["code"] == "RUN_NOT_ACTIVE"
        return
    else:
        headers = {}
    assert client.post(url, json=result(manifest, []), headers=headers).status_code == 401


def test_submit_schema_is_generated_from_model():
    root = Path(__file__).resolve().parents[1] / "src/ontofoundry_api/contracts"
    for model, name in [(ProposalSubmitResponse, "proposal-submit")]:
        schema = json.loads((root / f"ontofoundry.{name}.v1.schema.json").read_text())
        schema.pop("$schema")
        assert schema == model.model_json_schema()


def test_invalid_join_rejects_the_whole_batch():
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
    with pytest.raises(ProposalContractError):
        parse(contract_result(ctx, items), ctx)


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


def test_failed_run_is_reported_by_its_status_not_a_notice(client):
    session, _ = proposals_run(client)
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.task_status = "failed"
        record.task_detail = "本轮没有写出结果文件"
        db.commit()
    detail = client.get(ROOT + f"/sessions/{session['id']}").json()
    assert "proposal_notice" not in detail
    assert detail["task_status"] == "failed" and detail["task_detail"] == "本轮没有写出结果文件"


def test_every_broken_item_is_reported_in_one_submission(client):
    # SC-06: two independent mistakes cost one repair round, not two.
    session, manifest, url, headers = running_submit(client)
    items = some_items(session["draft"])
    missing = "00000000-0000-4000-8000-00000000abcd"
    broken = [
        {**items[1], "target_id": missing},
        {**items[2], "target_id": "00000000-0000-4000-8000-00000000abce"},
    ]
    report = client.post(url, json=result(manifest, [items[0], *broken]), headers=headers).json()
    assert not report["passed"]
    assert len(report["errors"]) == 2, report["errors"]
    assert "/items/1" in report["errors"][0]["message"] and "/items/2" in report["errors"][1]["message"]
    # One round is counted for the whole rejected submission.
    assert report["repair_used"] == 0
