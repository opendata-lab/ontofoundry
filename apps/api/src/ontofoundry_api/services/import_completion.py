"""Explicit human corrections create new reviewable batches; reports stay immutable."""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import UUID, uuid5

import sqlglot
from sqlalchemy import select, update
from sqlglot import exp

from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.documents import SourceDocument
from ontofoundry_api.adapters.ossie.ids import display_name, source_id, technical_name
from ontofoundry_api.adapters.ossie.metrics import variant
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.core import CoreDraft, SimpleMetric
from ontofoundry_api.domain.dependencies import reverse_dependencies, strict_equal
from ontofoundry_api.domain.models import COLLECTIONS
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.errors import ConflictError, ServiceError
from ontofoundry_api.services.import_integrity import payload_sha256
from ontofoundry_api.services.import_matching import (
    build_candidate_graph,
    elements,
    rewrite_import_ids,
)
from ontofoundry_api.services.import_proposals import build_import_batch
from ontofoundry_api.services.material_source import material_source_path
from ontofoundry_api.services.material_store import store_text_material
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposals import (
    batch_items,
    dependency_map,
    effective_statuses,
    store_batch,
)


def is_count(issue):
    if issue["construct"] != "Metric" or not issue.get("original"):
        return False
    try:
        text, dialect = variant(json.loads(issue["original"]))
        statements = sqlglot.parse(text, read=dialect)
        ast = statements[0] if len(statements) == 1 else None
        return (
            isinstance(ast, exp.Count)
            and isinstance(ast.this, exp.Star)
            and not any(v for k, v in ast.args.items() if k not in {"this", "big_int"})
        )
    except (ValueError, KeyError, TypeError, sqlglot.errors.SqlglotError):
        return False


def pending_candidate(db, session):
    batches = list(
        db.scalars(
            select(ProposalBatchRecord.id).where(
                ProposalBatchRecord.workspace_id == session.workspace_id,
                ProposalBatchRecord.session_id == session.id,
                ProposalBatchRecord.status == "available",
            )
        )
    )
    items = batch_items(db, batches, session.workspace_id, session.id)
    statuses = effective_statuses(
        items,
        dependency_map(db, batches, session.workspace_id, session.id),
        session.draft_json,
    )
    data = deepcopy(session.draft_json)
    for item in items:
        if statuses[item.id][0] != "pending":
            continue
        collection = COLLECTIONS[
            next(k for k in COLLECTIONS if k.value == item.target_kind)
        ]
        data[collection] = [e for e in data[collection] if e["id"] != item.target_id]
        if item.after_json:
            data[collection].append(item.after_json)
    try:
        return validate_core_graph(CoreDraft.model_validate(data))
    except ValueError as error:
        raise ConflictError(
            "当前提案存在冲突，请先处理后再补全", code="IMPORT_CANDIDATE_INVALID"
        ) from error


def current_import_blocked(db, record):
    if not record.session_id:
        return record.preview_json["blocked"]
    from ontofoundry_api.services.imports import identities

    session = db.get(ModelingSessionRecord, record.session_id)
    try:
        candidate = pending_candidate(db, session)
        source = rewrite_import_ids(
            CoreDraft.model_validate(record.converted_json), record.preview_json["id_map"]
        )
        current = elements(candidate)
        data = source.model_dump(mode="json")
        for history in record.completions_json:
            replacements = history.get("replacements", {})
            active = {
                e["id"]
                for values in replacements.values()
                for e in values
                if e["id"] in current and strict_equal(current[e["id"]][1], e)
            }
            if not active:
                continue
            old_ids = set(history.get("replaced_target_ids", []))
            for collection, values in replacements.items():
                data[collection] = [
                    e for e in data[collection] if e["id"] not in active | old_ids
                ] + [e for e in values if e["id"] in active]
        return build_candidate_graph(
            candidate,
            CoreDraft.model_validate(data),
            native=True,
            registered=identities(db, record.workspace_id),
        ).blocked
    except ConflictError:
        return record.preview_json["blocked"]


