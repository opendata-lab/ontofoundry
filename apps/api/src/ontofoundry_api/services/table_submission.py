"""Resolve input-only table refs against a run's pinned physical table snapshot."""

import hashlib
import json

from jsonschema import Draft202012Validator

from ontofoundry_api.contracts.proposal_diagnostics import schema_diagnostic
from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    TableEvidenceInput,
    result_schema,
)
from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.domain.table_reading import column_line, table_header, table_lines
from ontofoundry_api.services.dataset_sql import (
    TableReference,
    parse_query,
    physical_tables,
)
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.material_store import store_text_material
from ontofoundry_api.services.metadata_sync import normalize_schema


def prepare_table_submission(db, settings, session, raw):
    """Normalize a copy, preserving the digest of the original submission elsewhere."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        return raw  # The ordinary parser reports malformed JSON.
    schema = result_schema()
    invalid = next(Draft202012Validator(schema).iter_errors(data), None)
    if invalid:
        raise ProposalContractError(
            "RESULT_SCHEMA_INVALID", schema_diagnostic(invalid, schema, data)
        )
    manifest = session.run_manifest_json or {}
    tables = (manifest.get("table_snapshot") or {}).get("tables", [])
    by_ref = {t["key"]: t for t in tables}
    physical = {
        (t["connection_id"], t.get("schema_name") or "", t["table_name"]): t for t in tables
    }
    evidence = []
    used = set()
    for item in data["items"]:
        after = item.get("after") or {}
        for entry in [*item.get("evidence", []), *after.get("evidence", [])]:
            if entry.get("kind") != "table":
                continue
            TableEvidenceInput.model_validate(entry)
            ref = entry["ref"]
            key, dot, col = ref.partition(".")
            table = by_ref.get(key)
            if table is None or (dot and col not in {c["name"] for c in table["columns"]}):
                options = (
                    list(by_ref)
                    if table is None
                    else [key, *[key + "." + c["name"] for c in table["columns"]]]
                )
                raise ServiceError(
                    f"未知表引用 {ref}；有效引用：{'、'.join(options) or '无'}；请重新检索本轮表结构",
                    code="TABLE_REF_UNKNOWN",
                    status_code=422,
                    details={"valid_refs": options},
                )
            used.add(key)
            evidence.append(entry)
        if (
            "table_snapshot" not in manifest
            or item["target_kind"] != "dataset"
            or item["operation"] == "delete"
        ):
            continue
        connection_id = after.get("connection_id")
        connection = db.get(ConnectionRecord, connection_id) if connection_id else None
        if not connection or connection.workspace_id != session.workspace_id:
            raise ServiceError(
                f"数据集“{after.get('display_name') or after.get('name')}”的表 {after.get('table_name') or after.get('query_sql')} 未绑定本轮范围内的连接；请删去并列为未交付项",
                code="TABLE_NOT_IN_SESSION_SCOPE",
                status_code=422,
            )
        schema_name = normalize_schema(connection, after.get("schema_name")) or ""
        refs = (
            physical_tables(parse_query(after.get("query_sql"), connection.kind))
            if after.get("source_kind", "table") == "query"
            else [TableReference(schema_name, after.get("table_name"))]
        )
        for ref in refs:
            identity = (connection_id, ref.schema or schema_name, ref.name)
            table = physical.get(identity)
            if table is None or (
                ref.catalog and ref.catalog != connection.config_json.get("database", "")
            ):
                name = ".".join(
                    filter(None, [ref.catalog, ref.schema or schema_name, ref.name])
                )
                raise ServiceError(
                    f"数据集“{after.get('display_name') or after.get('name')}”使用的表 {name} 不在本轮固定范围内；请删去该数据集及依赖提案，并在回答中列为未交付项",
                    code="TABLE_NOT_IN_SESSION_SCOPE",
                    status_code=422,
                )
            used.add(table["key"])
    if not used:
        return raw
    # One receipt per batch, using only referenced tables, in pinned key order.
    lines, positions = [], {}
    for table in tables:
        key = table["key"]
        if key not in used:
            continue
        block = table_lines(table)
        positions[key] = (len(lines) + 1, table["table"])
        for column in table["columns"]:
            rendered = column_line(table, column)
            positions[key + "." + column["name"]] = (
                len(lines) + block.index(rendered) + 1,
                table["table"] + "." + column["name"],
            )
        assert block[0] == table_header(table)
        lines.extend(block)
    text = "\n".join(lines) + "\n"
    material = store_text_material(
        db,
        settings,
        session.workspace_id,
        "表结构收据 · 本轮提交",
        text,
        origin="table_receipt",
    )
    assert material.sha256 == hashlib.sha256(text.encode()).hexdigest()
    for entry in evidence:
        line, heading = positions[entry["ref"]]
        quote = entry["quote"]
        entry.clear()
        entry.update(
            kind="material",
            material_id=material.id,
            material_sha256=material.sha256,
            locator={"heading": heading, "line_start": line, "line_end": line},
            quote=quote,
        )
    return json.dumps(data, ensure_ascii=False).encode()
