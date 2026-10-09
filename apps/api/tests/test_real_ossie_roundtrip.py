"""Real external Ossie files: persisted API round trips and explicit loss ledger.

The known losses are asserted, not xfailed or hidden by a schema-only check.
Set OSSIE_REAL_ARTIFACT_DIR to save both exports and the complete audit JSON.
Original files are never opened by tests; fixtures are byte-for-byte copies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

import pytest

from ontofoundry_api.db_models import OntologyVersionRecord, WorkspaceRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.runtime_views import mappings_of
from ontofoundry_api.ossie.compiler import canonical_json, compile_ossie, validate_ossie
from ontofoundry_api.ossie.extensions import reverse_export_edits
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.ossie.mappings import _column, _dataset_fields
from ontofoundry_api.ossie.validator import validate_schema
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

FIXTURES = Path(__file__).parent / "fixtures" / "ossie_real"
ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
ONTOLOGY = f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}"
FILES = {
    "account-model-v2": "10f581699485142c8c0b87feac904fe57c944d2c94253fa8ea20be6503f0cc57",
    "architecture-governance": "bda8c581b10fdb0692d561eae73c0d2500e960041a1bcd1c72094653e4662c16",
}
MISSING = {"$missing": True}


def load_document(stem):
    raw = (FIXTURES / f"{stem}.ossie.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FILES[stem]
    return json.loads(raw)


def physical_column(document, expression):
    """Resolve only simple dataset.field expressions; never approximate SQL."""
    if not isinstance(expression, str) or "." not in expression:
        return None
    for mapping in document.get("ontology_mappings", []):
        for dataset in mapping["semantic_model"].get("datasets", []):
            if not expression.startswith(dataset["name"] + "."):
                continue
            column = _column(
                expression, dataset["name"], _dataset_fields(dataset, dataset["name"])
            )
            return (dataset.get("source"), column) if column else None
    return None


def semantic_differences(original, exported):
    """Compare every field, with named collections aligned independently of order.

    A missing subtree is one difference with its ENTIRE original value retained
    in `before` (including all roles, rules, descriptions and expressions).
    Roles and expression arrays remain ordered. Unknown changes default to (a).
    Dataset definitions are compared by logical name: losing the declared logical
    model remains (a), even where individual physical column mappings are equal.
    """
    differences = []

    def record(path, before, after, category="a", reason="内容丢失、改变或新增语义"):
        differences.append(
            {
                "category": category,
                "path": path,
                "reason": reason,
                "before": before,
                "after": after,
            }
        )

    def walk(before, after, path):
        if before == after:
            return
        if (
            path in ("$.ai_context.ontofoundry", "$.ai_context.instructions")
            and before == MISSING
        ):
            record(path, before, after, "b", "生成的平台扩展或说明，不替换原业务构造")
            return
        if path.endswith(".expression"):
            left = physical_column(original, before)
            right = physical_column(exported, after)
            if left is not None and left == right:
                record(path, before, after, "b", "dataset 别名/逻辑字段展开为同一物理表列")
                return
        if path.endswith(".object_mapping.concept") and after == MISSING:
            owner = re.search(r"concept_mappings\[concept=([^\]]+)\]", path)
            relation = re.search(r"children\[relationship=([^\]]+)\]", path)
            if owner and relation:
                component = next(
                    c for c in original["ontology"] if c["concept"] == owner[1]
                )
                roles = next(
                    r["roles"]
                    for r in component["relationships"]
                    if r["name"] == relation[1]
                )
                if len(roles) == 1 and roles[0]["concept"] == before:
                    record(path, before, after, "b", "保留关系的目标概念已由本体 role 定义")
                    return
        if (
            isinstance(before, dict)
            and isinstance(after, dict)
            and MISSING not in (before, after)
        ):
            for key in sorted(before.keys() | after.keys()):
                walk(before.get(key, MISSING), after.get(key, MISSING), f"{path}.{key}")
            return
        if isinstance(before, list) and isinstance(after, list):
            if path.endswith((".extends", ".identify_by")) and sorted(before) == sorted(
                after
            ):
                record(path, before, after, "b", "集合成员不变，仅排序不同")
                return
            key = {
                "ontology": "concept",
                "relationships": "name",
                "datasets": "name",
                "fields": "name",
                "metrics": "name",
                "concept_mappings": "concept",
                "ontology_mappings": "name",
                "children": "relationship",
            }.get(path.rsplit(".", 1)[-1])
            if key and all(
                isinstance(item, dict) and key in item for item in before + after
            ):
                left = {item[key]: item for item in before}
                right = {item[key]: item for item in after}
                assert len(left) == len(before) and len(right) == len(after), path
                if left.keys() == right.keys() and list(left) != list(right):
                    record(path, list(left), list(right), "b", "同名构造仅排序不同")
                for name in sorted(left.keys() | right.keys()):
                    walk(
                        left.get(name, MISSING),
                        right.get(name, MISSING),
                        f"{path}[{key}={name}]",
                    )
                return
            for index in range(max(len(before), len(after))):
                walk(
                    before[index] if index < len(before) else MISSING,
                    after[index] if index < len(after) else MISSING,
                    f"{path}[{index}]",
                )
            return
        record(path, before, after)

    walk(original, exported, "$")
    return differences


def publish_export(client, document):
    response = client.post(
        ROOT + "/imports/ossie", json={"document": document, "mode": "replace"}
    )
    assert response.status_code == 201, response.text
    imported = response.json()
    assert imported["validation"]["publishable"], imported["validation"]
    preview = client.post(
        ROOT + f"/sessions/{imported['id']}/preview",
        json={"expected_session_revision": imported["revision"]},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    response = client.post(
        ROOT + f"/sessions/{imported['id']}/publish",
        json={
            "expected_session_revision": imported["revision"],
            "expected_current_version_id": body["current_version_id"],
            "expected_merged_snapshot_sha256": body["merged_snapshot_sha256"],
            "message": "真实 Ossie 往返验证",
        },
    )
    assert response.status_code == 200, response.text
    version_id = response.json()["version"]["version_id"]
    exported = client.get(ONTOLOGY + f"/versions/{version_id}/export")
    assert exported.status_code == 200, exported.text
    result = exported.json()
    assert validate_schema(result) == []
    assert validate_ossie(result)["publishable"]
    assert result == body["ossie"]
    with client.app.state.session_factory() as db:
        version = db.get(OntologyVersionRecord, version_id)
        space = db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
        assert space.current_version_id == version_id
        assert version.ossie_json == result
        assert version.snapshot_json == imported["draft"]
    return result, imported["import_report"]


@pytest.mark.parametrize("stem", FILES)
def test_real_ossie_roundtrip(client, tmp_path, stem):
    document = load_document(stem)
    assert validate_schema(document) == []
    assert validate_ossie(document)["publishable"]
    # The shared client fixture uses a unique tmp_path SQLite database. Align
    # destination metadata explicitly: publishing obtains it from the workspace,
    # not from the import report. No production database is ever accessed.
    assert client.app.state.engine.url.drivername == "sqlite+pysqlite"
    assert Path(client.app.state.engine.url.database).is_relative_to(tmp_path)
    with client.app.state.session_factory() as db:
        space = db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
        space.slug = document["name"].replace("_", "-")
        space.name = document["name"]
        space.description = document["description"]
        db.commit()
    first, report = publish_export(client, document)
    second, second_report = publish_export(client, first)
    assert second == first  # includes platform rule ids, mappings and ai_context
    assert canonical_json(second) == canonical_json(first)
    assert second_report["skipped"] == []
    assert first["name"] == document["name"]
    assert first["description"] == document["description"]
    differences = semantic_differences(document, reverse_export_edits(first))
    losses = [item for item in differences if item["category"] == "a"]
    assert losses == []
    assert reverse_export_edits(first) == document
    assert report["skipped"] == []
    expected_nary = 6 if stem == "account-model-v2" else 8
    relationships = [(c["concept"], r) for c in document["ontology"] for r in c.get("relationships", []) if len(r.get("roles", [])) >= 2]
    exported_relationships = [(c["concept"], r) for c in first["ontology"] for r in c.get("relationships", []) if len(r.get("roles", [])) >= 2]
    assert len(relationships) == expected_nary
    assert exported_relationships == relationships
    directory = Path(os.environ.get("OSSIE_REAL_ARTIFACT_DIR", tmp_path))
    directory.mkdir(parents=True, exist_ok=True)
    for suffix, payload in (
        ("export.json", first),
        ("second-export.json", second),
        (
            "report.json",
            {
                "source_sha256": FILES[stem],
                "import_report": report,
                "schema_validation": validate_ossie(first),
                "idempotent": True,
                "difference_counts": dict(Counter(d["category"] for d in differences)),
                "differences": differences,
            },
        ),
    ):
        (directory / f"{stem}.{suffix}").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )


@pytest.mark.parametrize("column", ["key", "order", "MixedCase", "column name", 'a"b'])
def test_ansi_quoted_column_mapping_roundtrip(column):
    document = load_document("architecture-governance")
    mapping = document["ontology_mappings"][0]
    rule = next(c for c in mapping["concept_mappings"] if c["concept"] == "arch_rule")
    dataset = next(
        d for d in mapping["semantic_model"]["datasets"] if d["name"] == "arch_rule"
    )
    dataset["fields"][0]["expression"]["dialects"][0]["expression"] = (
        '"' + column.replace('"', '""') + '"'
    )
    mapping["concept_mappings"] = [rule]
    mapping["semantic_model"] = {"name": "rules", "datasets": [dataset]}
    payload, report = import_ossie(document, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    draft = OntologyDraft.model_validate(payload)
    assert report["counts"]["mappings_added"] == 1
    assert mappings_of(draft)[0].key_column == column  # reflected physical column name
    first = compile_ossie(draft, ontology_name="rules", ontology_description="")
    assert validate_schema(first) == []
    payload, _ = import_ossie(first, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    assert mappings_of(OntologyDraft.model_validate(payload))[0].key_column == column
    assert (
        compile_ossie(
            OntologyDraft.model_validate(payload),
            ontology_name="rules",
            ontology_description="",
        )
        == first
    )


@pytest.mark.parametrize(
    "expression", ["key + 1", '"key" + 1', "COUNT(key)", "arch_rule.key\n + 1"]
)
def test_column_parser_does_not_treat_computed_sql_as_a_column(expression):
    assert _column(expression, "arch_rule") is None


@pytest.mark.parametrize("stem", FILES)
def test_publish_uses_destination_workspace_metadata(client, stem):
    document = load_document(stem)
    with client.app.state.session_factory() as db:
        space = db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
        destination_name = space.slug.replace("-", "_")
        destination_description = space.description or space.name
    exported, report = publish_export(client, document)
    assert report["name"] == document["name"]
    assert report["description"] == document["description"]
    assert exported["name"] == document["name"] != destination_name
    assert exported["description"] == document["description"] != destination_description