def completion_issues(record, blocked):
    reasons = {b["target_id"]: b["reason"] for b in blocked}
    result = []
    for issue in record.report_json["issues"]:
        reason = next(
            (
                reasons[record.preview_json["id_map"].get(i, i)]
                for i in issue["target_element_ids"]
                if record.preview_json["id_map"].get(i, i) in reasons
            ),
            None,
        )
        if issue["completion_status"] == "available" or reason:
            result.append({**issue, "message": reason or issue["message"]})
    return result


def completion_list(db, record, *, blocked=None):
    session = (
        db.get(ModelingSessionRecord, record.session_id) if record.session_id else None
    )
    draft = session.draft_json if session else record.converted_json
    dataset_by_id = {e["id"]: e for e in draft["datasets"]}
    # Available pending datasets are legitimate explicit choices as well.
    if session:
        for row in db.scalars(
            select(ProposalItemRecord).where(
                ProposalItemRecord.session_id == session.id,
                ProposalItemRecord.target_kind == "dataset",
                ProposalItemRecord.status == "pending",
            )
        ):
            if row.after_json:
                dataset_by_id[row.target_id] = row.after_json
    result = []
    for issue in completion_issues(
        record, current_import_blocked(db, record) if blocked is None else blocked
    ):
        status = "available"
        histories = [h for h in record.completions_json if h["issue_id"] == issue["id"]]
        if histories and session:
            history = histories[-1]
            rows = list(
                db.scalars(
                    select(ProposalItemRecord).where(
                        ProposalItemRecord.batch_id == history["batch_id"]
                    )
                )
            )
            relevant = [r for r in rows if r.target_id in history["target_ids"]]
            current = {
                i: e for i, (_, e) in elements(CoreDraft.model_validate(draft)).items()
            }
            if relevant and all(
                r.target_id in current and strict_equal(current[r.target_id], r.after_json)
                for r in relevant
            ):
                status = "accepted"
            elif any(r.status == "pending" for r in relevant):
                status = "proposed"
        scope_path = issue["source_path"].split("/semantic_model/")[0]
        source_ids = {
            t
            for i in record.report_json["issues"]
            if i["construct"] == "datasets"
            and i["outcome"] == "converted"
            and i["source_path"].startswith(scope_path + "/")
            for t in i["target_element_ids"]
        }
        scoped = {record.preview_json["id_map"].get(i, i) for i in source_ids}
        datasets = [
            {"id": i, "name": d["name"]}
            for i, d in sorted(dataset_by_id.items())
            if not is_count(issue) or i in scoped
        ]
        metadata_id = (
            next(
                (
                    record.preview_json["id_map"].get(i, i)
                    for i in issue["target_element_ids"]
                    if record.preview_json["id_map"].get(i, i) in dataset_by_id
                ),
                None,
            )
            if issue["construct"] == "DatasetMetadata" and issue["outcome"] == "converted"
            else None
        )
        metadata = dataset_by_id.get(metadata_id) if metadata_id else None
        if (
            metadata
            and metadata.get("dialect")
            and metadata.get("columns")
            and all(c.get("physical_type") for c in metadata["columns"])
        ):
            in_draft = any(
                d["id"] == metadata_id and d == metadata for d in draft["datasets"]
            )
            status = "accepted" if session and in_draft else "proposed"
        result.append(
            {
                "issue_id": issue["id"],
                "message": issue["message"],
                "original": issue["original"],
                "source_path": issue["source_path"],
                "source_locator": issue["source_locator"],
                "kind": "dataset_metadata"
                if metadata
                else "count_dataset"
                if is_count(issue)
                else "source_definition",
                "dataset": metadata,
                "datasets": datasets,
                "status": status,
            }
        )
    return result


