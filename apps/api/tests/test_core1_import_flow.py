"""Real import HTTP lifecycle: no mutations until review and normal publication."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from core1_fixtures import EXAMPLES_DIR, example_names
from dataset_binding import bind_datasets
from sqlalchemy import select
from test_core1_ossie_import import dataset, document, entity, expression, ontology_map

from ontofoundry_api.db_models import (
    ImportRecord,
    MaterialRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
)
from ontofoundry_api.domain.evidence import check_material_evidence
from ontofoundry_api.services.materials_lookup import material_lookup


@pytest.fixture
def space(client):
    response = client.post(
        "/api/v1/workspaces",
        json={
            "name": "虚构导入" + uuid4().hex[:8],
            "slug": "fiction-import-" + uuid4().hex[:8],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def import_root(wid, adapter="ontofoundry-core-1"):
    return f"/api/v1/modeling/workspaces/{wid}/imports/{adapter}"


def preview(client, wid, raw, adapter="ontofoundry-core-1"):
    response = client.post(import_root(wid, adapter) + "?name=fiction.json", content=raw)
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, wid, p, **overrides):
    return client.post(
        import_root(wid, p["adapter"]) + f"/{p['import_id']}/confirm",
        json={
            "content_sha256": p["content_sha256"],
            "expected_current_version_id": p["base_version_id"],
            "idempotency_key": "fiction-confirm-0001",
            **overrides,
        },
    )


def session(client, wid, sid):
    return client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}").json()


def batch(client, wid, result):
    response = client.get(
        f"/api/v1/workspaces/{wid}/sessions/{result['session_id']}/proposal-batches/{result['batch_id']}"
    )
    assert response.status_code == 200, response.text
    return response.json()


def _changes(client, import_id):
    with client.app.state.session_factory() as db:
        record = db.get(ImportRecord, import_id)
        return [
            (c["target_kind"], c.get("field_changes") or c.get("after"))
            for c in record.preview_json["changes"]
        ]


def bind_imported_datasets(client, wid, result):
    """Pick a registered connection for unbound dataset proposals, as a reviewer would."""
    for item in batch(client, wid, result)["items"]:
        after = item.get("after")
        if item["status"] != "pending" or item["target_kind"] != "dataset" or not after:
            continue
        if after.get("connection_id") or after.get("source_kind", "table") != "table":
            continue
        dataset = bind_datasets(client, {"datasets": [dict(after)]}, wid)["datasets"][0]
        current = session(client, wid, result["session_id"])
        response = client.put(
            f"/api/v1/workspaces/{wid}/sessions/{result['session_id']}/proposals/{item['id']}/dataset",
            json={"dataset": dataset, "expected_session_revision": current["revision"]},
        )
        assert response.status_code == 200, response.text


def accept(client, wid, result):
    bind_imported_datasets(client, wid, result)
    current = session(client, wid, result["session_id"])
    items = batch(client, wid, result)["items"]
    if not items:
        return current
    response = client.post(
        f"/api/v1/workspaces/{wid}/sessions/{result['session_id']}/proposal-decisions",
        json={
            "idempotency_key": str(uuid4()),
            "expected_session_revision": current["revision"],
            "decisions": [
                {"proposal_id": i["id"], "decision": "accept"}
                for i in items
                if i["status"] == "pending"
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["session"]


def publish(client, wid, current):
    root = f"/api/v1/workspaces/{wid}/sessions/{current['id']}"
    response = client.post(
        root + "/preview", json={"expected_session_revision": current["revision"]}
    )
    assert response.status_code == 200, response.text
    p = response.json()
    response = client.post(
        root + "/publish",
        json={
            "expected_session_revision": current["revision"],
            "expected_current_version_id": p["current_version_id"],
            "expected_merged_snapshot_sha256": p["merged_snapshot_sha256"],
            "expected_instance_change_sequence": p["instance_change_sequence"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("name", example_names())
def test_thirteen_native_files_preview_confirm_review_publish(client, space, name):
    raw = (EXAMPLES_DIR / (name + ".json")).read_bytes()
    p = preview(client, space, raw)
    assert not p["document_error"]
    assert not p["proposal_summary"]["blocked"]
    assert client.get(f"/api/v1/workspaces/{space}/sessions").json()["items"] == []
    with client.app.state.session_factory() as db:
        assert db.scalar(select(ProposalBatchRecord.id)) is None
        record = db.get(ImportRecord, p["import_id"])
        material = db.get(MaterialRecord, p["material_id"])
        assert record.raw_sha256 == hashlib.sha256(raw).hexdigest()
        formatted = client.app.state.settings.data_dir / space / (material.sha256 + ".md")
        assert material.sha256 == hashlib.sha256(formatted.read_bytes()).hexdigest()
        assert (
            raw == (client.app.state.settings.data_dir / record.raw_artifact).read_bytes()
        )
    response = confirm(client, space, p)
    assert response.status_code == 200, response.text
    result = response.json()
    current = session(client, space, result["session_id"])
    assert not current["draft"]["object_types"] and not current["draft"]["metrics"]
    assert current["import_source"] == {
        "adapter": p["adapter"],
        "report_id": p["import_id"],
    }
    assert confirm(client, space, p).json() == result
    detail = batch(client, space, result)
    assert all(i["operation"] == "create" for i in detail["items"])
    assert detail["producer"]["kind"] == "import"
    with client.app.state.session_factory() as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(ModelingSessionRecord).where(
                            ModelingSessionRecord.workspace_id == space
                        )
                    )
                )
            )
            == 1
        )
        stored = db.get(ProposalBatchRecord, result["batch_id"])
        assert stored.dataagent_task_id is None
        for item in detail["items"]:
            for evidence in item["evidence"]:
                if evidence["kind"] == "material":
                    check_material_evidence(
                        evidence,
                        material_lookup(db, client.app.state.settings, space),
                        "导入",
                    )
    accepted = accept(client, space, result)
    manual_before = [
        e
        for c in json.loads(raw)["draft"].values()
        if isinstance(c, list)
        for item in c
        if isinstance(item, dict)
        for e in item.get("evidence", [])
        if e["kind"] == "manual"
    ]
    manual_after = [
        e
        for c in accepted["draft"].values()
        if isinstance(c, list)
        for item in c
        if isinstance(item, dict)
        for e in item.get("evidence", [])
        if e["kind"] == "manual"
    ]
    assert manual_before == manual_after
    publish(client, space, accepted)
    again = preview(client, space, raw)
    assert (
        not again["proposal_summary"]["create"] and not again["proposal_summary"]["update"]
    ), _changes(client, again["import_id"])
    reopened = client.get(import_root(space) + "/" + p["import_id"]).json()
    assert reopened["report"] == p["report"]


@pytest.mark.parametrize("file", ["storybook-lending", "library-lending"])
def test_original_ossie_examples_preview_to_pending_keep_report(client, space, file):
    raw = (
        Path(__file__).parent / f"fixtures/ossie_synthetic/{file}.ossie.json"
    ).read_bytes()
    p = preview(client, space, raw, "ossie")
    assert p["adapter"] == "ossie-0.2" and not p["document_error"]
    response = confirm(client, space, p)
    assert response.status_code == 200, response.text
    assert (
        len(batch(client, space, response.json())["items"])
        == p["proposal_summary"]["create"]
    )
    assert (
        client.get(import_root(space, "ossie") + "/" + p["import_id"]).json()["report"]
        == p["report"]
    )
    publish(client, space, accept(client, space, response.json()))


@pytest.mark.parametrize("raw", [b"", b'{"ontology":', b'{"format":"wrong"}'])
def test_file_error_cannot_confirm_but_report_is_reopenable(client, space, raw):
    p = preview(client, space, raw)
    assert p["document_error"]
    assert confirm(client, space, p).status_code == 422
    assert client.get(import_root(space) + "/" + p["import_id"]).status_code == 200
    assert client.get(f"/api/v1/workspaces/{space}/sessions").json()["items"] == []


def test_changed_head_and_tampered_hash_do_not_create_session(client, space):
    raw = (EXAMPLES_DIR / "01-basic-sales.json").read_bytes()
    first = preview(client, space, raw)
    second = preview(client, space, raw)
    result = confirm(client, space, first).json()
    publish(client, space, accept(client, space, result))
    response = confirm(client, space, second)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "IMPORT_BASE_CHANGED"
    )
    third = preview(client, space, raw)
    response = confirm(client, space, third, content_sha256="0" * 64)
    assert response.status_code == 409
    assert len(client.get(f"/api/v1/workspaces/{space}/sessions").json()["items"]) == 1


def test_tampered_artifacts_and_stored_preview_are_rejected(client, space):
    raw = (EXAMPLES_DIR / "01-basic-sales.json").read_bytes()
    p = preview(client, space, raw)
    with client.app.state.session_factory() as db:
        record = db.get(ImportRecord, p["import_id"])
        path = client.app.state.settings.data_dir / record.raw_artifact
        path.write_bytes(b"{}")
    response = confirm(client, space, p)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "IMPORT_ARTIFACT_CHANGED"
    )
    p = preview(client, space, raw)
    with client.app.state.session_factory() as db:
        record = db.get(ImportRecord, p["import_id"])
        record.preview_json = {**record.preview_json, "changes": []}
        db.commit()
    assert confirm(client, space, p).json()["error"]["code"] == "IMPORT_CONTENT_CHANGED"


def test_reports_are_workspace_scoped_and_bearer_management_is_denied(client, space):
    p = preview(client, space, b"{}")
    other = client.post(
        "/api/v1/workspaces",
        json={"name": "虚构隔离" + uuid4().hex[:8], "slug": "fiction-" + uuid4().hex[:8]},
    ).json()["id"]
    assert client.get(import_root(other) + "/" + p["import_id"]).status_code == 404
    assert (
        client.get(import_root(space, "no-such-adapter") + "/" + p["import_id"]).status_code
        == 404
    )
    assert (
        client.post(
            import_root(space) + "?name=fiction.json",
            content=b"{}",
            headers={"authorization": "Bearer fiction"},
        ).status_code
        == 401
    )


def count_document():
    return document(
        entity("fiction_order"),
        ontology_mappings=[
            ontology_map(
                [dataset("orders")],
                name="fiction_scope",
                metrics=[{"name": "order_count", "expression": expression("COUNT(*)")}],
            )
        ],
    )


def test_count_completion_is_explicit_reviewable_idempotent_and_report_immutable(
    client, space
):
    p = preview(client, space, json.dumps(count_document()).encode(), "ossie-0.2")
    completion = next(c for c in p["completion"] if c["kind"] == "count_dataset")
    result = confirm(client, space, p).json()
    current = session(client, space, result["session_id"])
    url = import_root(space, p["adapter"]) + f"/{p['import_id']}/completions"
    body = {
        "issue_id": completion["issue_id"],
        "expected_session_revision": current["revision"],
        "expected_draft_sha256": current["draft_sha256"],
        "idempotency_key": "fiction-completion-0001",
        "dataset_id": completion["datasets"][0]["id"],
    }
    invalid = client.post(url, json={**body, "dataset_id": str(uuid4())})
    assert invalid.status_code == 422, invalid.text
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised["batch_id"] != result["batch_id"]
    assert client.post(url, json=body).json() == revised
    duplicate = client.post(
        url, json={**body, "idempotency_key": "fiction-completion-duplicate"}
    )
    assert (
        duplicate.status_code == 409
        and duplicate.json()["error"]["code"] == "IMPORT_COMPLETION_UNCHANGED"
    )
    detail = batch(client, space, revised)
    assert any(i["after"].get("aggregation") == "count" for i in detail["items"])
    assert not session(client, space, current["id"])["draft"]["metrics"]
    reread = client.get(import_root(space, p["adapter"]) + "/" + p["import_id"]).json()
    assert reread["report"] == p["report"]
    assert (
        next(c for c in reread["completion"] if c["issue_id"] == completion["issue_id"])[
            "status"
        ]
        == "proposed"
    )
    accepted = accept(client, space, revised)
    assert len(accepted["draft"]["metrics"]) == 1
    reread = client.get(import_root(space, p["adapter"]) + "/" + p["import_id"]).json()
    assert (
        next(c for c in reread["completion"] if c["issue_id"] == completion["issue_id"])[
            "status"
        ]
        == "accepted"
    )
    stale = client.post(url, json={**body, "idempotency_key": "fiction-completion-0002"})
    assert stale.status_code == 409
    publish(client, space, accepted)


def test_source_definition_completion_retranslates_and_preserves_historical_report(
    client, space
):
    source = count_document()
    source["ontology_mappings"][0]["semantic_model"]["metrics"][0]["expression"] = (
        expression("SELECT 1")
    )
    p = preview(client, space, json.dumps(source).encode(), "ossie-0.2")
    completion = next(
        c
        for c in p["completion"]
        if c["kind"] == "source_definition" and "/metrics/" in c["source_path"]
    )
    result = confirm(client, space, p).json()
    current = session(client, space, result["session_id"])
    definition = json.loads(completion["original"])
    definition["expression"] = expression("COUNT(orders.code)")
    body = {
        "issue_id": completion["issue_id"],
        "expected_session_revision": current["revision"],
        "expected_draft_sha256": current["draft_sha256"],
        "idempotency_key": "fiction-definition-0001",
        "definition": definition,
    }
    response = client.post(
        import_root(space, p["adapter"]) + f"/{p['import_id']}/completions", json=body
    )
    assert response.status_code == 200, response.text
    revised = response.json()
    assert any(i["target_kind"] == "metric" for i in batch(client, space, revised)["items"])
    assert (
        client.get(import_root(space, p["adapter"]) + "/" + p["import_id"]).json()["report"]
        == p["report"]
    )


def test_dataset_metadata_completion_generates_proposal_without_changing_source_report(
    client, space
):
    p = preview(client, space, json.dumps(count_document()).encode(), "ossie-0.2")
    completion = next(c for c in p["completion"] if c["kind"] == "dataset_metadata")
    result = confirm(client, space, p).json()
    current = session(client, space, result["session_id"])
    dataset = completion["dataset"]
    dataset["dialect"] = "postgres"
    dataset["columns"][0]["physical_type"] = "VARCHAR"
    response = client.post(
        import_root(space, p["adapter"]) + f"/{p['import_id']}/completions",
        json={
            "issue_id": completion["issue_id"],
            "expected_session_revision": current["revision"],
            "expected_draft_sha256": current["draft_sha256"],
            "idempotency_key": "fiction-metadata-0001",
            "dataset": dataset,
        },
    )
    assert response.status_code == 200, response.text
    revised = response.json()
    details = batch(client, space, revised)
    assert (
        next(i for i in details["items"] if i["target_kind"] == "dataset")["after"][
            "dialect"
        ]
        == "postgres"
    )
    assert not session(client, space, current["id"])["draft"]["datasets"]
    accepted = accept(client, space, revised)
    assert accepted["draft"]["datasets"][0]["columns"][0]["physical_type"] == "VARCHAR"
    reopened = client.get(import_root(space, p["adapter"]) + "/" + p["import_id"]).json()
    assert reopened["report"] == p["report"]
    assert (
        next(c for c in reopened["completion"] if c["issue_id"] == completion["issue_id"])[
            "status"
        ]
        == "accepted"
    )


def test_correcting_conflicting_parent_unblocks_reverse_dependents_in_new_batch(
    client, space
):
    from test_core1_import_matching import graph, object_type

    existing = object_type("alpha")
    gamma = object_type("gamma")
    base_doc = {
        "format": "ontofoundry",
        "schema_version": "core-1",
        "exported_at": "2026-10-18T00:00:00Z",
        "draft": graph(existing, gamma).model_dump(mode="json"),
    }
    initial = preview(client, space, json.dumps(base_doc).encode())
    first = confirm(client, space, initial).json()
    publish(client, space, accept(client, space, first))
    new = {**gamma, "name": "alpha"}
    source = graph(new).model_dump(mode="json")
    source["properties"] = [
        {
            "id": str(uuid4()),
            "owner_type_id": new["id"],
            "display_name": "编号",
            "name": "code",
            "value_kind": "string",
        }
    ]
    p = preview(client, space, json.dumps({**base_doc, "draft": source}).encode())
    assert len(p["current_blocked"]) == 2
    result = confirm(client, space, p).json()
    current = session(client, space, result["session_id"])
    issue = next(c for c in p["completion"] if c["source_path"] == "/draft/object_types/0")
    definition = json.loads(issue["original"])
    definition["name"] = "gamma"
    definition["display_name"] = "伽马"
    response = client.post(
        import_root(space) + f"/{p['import_id']}/completions",
        json={
            "issue_id": issue["issue_id"],
            "expected_session_revision": current["revision"],
            "expected_draft_sha256": current["draft_sha256"],
            "idempotency_key": "fiction-unblock-0001",
            "definition": definition,
        },
    )
    assert response.status_code == 200, response.text
    revised = response.json()
    assert {i["target_kind"] for i in batch(client, space, revised)["items"]} == {
        "object_type",
        "property",
    }
    reopened = client.get(import_root(space) + "/" + p["import_id"]).json()
    assert reopened["current_blocked"] == []
    assert reopened["report"] == p["report"]
    accepted = accept(client, space, revised)
    assert len(accepted["draft"]["properties"]) == 1


def test_nonmember_cannot_preview_read_or_confirm(client, space):
    from ontofoundry_api.api.auth import Principal, current_principal

    p = preview(client, space, (EXAMPLES_DIR / "01-basic-sales.json").read_bytes())
    client.app.dependency_overrides[current_principal] = lambda: Principal(
        id=str(uuid4()), subject="fictional-outsider", display_name="虚构访客", email=None
    )
    try:
        assert client.get(import_root(space) + "/" + p["import_id"]).status_code == 403
        assert confirm(client, space, p).status_code == 403
        assert (
            client.post(
                import_root(space) + "?name=fiction.json", content=b"{}"
            ).status_code
            == 403
        )
    finally:
        client.app.dependency_overrides.clear()


def test_concurrent_confirm_creates_exactly_one_session(client, space):
    from concurrent.futures import ThreadPoolExecutor

    p = preview(client, space, (EXAMPLES_DIR / "01-basic-sales.json").read_bytes())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: confirm(client, space, p), range(2)))
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    assert responses[0].json() == responses[1].json()
    assert len(client.get(f"/api/v1/workspaces/{space}/sessions").json()["items"]) == 1


def test_ossie_alias_rejects_legacy_replace_and_publish_options(client, space):
    response = client.post(
        import_root(space, "ossie") + "?name=fiction.json&mode=replace&publish=true",
        content=json.dumps(count_document()).encode(),
    )
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "IMPORT_OPTIONS_UNSUPPORTED"
    )
    assert client.get(f"/api/v1/workspaces/{space}/sessions").json()["items"] == []
