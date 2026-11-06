"""Pinned scope, table evidence conversion, receipt size and repair stability."""

import json
from copy import deepcopy

import pytest
from sqlalchemy import select
from test_linked_tables import link, register
from test_proposal_submit import running_submit
from test_t1_proposal_contract import create as legacy_create
from test_t1_proposal_contract import items_only
from test_t3_proposal_results import stored
from test_table_structure_receipts import change_column

from ontofoundry_api.db_models import MaterialRecord, ModelingSessionRecord
from ontofoundry_api.domain.evidence import check_material_evidence
from ontofoundry_api.domain.table_reading import column_line, table_header
from ontofoundry_api.services.dataset_sources import linked_table_details
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.modeling_input import linked_tables_payload


def create(ref, kind, after):
    return items_only([legacy_create(ref, kind, after)])[0]


def pinned(client):
    connection = register(client, ["fiction_orders", "fiction_stores", "fiction_unused"])
    session, manifest, url, headers = running_submit(client)
    with client.app.state.session_factory() as db:
        details = linked_table_details(
            db,
            session["workspace_id"],
            [
                link(connection, t)
                for t in ("fiction_orders", "fiction_stores", "fiction_unused")
            ],
        )
        _, body = linked_tables_payload(details)
        tables = json.loads(body)["tables"]
        row = db.get(ModelingSessionRecord, session["id"])
        row.run_manifest_json = {
            **row.run_manifest_json,
            "table_snapshot": {"tables": tables},
            "input_files": {"tables_file": "uploads/pinned.json", "tables_sha256": "fixed"},
        }
        db.commit()
    return session, url, headers, connection, tables


def dataset(connection, table="fiction_orders", **kwargs):
    return create(
        "source",
        "dataset",
        {
            "name": "fiction_source",
            "display_name": "虚构来源",
            "connection_id": connection,
            "schema_name": "retail",
            "table_name": table,
            **kwargs,
        },
    )


def test_converts_both_evidence_locations_and_includes_only_used_tables(client):
    session, url, headers, connection, tables = pinned(client)
    evidence = {
        "kind": "table",
        "ref": "t2.amount",
        "quote": column_line(tables[1], tables[1]["columns"][1]),
    }
    item = create(
        "concept",
        "object_type",
        {"name": "fiction_store", "evidence": [deepcopy(evidence)]},
    )
    item["evidence"] = [{"kind": "table", "ref": "t2", "quote": table_header(tables[1])}]
    payload = {"items": [dataset(connection), item]}
    report = client.post(url, json=payload, headers=headers).json()
    assert report["passed"], report
    items = stored(client, session["id"])[1]
    concept = next(i for i in items if i.client_ref == "concept")
    with client.app.state.session_factory() as db:
        receipts = db.scalars(
            select(MaterialRecord).where(MaterialRecord.origin == "table_receipt")
        ).all()
        assert len(receipts) == 1
        lookup = material_lookup(db, client.app.state.settings, session["workspace_id"])
        lines = lookup(receipts[0].id)[1]
        body = "\n".join(lines)
        assert (
            "fiction_orders" in body
            and "fiction_stores" in body
            and "fiction_unused" not in body
        )
        for entry in [*concept.evidence_json, *concept.after_json["evidence"]]:
            assert entry["kind"] == "material" and entry["material_id"] == receipts[0].id
            line = entry["locator"]["line_start"]
            assert lines[line - 1] == entry["quote"]
            check_material_evidence(entry, lookup, "虚构证据")
        assert (
            concept.after_json["evidence"][0]["locator"]["heading"]
            == "retail.fiction_stores.amount"
        )
    # Idempotency uses the original shorthand payload's digest.
    assert (
        client.post(url, json=payload, headers=headers).json()["batch_id"]
        == report["batch_id"]
    )


