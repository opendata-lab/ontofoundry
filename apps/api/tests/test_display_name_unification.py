"""Naming, external compatibility and destructive cutover have explicit boundaries."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from core1_fixtures import example_draft
from pydantic import ValidationError

from ontofoundry_api.adapters.archive import read_archive, read_ossie, write_archive
from ontofoundry_api.adapters.base import ExportContext, ImportContext
from ontofoundry_api.adapters.native.importer import NativeAdapter
from ontofoundry_api.adapters.native.package import NativePackageAdapter
from ontofoundry_api.adapters.ossie.importer import OssieAdapter
from ontofoundry_api.adapters.ossie.validator import validate_schema
from ontofoundry_api.database import Base
from ontofoundry_api.domain.core import ObjectType
from ontofoundry_api.domain.validation import validate_core_graph


def test_optional_display_names_and_strict_identifiers():
    obj = ObjectType(id=uuid4(), name="fictional_order")
    assert obj.display_name is None
    assert (
        ObjectType(id=uuid4(), name="fictional_order", display_name="  合同  ").display_name
        == "合同"
    )
    for name in ("合同", "1contract", "contract-name", "Ｃontract"):
        with pytest.raises(ValidationError):
            ObjectType(id=uuid4(), name=name)
    with pytest.raises(ValidationError):
        ObjectType.model_validate(
            {"id": str(uuid4()), "name": "订单", "technical_name": "order"}
        )
    model = example_draft("01-basic-sales")
    for obj in model.object_types:
        obj.display_name = "同一个名称"
    validate_core_graph(model)
    model.object_types[1].name = model.object_types[0].name.upper()
    with pytest.raises(ValueError, match="英文标识重复"):
        validate_core_graph(model)


def test_ossie_zip_separates_names_and_preserves_legacy_external_extension():
    model = example_draft("01-basic-sales")
    model.link_types[0].display_name = "签约方"
    model.object_types[0].synonyms = ["合作方"]
    adapter = OssieAdapter()
    artifact = adapter.export_document(
        model, ExportContext("青岚演示", "qinglan", "虚构示例")
    )
    assert artifact.media_type == "application/zip"
    files = read_archive(artifact.document)
    assert set(files) == {"qinglan.ossie.json", "ontofoundry-extension.json"}
    raw, extension_raw = read_ossie(artifact.document)
    pure, extension = json.loads(raw), json.loads(extension_raw)
    assert not validate_schema(pure)
    assert "ontofoundry" not in pure.get("ai_context", {})
    assert model.link_types[0].display_name in extension["display_names"].values()
    assert not any(c["concept"] == "签约方" for c in pure["ontology"])
    ctx = ImportContext(model.workspace_id)
    restored = adapter.import_document(artifact.document, ctx).model
    assert restored.link_types[0].display_name == "签约方"
    standalone = adapter.import_document(raw, ctx).model
    assert all(o.display_name is None for o in standalone.object_types)
    assert all(p.display_name is None for p in standalone.properties)
    assert all(link.display_name is None for link in standalone.link_types)
    pure["ai_context"] = {"ontofoundry": extension}
    old = adapter.import_document(json.dumps(pure).encode(), ctx)
    assert any("旧版扩展块" in i.message for i in old.report.issues)
    assert old.model.link_types[0].display_name == "签约方"


def test_metric_synonyms_use_native_ai_context():
    model = example_draft("13-dataset-metrics")
    model.object_types = [ObjectType(id=uuid4(), name="fictional_order")]
    metric = model.metrics[0]
    metric.synonyms = ["交易总数"]
    artifact = OssieAdapter().export_document(
        model, ExportContext("青岚演示", "qinglan", "")
    )
    raw, extension = read_ossie(artifact.document)
    value = json.loads(raw)
    exported = next(
        m
        for scope in value["ontology_mappings"]
        for m in scope["semantic_model"]["metrics"]
        if m["name"] == metric.name
    )
    assert exported["ai_context"]["synonyms"] == metric.synonyms
    assert "metric:" + metric.name not in json.loads(extension)["synonyms"]
    restored = OssieAdapter().import_document(
        artifact.document, ImportContext(model.workspace_id)
    )
    assert (
        next(m for m in restored.model.metrics if m.name == metric.name).synonyms
        == metric.synonyms
    )


def test_old_native_files_convert_only_at_external_boundary():
    model = example_draft("01-basic-sales")
    ctx = ExportContext("青岚演示", "qinglan", "")
    artifact = NativeAdapter().export_document(model, ctx)
    value = json.loads(artifact.document)
    for collection in ("object_types", "properties", "rules", "metrics"):
        for element in value["draft"][collection]:
            element["technical_name"] = element.pop("name")
            element["name"] = element.pop("display_name")
    result = NativeAdapter().import_document(
        json.dumps(value).encode(), ImportContext(model.workspace_id)
    )
    assert any(i.construct == "LegacyNames" for i in result.report.issues)
    assert result.model.object_types[0].name == model.object_types[0].name
    assert result.model.object_types[0].display_name == model.object_types[0].display_name
    bundle = NativePackageAdapter().export_document(model, ctx)
    imported = NativeAdapter().import_document(
        bundle.document, ImportContext(model.workspace_id)
    )
    assert imported.model == model
    assert "technical_name" not in read_archive(bundle.document)["draft.json"].decode()


def test_unsafe_or_incomplete_archives_are_reported():
    for files in (
        {"../ontology.json": b"{}", "ontofoundry-extension.json": b"{}"},
        {"ontology.json": b"{}"},
    ):
        result = OssieAdapter().import_document(
            write_archive(files), ImportContext(uuid4())
        )
        assert any(
            i.outcome == "error" and i.construct == "document" for i in result.report.issues
        )


def test_cutover_cleans_every_content_table_and_preserves_configuration():
    import ontofoundry_api.db_models  # noqa: F401

    path = (
        Path(__file__).parents[1]
        / "src/ontofoundry_api/alembic/versions/20261020_000001_unify_element_names.py"
    )
    spec = importlib.util.spec_from_file_location("name_cutover", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    identities = {t.name: t.name + "_id" for t in Base.metadata.sorted_tables}
    refs = {
        "workspace_id": "workspaces",
        "created_by": "users",
        "published_by": "users",
        "actor_id": "users",
        "user_id": "users",
        "session_id": "modeling_sessions",
        "batch_id": "proposal_batches",
        "token_id": "service_tokens",
        "connection_id": "data_connections",
        "material_id": "materials",
        "request_id": "proposal_decision_requests",
        "item_id": "proposal_items",
        "job_id": "metadata_sync_jobs",
    }
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        for table in Base.metadata.sorted_tables:
            if table.name in {"document_instances", "instance_links", "instance_evidence", "instance_history"}:
                continue
            row = {}
            for column in table.columns:
                if column.nullable:
                    continue
                if column.name in refs:
                    value = identities[refs[column.name]]
                elif isinstance(column.type, sa.JSON):
                    value = {"technical_name": "legacy_identifier", "name": "旧名称"}
                elif isinstance(column.type, sa.DateTime):
                    value = datetime(2026, 10, 20, tzinfo=UTC)
                elif isinstance(column.type, sa.Integer):
                    value = 1
                else:
                    value = (
                        identities[table.name]
                        if column.name == "id"
                        else "fictional_" + column.name
                    )
                row[column.name] = value
            if table.name == "proposal_item_dependencies":
                # A second target is needed for the non-self dependency constraint.
                original = dict(
                    conn.execute(sa.select(Base.metadata.tables["proposal_items"]))
                    .mappings()
                    .one()
                )
                original.update(
                    id="second_item", ordinal=2, fingerprint="second_fingerprint"
                )
                conn.execute(Base.metadata.tables["proposal_items"].insert(), original)
                row["depends_on_item_id"] = "second_item"
            conn.execute(table.insert(), row)
        conn.execute(sa.text("UPDATE workspaces SET current_version_id='old_version'"))
        conn.exec_driver_sql(
            "CREATE TABLE modeling_session_migrations (id TEXT PRIMARY KEY, source_draft_json JSON)"
        )
        conn.exec_driver_sql(
            "INSERT INTO modeling_session_migrations VALUES ('fictional_migration', '{}')"
        )
        keep = set(Base.metadata.tables) - set(migration.CONTENT_TABLES)
        before = {
            name: [
                dict(r)
                for r in conn.execute(sa.select(Base.metadata.tables[name])).mappings()
            ]
            for name in keep
        }
        migration.discard_ontology(conn)
        migration.discard_ontology(conn)
        for table in migration.CONTENT_TABLES:
            if table in sa.inspect(conn).get_table_names():
                assert (
                    conn.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar() == 0
                )
        before["workspaces"][0]["current_version_id"] = None
        for name in keep:
            assert [
                dict(r)
                for r in conn.execute(sa.select(Base.metadata.tables[name])).mappings()
            ] == before[name]


def test_native_package_http_restores_material_evidence_before_review(client):
    import hashlib

    from test_core1_import_flow import accept, confirm, preview, publish

    from ontofoundry_api.domain.core import MaterialEvidence
    from ontofoundry_api.services.materials_lookup import material_lookup

    response = client.post(
        "/api/v1/workspaces", json={"name": "青岚包导入", "slug": "qinglan-bundle"}
    )
    assert response.status_code == 201, response.text
    workspace_id = response.json()["id"]
    model = example_draft("01-basic-sales")
    data = "青岚合同由虚构合作方签署。\n第二行是虚构材料。".encode()
    sha = hashlib.sha256(data).hexdigest()
    material_id = str(uuid4())
    model.object_types[0].evidence = [
        MaterialEvidence(
            kind="material",
            id=uuid4(),
            material_id=material_id,
            material_sha256=sha,
            locator={"line_start": 1, "line_end": 1},
            quote="青岚合同由虚构合作方签署。",
        )
    ]
    context = ExportContext(
        "青岚包导入",
        "qinglan-bundle",
        "虚构材料往返",
        materials=(
            {
                "material_id": material_id,
                "name": "青岚合同材料.md",
                "sha256": sha,
                "byte_size": len(data),
                "path": "materials/" + sha + ".md",
                "data": data,
            },
        ),
    )
    artifact = NativePackageAdapter().export_document(model, context)
    p = preview(client, workspace_id, artifact.document)
    assert not p["document_error"]
    result = confirm(client, workspace_id, p).json()
    accepted = accept(client, workspace_id, result)
    obj = next(
        o
        for o in accepted["draft"]["object_types"]
        if o["name"] == model.object_types[0].name
    )
    restored = next(e for e in obj["evidence"] if e["material_sha256"] == sha)
    assert restored["id"] == str(model.object_types[0].evidence[0].id)
    with client.app.state.session_factory() as db:
        material = material_lookup(db, client.app.state.settings, workspace_id)(
            restored["material_id"]
        )
        assert material == (sha, data.decode().splitlines())
    publish(client, workspace_id, accepted)
    files = read_archive(artifact.document)
    manifest = json.loads(files["manifest.json"])
    manifest["materials"] = []
    files["manifest.json"] = json.dumps(manifest).encode()
    invalid = preview(client, workspace_id, write_archive(files))
    assert invalid["document_error"]
    malformed = preview(
        client, workspace_id, write_archive({"manifest.json": b"[]", "draft.json": b"{}"})
    )
    assert malformed["document_error"]


def test_ossie_rule_names_restore_only_from_sidecar():
    model = example_draft("08-rules")
    exported = OssieAdapter().export_document(
        model, ExportContext("青岚规则", "qinglan", "")
    )
    assert exported.document is not None
    result = OssieAdapter().import_document(
        exported.document, ImportContext(model.workspace_id)
    )
    assert sorted(
        (r.name, r.display_name, r.description, r.expression) for r in result.model.rules
    ) == sorted((r.name, r.display_name, r.description, r.expression) for r in model.rules)
    raw, _ = read_ossie(exported.document)
    standalone = OssieAdapter().import_document(raw, ImportContext(model.workspace_id))
    assert standalone.model.rules
    assert all(r.display_name is None for r in standalone.model.rules)
