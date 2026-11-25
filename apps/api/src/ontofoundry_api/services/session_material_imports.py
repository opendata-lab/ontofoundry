"""Translate Ossie material before pinning a modeling run's review context."""

import hashlib
import logging
from bisect import bisect_right
from itertools import accumulate
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select

from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.documents import raw_json_spans
from ontofoundry_api.adapters.ossie.importer import OssieAdapter
from ontofoundry_api.contracts.proposals import MAX_ITEMS
from ontofoundry_api.db_models import ProposalItemRecord, SessionMaterialImportRecord
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.import_matching import build_candidate_graph, elements
from ontofoundry_api.services.imports import identities, store_import_batch
from ontofoundry_api.services.material_source import (
    MaterialSourceMissing,
    material_source_path,
)
from ontofoundry_api.services.material_store import discard_new_files
from ontofoundry_api.services.table_submission import dataset_scope_tables

logger = logging.getLogger(__name__)


def _ossie_bytes(db, settings, material, adapter):
    try:
        path = material_source_path(db, settings, material)
    except MaterialSourceMissing:
        return None  # Normal run delivery reports a missing material.
    with path.open("rb") as source:
        prefix = source.read(4096)
        if prefix.startswith(b"PK") or not (
            prefix.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"{")
            or Path(material.name).suffix.lower() == ".json"
        ):
            return None
        raw = prefix + source.read()
    return raw if adapter.detect(raw) else None


def _locate_source(raw, material, translation, candidate, batch_id):
    """Replace formatted offsets with original lines and cite the exact value."""
    source = raw.decode("utf-8-sig")
    spans = raw_json_spans(source)
    line_ends = list(accumulate(map(len, source.splitlines(keepends=True))))
    allowed = {change["target_id"] for change in candidate.changes}
    evidence = {}
    for issue in translation["issues"]:
        locator = issue["source_locator"]
        span = spans.get(locator.get("json_pointer"))
        if locator.get("sha256") != material.sha256 or span is None:
            continue
        start, end = span
        locator.pop("formatted_sha256", None)
        locator["line_start"] = bisect_right(line_ends, start) + 1
        locator["line_end"] = bisect_right(line_ends, end - 1) + 1
        for original in issue["target_element_ids"]:
            target = candidate.id_map.get(original, original)
            if target in allowed and target not in evidence:
                evidence[target] = [
                    {
                        "id": str(uuid5(UUID(batch_id), "source:" + target)),
                        "kind": "material",
                        "material_id": material.id,
                        "material_sha256": material.sha256,
                        "locator": {
                            key: locator[key] for key in ("line_start", "line_end")
                        },
                        "quote": source[start : min(end, start + 2000)],
                    }
                ]
    return evidence


def _convert(
    db, settings, session, draft, manifest, material, raw, adapter, record_id, report
):
    if hashlib.sha256(raw).hexdigest() != material.sha256:
        raise ServiceError("材料内容与登记的 SHA256 不一致", code="IMPORT_ARTIFACT_CHANGED")
    workspace_id = session.workspace_id
    tables = manifest["table_snapshot"]["tables"]
    result = adapter.import_document(
        raw, ImportContext(UUID(workspace_id), session_tables=tuple(tables))
    )
    translation = report["translation"] = result.report.model_dump(mode="json")
    if any(
        i.construct == "document" and i.outcome == "error" for i in result.report.issues
    ):
        report.update(status="failed", message="Ossie 文档校验失败，请按普通材料阅读")
        return None

    physical = {
        (t["connection_id"], t.get("schema_name") or "", t["table_name"]): t for t in tables
    }
    missing = []

    def scope_error(dataset):
        try:
            if dataset_scope_tables(db, workspace_id, dataset, physical):
                return None
            reason = "查询数据集没有可与本轮会话表匹配的物理来源"
        except ServiceError as exc:
            reason = exc.message
        missing.append(dataset["id"])
        return reason

    candidate = build_candidate_graph(
        CoreDraft.model_validate(draft),
        result.model,
        native=False,
        registered=identities(db, workspace_id),
        dataset_scope_error=scope_error,
    )
    targets = {
        candidate.id_map.get(source_id, source_id): (kind, element.get("name"))
        for source_id, (kind, element) in elements(result.model).items()
    }
    report["excluded"] = [
        {
            **item,
            "target_kind": targets[item["target_id"]][0],
            "name": targets[item["target_id"]][1],
        }
        for item in candidate.blocked
    ]
    report["missing_table_count"] = len(missing)
    if len(candidate.changes) > MAX_ITEMS:
        raise ServiceError(f"导入提案超过 {MAX_ITEMS} 条", code="IMPORT_ITEM_LIMIT")

    batch_id = str(uuid5(UUID(record_id), "initial-batch"))
    evidence = _locate_source(raw, material, translation, candidate, batch_id)
    if not candidate.changes:
        report["status"] = "no_changes"
        return None

    batch = store_import_batch(
        db,
        settings,
        session,
        draft,
        candidate.changes,
        batch_id=batch_id,
        evidence=evidence,
        manifest={
            "run_token": "import:" + record_id,
            "base_version_id": manifest["base_version_id"],
            "base_version_sha256": manifest["base_version_sha256"],
            "source_session_revision": manifest["source_session_revision"],
            "source_draft_sha256": manifest["source_draft_sha256"],
            "materials": [{"id": material.id, "sha256": material.sha256}],
            "producer": {"kind": "import", "adapter": adapter.id},
        },
        actor_id=manifest["started_by"],
    )
    report.update(
        status="imported", proposal_count=len(candidate.changes), batch_id=batch.id
    )
    return batch.id