def complete_import(db, settings, workspace_id, actor_id, adapter_id, import_id, body):
    from ontofoundry_api.services.imports import (
        adapter_for,
        check_artifacts,
        confirmed_view,
        get_import,
        identities,
    )

    record = get_import(db, workspace_id, adapter_id, import_id, lock=True)
    if not record.session_id:
        raise ConflictError("请先确认导入，再处理待补全", code="IMPORT_NOT_CONFIRMED")
    request_hash = payload_sha256(body.model_dump(mode="json"))
    replay = next(
        (
            h
            for h in record.completions_json
            if h["idempotency_key"] == body.idempotency_key
        ),
        None,
    )
    if replay:
        if replay["request_sha256"] != request_hash:
            raise ConflictError("同一补全请求不能提交不同内容", code="IDEMPOTENCY_CONFLICT")
        return {**confirmed_view(record), "batch_id": replay["batch_id"]}
    check_artifacts(record, settings, db=db)
    session = db.scalar(
        select(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == record.session_id,
            ModelingSessionRecord.workspace_id == workspace_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        session.revision != body.expected_session_revision
        or session.draft_sha256 != body.expected_draft_sha256
    ):
        raise ConflictError(
            "草稿已变化，请刷新报告后重新补全", code="SESSION_REVISION_CHANGED"
        )
    if session.task_status in {
        "submitting",
        "queued",
        "running",
        "waiting_input",
        "waiting_permission",
    }:
        raise ConflictError("建模运行中，请结束后再补全", code="SESSION_RUNNING")
    issue = next(
        (
            i
            for i in completion_issues(record, current_import_blocked(db, record))
            if i["id"] == str(body.issue_id)
        ),
        None,
    )
    if issue is None:
        raise ServiceError(
            "该条目不支持人工补全", code="IMPORT_COMPLETION_INVALID", status_code=422
        )
    reserved = db.execute(
        update(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == session.id,
            ModelingSessionRecord.revision == body.expected_session_revision,
            ModelingSessionRecord.draft_sha256 == body.expected_draft_sha256,
        )
        .values(updated_at=utc_now())
    )
    if reserved.rowcount != 1:
        raise ConflictError(
            "草稿已变化，请刷新报告后重新补全", code="SESSION_REVISION_CHANGED"
        )
    candidate = pending_candidate(db, session)
    raw = (settings.data_dir / record.raw_artifact).read_bytes()
    document = SourceDocument.parse(raw)
    correction_report = None
    target_ids = set()
    evidence = {}
    if body.dataset is not None and body.dataset_id is None and body.definition is None:
        allowed_ids = {
            record.preview_json["id_map"].get(i, i) for i in issue["target_element_ids"]
        }
        previous = next((d for d in candidate.datasets if d.id == body.dataset.id), None)
        if (
            issue["construct"] != "DatasetMetadata"
            or previous is None
            or str(previous.id) not in allowed_ids
        ):
            raise ServiceError(
                "数据集不属于此待补全条目", code="IMPORT_DATASET_INVALID", status_code=422
            )
        for key in (
            "name",
            "schema_name",
            "table_name",
            "description",
            "snapshot_date_column",
        ):
            if getattr(previous, key) != getattr(body.dataset, key):
                raise ServiceError(
                    "此处仅补数据集的方言和列元数据",
                    code="IMPORT_COMPLETION_INVALID",
                    status_code=422,
                )
        corrected = candidate.model_copy(deep=True)
        corrected.datasets = [
            body.dataset if d.id == body.dataset.id else d for d in corrected.datasets
        ]
        result = build_candidate_graph(
            candidate, corrected, native=True, registered=identities(db, workspace_id)
        )
        target_ids.add(str(body.dataset.id))
        correction_material = store_text_material(
            db,
            settings,
            workspace_id,
            "导入数据集补全.json",
            json.dumps(body.dataset.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
        )
    elif (
        is_count(issue)
        and body.dataset_id
        and body.definition is None
        and body.dataset is None
    ):
        choice = next(
            (c for c in completion_list(db, record) if c["issue_id"] == issue["id"]), None
        )
        if (
            not choice
            or str(body.dataset_id) not in {d["id"] for d in choice["datasets"]}
            or body.dataset_id not in {d.id for d in candidate.datasets}
        ):
            raise ServiceError(
                "请选择此来源中可用的数据集", code="IMPORT_DATASET_INVALID", status_code=422
            )
        scope_path = issue["source_path"].split("/semantic_model/")[0]
        scope = document.get(scope_path)
        mappings = document.value.get("ontology_mappings", [])
        key = scope.get("name")
        if (
            not key
            or sum(m.get("name") == key for m in mappings if isinstance(m, dict)) != 1
        ):
            key = scope_path
        definition = json.loads(issue["original"])
        ident = source_id(UUID(workspace_id), "metric:" + key + "." + definition["name"])
        existing = next((m for m in candidate.metrics if m.id == ident), None)
        others = [m for m in candidate.metrics if m.id != ident]
        metric = SimpleMetric(
            id=ident,
            kind="simple",
            name=existing.name
            if existing
            else display_name(definition["name"], {m.name.casefold() for m in others}),
            technical_name=existing.technical_name
            if existing
            else technical_name(
                definition["name"], {m.technical_name.casefold() for m in others}
            ),
            description=definition.get("description", ""),
            dataset_id=body.dataset_id,
            aggregation="count",
        )
        corrected = candidate.model_copy(deep=True)
        corrected.metrics = [*others, metric]
        result = build_candidate_graph(
            candidate, corrected, native=True, registered=identities(db, workspace_id)
        )
        target_ids.add(str(ident))
        correction_material = store_text_material(
            db,
            settings,
            workspace_id,
            "导入补全选择.json",
            json.dumps(
                {
                    "source_path": issue["source_path"],
                    "original": definition,
                    "dataset_id": str(body.dataset_id),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
    elif body.definition is not None and body.dataset_id is None and body.dataset is None:
        # Correct the selected source subtree only, then run the real adapter again.
        source = deepcopy(document.value)
        parts = issue["source_path"].split("/")[1:]
        node = source
        try:
            for part in parts[:-1]:
                key = part.replace("~1", "/").replace("~0", "~")
                node = node[int(key)] if isinstance(node, list) else node[key]
            last = parts[-1].replace("~1", "/").replace("~0", "~")
            node[int(last) if isinstance(node, list) else last] = body.definition
        except (KeyError, IndexError, ValueError) as error:
            raise ServiceError(
                "该来源无法局部修订，请修正文件后重新导入",
                code="IMPORT_COMPLETION_INVALID",
                status_code=422,
            ) from error
        corrected_bytes = (json.dumps(source, ensure_ascii=False, indent=2) + "\n").encode()
        translated = adapter_for(record.adapter).import_document(
            corrected_bytes, ImportContext(UUID(workspace_id))
        )
        correction_report = translated.report.model_dump(mode="json")
        selected = [
            i
            for i in translated.report.issues
            if i.source_path == issue["source_path"]
            or i.source_path.startswith(issue["source_path"] + "/")
        ]
        if not selected or any(i.outcome == "error" for i in selected):
            raise ServiceError(
                "修订定义仍未通过转换，请检查来源和依赖",
                code="IMPORT_COMPLETION_INVALID",
                status_code=422,
                details={"report": correction_report},
            )
        matched = build_candidate_graph(
            candidate,
            translated.model,
            native=record.adapter == "ontofoundry-core-1",
            registered=identities(db, workspace_id),
        )
        source_targets = {
            t for i in selected if i.outcome == "converted" for t in i.target_element_ids
        }
        source_targets |= reverse_dependencies(translated.model, source_targets)
        target_ids = {matched.id_map.get(str(t), str(t)) for t in source_targets}
        subset = candidate.model_copy(deep=True)
        for c in COLLECTIONS.values():
            additions = [e for e in getattr(matched.model, c) if str(e.id) in target_ids]
            setattr(
                subset,
                c,
                [e for e in getattr(subset, c) if str(e.id) not in target_ids] + additions,
            )
        result = build_candidate_graph(
            candidate, subset, native=True, registered=identities(db, workspace_id)
        )
        correction_material = store_text_material(
            db, settings, workspace_id, "导入修订.json", corrected_bytes.decode()
        )
    else:
        raise ServiceError(
            "请选择数据集或提供修订后的来源定义",
            code="IMPORT_COMPLETION_INVALID",
            status_code=422,
        )
    if result.blocked or not target_ids:
        raise ServiceError(
            "修订与当前模型冲突，请检查依赖",
            code="IMPORT_COMPLETION_BLOCKED",
            status_code=422,
        )
    if not result.changes:
        raise ConflictError(
            "此修订已在当前草稿或待审提案中", code="IMPORT_COMPLETION_UNCHANGED"
        )
    # Include all still-pending dependencies, so the replacement batch is self-contained.
    final_result = build_candidate_graph(
        CoreDraft.model_validate(session.draft_json),
        result.model,
        native=True,
        registered=identities(db, workspace_id),
    )
    if final_result.blocked or not final_result.changes:
        raise ConflictError(
            "修订结果没有可生成的新提案", code="IMPORT_COMPLETION_UNCHANGED"
        )
    batch_id = str(uuid5(UUID(record.id), "completion:" + body.idempotency_key))
    lines = material_source_path(db, settings, correction_material).read_text().splitlines()
    for target in target_ids:
        evidence[target] = [
            {
                "kind": "material",
                "id": str(uuid5(UUID(batch_id), target)),
                "material_id": correction_material.id,
                "material_sha256": correction_material.sha256,
                "locator": {"line_start": 1, "line_end": len(lines)},
                "quote": "\n".join(lines)[:2000],
            }
        ]
    parsed = build_import_batch(
        session.draft_json,
        final_result.changes,
        batch_id=batch_id,
        lookup=material_lookup(db, settings, workspace_id),
        evidence_by_target=evidence,
    )
    duplicate_batch = db.scalar(
        select(ProposalBatchRecord.id).where(
            ProposalBatchRecord.workspace_id == workspace_id,
            ProposalBatchRecord.session_id == session.id,
            ProposalBatchRecord.result_sha256 == parsed.result_sha256,
        )
    )
    if duplicate_batch:
        raise ConflictError(
            "相同修订已生成提案，请审阅已有批次",
            code="IMPORT_COMPLETION_UNCHANGED",
            details={"batch_id": duplicate_batch},
        )
    store_batch(
        db,
        workspace_id=workspace_id,
        session_id=session.id,
        task_id=None,
        manifest={
            "run_token": "completion:" + body.idempotency_key,
            "base_version_id": session.base_version_id,
            "base_version_sha256": session.base_version_sha256,
            "source_session_revision": session.revision,
            "source_draft_sha256": session.draft_sha256,
            "materials": [
                {"id": correction_material.id, "sha256": correction_material.sha256}
            ],
            "producer": {
                "kind": "import",
                "adapter": record.adapter,
                "report_id": record.id,
                "issue_id": issue["id"],
                "actor_id": actor_id,
            },
        },
        parsed=parsed,
    )
    record.completions_json = [
        *record.completions_json,
        {
            "issue_id": issue["id"],
            "idempotency_key": body.idempotency_key,
            "request_sha256": request_hash,
            "batch_id": batch_id,
            "target_ids": sorted(target_ids),
            "material_id": correction_material.id,
            "report": correction_report,
            "replaced_target_ids": [
                record.preview_json["id_map"].get(i, i) for i in issue["target_element_ids"]
            ],
            "replacements": {
                c: [
                    e.model_dump(mode="json")
                    for e in getattr(result.model, c)
                    if str(e.id) in target_ids
                ]
                for c in COLLECTIONS.values()
            },
        },
    ]
    db.commit()
    return {**confirmed_view(record), "batch_id": batch_id}