@pytest.mark.parametrize("ref", ["t99", "t1.missing"])
def test_unknown_reference_is_a_structured_error_and_creates_no_receipt(client, ref):
    session, url, headers, _, _ = pinned(client)
    item = create("concept", "object_type", {"name": "fiction_concept"})
    item["evidence"] = [{"kind": "table", "ref": ref, "quote": "未知"}]
    report = client.post(url, json={"items": [item]}, headers=headers).json()
    assert not report["passed"] and report["errors"][0]["code"] == "TABLE_REF_UNKNOWN"
    assert (
        "有效引用" in report["errors"][0]["message"]
        and "t1" in report["errors"][0]["message"]
    )
    assert stored(client, session["id"])[0] == []
    with client.app.state.session_factory() as db:
        assert (
            db.scalar(
                select(MaterialRecord).where(MaterialRecord.origin == "table_receipt")
            )
            is None
        )


def test_repair_reuses_pinned_columns_after_metadata_sync(client):
    session, url, headers, connection, tables = pinned(client)
    entry = {"kind": "table", "ref": "t1.amount", "quote": "错误引文"}
    item = create(
        "concept", "object_type", {"name": "fiction_concept", "evidence": [entry]}
    )
    assert not client.post(url, json={"items": [item]}, headers=headers).json()["passed"]
    change_column(client, connection, "BIGINT")
    entry["quote"] = column_line(tables[0], tables[0]["columns"][1])
    report = client.post(url, json={"items": [item]}, headers=headers).json()
    assert report["passed"] and report["repair_used"] == 1, report
    with client.app.state.session_factory() as db:
        manifest = db.get(ModelingSessionRecord, session["id"]).run_manifest_json
        assert manifest["input_files"]["tables_file"] == "uploads/pinned.json"
        assert (
            manifest["table_snapshot"]["tables"][0]["columns"][1]["type"] == "DECIMAL(12,2)"
        )
        receipt = db.scalar(
            select(MaterialRecord).where(MaterialRecord.origin == "table_receipt")
        )
        assert "DECIMAL(12,2)" in "\n".join(
            material_lookup(db, client.app.state.settings, session["workspace_id"])(
                receipt.id
            )[1]
        )


@pytest.mark.parametrize("query", [False, True])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_scope_rejects_new_or_updated_table_and_query_sources(client, query, operation):
    session, url, headers, connection, tables = pinned(client)
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        row.run_manifest_json = {
            **row.run_manifest_json,
            "table_snapshot": {"tables": tables[:1]},
        }
        db.commit()
    item = dataset(connection, "fiction_stores")
    if query:
        item["after"].update(
            source_kind="query",
            table_name=None,
            schema_name=None,
            query_sql="WITH s AS (SELECT id FROM retail.fiction_stores) SELECT id FROM s",
        )
    if operation == "update":
        old = (
            deepcopy(session["draft"]["datasets"][0])
            if session["draft"]["datasets"]
            else None
        )
        # Scope checks run before target resolution; use a known draft target.
        if old is None:
            from uuid import uuid4

            old = {**item["after"], "id": str(uuid4())}
            with client.app.state.session_factory() as db:
                row = db.get(ModelingSessionRecord, session["id"])
                manifest = deepcopy(row.run_manifest_json)
                manifest["pinned_draft"]["datasets"].append(old)
                row.run_manifest_json = manifest
                db.commit()
        item.update(operation="update", target_id=old["id"])
        item.pop("client_ref", None)
    report = client.post(url, json={"items": [item]}, headers=headers).json()
    assert (
        not report["passed"] and report["errors"][0]["code"] == "TABLE_NOT_IN_SESSION_SCOPE"
    ), report
    message = report["errors"][0]["message"]
    assert "虚构来源" in message and "fiction_stores" in message and "未交付" in message


def test_query_cte_only_uses_in_scope_physical_tables(client):
    _, url, headers, connection, _ = pinned(client)
    item = dataset(
        connection,
        None,
        source_kind="query",
        schema_name=None,
        query_sql="WITH s AS (SELECT id FROM retail.fiction_orders) SELECT id FROM s",
        columns=[{"name": "id", "physical_type": "VARCHAR(16)"}],
    )
    report = client.post(url, json={"items": [item]}, headers=headers).json()
    assert report["passed"], report