def preimport_materials(db, settings, session, draft, manifest, materials):
    """Stage at most one pending import batch in the caller's run transaction."""
    records = {
        row.material_sha256: row
        for row in db.scalars(
            select(SessionMaterialImportRecord).where(
                SessionMaterialImportRecord.session_id == session.id
            )
        )
    }
    pending = set(
        db.scalars(
            select(ProposalItemRecord.batch_id)
            .where(
                ProposalItemRecord.session_id == session.id,
                ProposalItemRecord.status == "pending",
            )
            .distinct()
        )
    )
    active = next((row for row in records.values() if row.batch_id in pending), None)
    active_id = active.batch_id if active else None
    reports = {active.material_sha256: active.report_json} if active else {}
    adapter = OssieAdapter()
    for material in materials:
        sha = material.sha256
        if sha in records:
            reports[sha] = records[sha].report_json
            continue
        raw = _ossie_bytes(db, settings, material, adapter)
        if raw is None:
            continue
        report = reports[sha] = {
            "material_id": material.id,
            "material_sha256": sha,
            "filename": material.name,
            "proposal_count": 0,
            "missing_table_count": 0,
        }
        if pending:
            report.update(
                status="skipped", message="请先处理待审提案，再发消息导入这份材料"
            )
            continue
        record_id, batch_id = str(uuid4()), None
        file_mark = len(db.info.get("new_material_files", ()))
        try:
            with db.begin_nested():
                batch_id = _convert(
                    db,
                    settings,
                    session,
                    draft,
                    manifest,
                    material,
                    raw,
                    adapter,
                    record_id,
                    report,
                )
        except Exception as exc:
            discard_new_files(db, since=file_mark)
            if isinstance(exc, ServiceError):
                message = exc.message
            else:
                logger.exception("Could not import Ossie material %s", material.id)
                message = "Ossie 转换或校验失败，请按普通材料阅读"
            report.pop("batch_id", None)
            report.update(status="failed", message=message, proposal_count=0)
            batch_id = None
        record = SessionMaterialImportRecord(
            id=record_id,
            session_id=session.id,
            material_sha256=sha,
            report_json=report,
            batch_id=batch_id,
        )
        db.add(record)
        records[sha] = record
        if batch_id:
            active_id = batch_id
            pending.add(batch_id)
    return list(reports.values()), active_id


def import_report_note(reports, active_batch_id, file):
    pending_count = sum(
        r["proposal_count"]
        for r in reports
        if active_batch_id and r.get("batch_id") == active_batch_id
    )
    missing_count = sum(r["missing_table_count"] for r in reports)
    notes = []
    if pending_count or missing_count:
        notes.append("导入项已在草稿，不重读材料；计划逐项列出快照列、未证明的物理连接、中文显示名和其他待补全，按 import-completion.md 处理")
    if any(r["status"] == "skipped" for r in reports):
        notes.append("请先处理待审提案再发消息导入")
    if any(r["status"] == "failed" for r in reports):
        notes.append("导入失败的材料按普通材料阅读")
    return {
        "file": file,
        "proposal_count": pending_count,
        "missing_table_count": missing_count,
        "note": "；".join(notes) or "已检查导入报告，当前没有新增导入提案",
    }
