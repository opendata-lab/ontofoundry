"""Source diagnostics are derived from the current candidate graph, never status."""

from copy import deepcopy

from sqlalchemy import select, update

from ontofoundry_api.db_models import ModelingSessionRecord, ProposalItemRecord
from ontofoundry_api.domain.core import Dataset
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.services.dataset_validation import check_dataset
from ontofoundry_api.services.errors import DatasetSourceError


def candidate_for(db, session):
    draft = deepcopy(session.draft_json)
    items = db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.session_id == session.id, ProposalItemRecord.status == "pending").order_by(ProposalItemRecord.created_at, ProposalItemRecord.ordinal)).all()
    for item in items:
        if ElementKind(item.target_kind) not in COLLECTIONS:
            continue
        collection = COLLECTIONS[ElementKind(item.target_kind)]
        draft[collection] = [e for e in draft[collection] if e["id"] != item.target_id]
        if item.after_json:
            draft[collection].append(deepcopy(item.after_json))
    return draft


def proposal_diagnostics(db, workspace_id, item):
    session = db.get(ModelingSessionRecord, item.session_id)
    if session is None or not item.after_json:
        return []
    draft = candidate_for(db, session)
    datasets = {d["id"]: d for d in draft["datasets"]}
    checked = {}
    def check(identity):
        if identity not in checked:
            raw = datasets.get(identity)
            checked[identity] = check_dataset(db, workspace_id, Dataset.model_validate(raw)) if raw else {"valid": False, "columns": None, "diagnostics": [{"code": "DATASET_NOT_FOUND", "severity": "error", "path": "/dataset_id", "message": "依赖数据集不存在"}]}
        return checked[identity]
    element = item.after_json
    if item.target_kind == "dataset":
        return check(item.target_id)["diagnostics"]
    result = []
    def columns(identity, names, path):
        state = check(identity)
        if not state["valid"]:
            result.append({"code": "DATASET_SOURCE_BLOCKED", "severity": "error", "path": path, "message": "依赖数据集来源未就绪", "details": {"dataset_id": identity}})
            return
        known = {c["name"] for c in state.get("columns") or datasets.get(identity, {}).get("columns") or []}
        for name in names:
            if known and name not in known:
                result.append({"code": "COLUMN_NOT_FOUND", "severity": "error", "path": path, "message": f"列 {name} 不存在", "details": {"dataset_id": identity}})
    if item.target_kind == "mapping":
        sources = {s["id"]: s for s in element["sources"]}
        for source in sources.values():
            columns(source["dataset_id"], source["key_columns"], "/sources/" + source["id"])
        for name, field in element["fields"].items():
            if field["kind"] == "column" and field["source_id"] in sources:
                columns(sources[field["source_id"]]["dataset_id"], [field["column"]], "/fields/" + name)
    if item.target_kind == "metric":
        metrics = {m["id"]: m for m in draft["metrics"]}
        parts = [metrics.get(element[k], {}) for k in ("numerator_id", "denominator_id")] if element["kind"] == "ratio" else [element]
        for part in parts:
            identity = part.get("dataset_id")
            if identity:
                names = [r["column"] for r in [part.get("measure"), part.get("time_field"), *[f["column"] for f in part.get("filters", [])]] if r]
                if part["kind"] == "expression":
                    import sqlglot
                    from sqlglot import exp
                    names += [c.name for c in sqlglot.parse_one(part["expression"]).find_all(exp.Column)]
                columns(identity, names, "/" + ("components" if element["kind"] == "ratio" else "measure"))
    return result


def revise_dataset(db, workspace_id, session_id, proposal_id, dataset, expected_revision, settings):
    from ontofoundry_api.services.proposal_apply import save_pending, trial_pending
    from ontofoundry_api.services.session_gate import (
        lock_session,
        require_current_batch,
        require_idle,
    )
    session = lock_session(db, workspace_id, session_id)
    require_idle(session)
    item = db.get(ProposalItemRecord, proposal_id)
    if item is None or item.session_id != session_id or item.workspace_id != workspace_id:
        raise DatasetSourceError("提案不存在", code="PROPOSAL_NOT_FOUND", status_code=404)
    require_current_batch(db, session, item.batch_id)
    if item.target_kind != "dataset" or item.status != "pending" or item.operation == "delete" or str(dataset.id) != item.target_id:
        raise DatasetSourceError("只有待审阅数据集提案可以修改来源", code="PROPOSAL_NOT_DECIDABLE")
    trial = trial_pending(db, session, item.batch_id, settings, {item.id: dataset.model_dump(mode="json")})
    changed = db.execute(update(ModelingSessionRecord).where(ModelingSessionRecord.id == session_id, ModelingSessionRecord.revision == expected_revision).values(revision=expected_revision + 1))
    if changed.rowcount != 1:
        raise DatasetSourceError("会话已更新，请重新读取", code="SESSION_REVISION_CHANGED", status_code=409)
    save_pending(db, session, item.batch_id, trial)
    db.commit()
    return {"proposal_id": item.id, "session_revision": expected_revision + 1}
