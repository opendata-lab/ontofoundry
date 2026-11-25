from copy import deepcopy
from typing import Any
from uuid import uuid4

import jsonschema
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    OntologyVersionRecord,
    WorkspaceRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.snapshot import draft_sha256, empty_snapshot
from ontofoundry_api.services.element_diff import element_changes
from ontofoundry_api.services.errors import ServiceError, SessionRequestError
from ontofoundry_api.services.ontology_query import (
    _all_graph,
    current_version,
    snapshot_of,
    version_summary,
)
from ontofoundry_api.services.proposals import pending_summary, proposal_state
from ontofoundry_api.services.publish_preview import (
    auto_merged,
    element_labels,
    impacts,
    three_way,
)
from ontofoundry_api.services.read_cache import session_reads, version_snapshots
from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES
from ontofoundry_api.services.session_gate import lock_session, require_draft_edit
from ontofoundry_api.services.workspaces import get_workspace, publish_draft


def get_modeling_session(db: Session, workspace_id: str, session_id: str):
    item = db.get(ModelingSessionRecord, session_id)
    if (
        not item
        or item.workspace_id != workspace_id
        or item.draft_json.get("schema_version") != "core-1"
    ):
        raise SessionRequestError(404, "建模会话不存在")
    return item


def session_draft(item) -> dict:
    """Read the current draft without rewriting session history."""
    if item.draft_json.get("schema_version") != "core-1":
        raise SessionRequestError(404, "旧建模会话已停用，请新建会话")
    draft = deepcopy(item.draft_json)
    return draft


def version_snapshot_sha256(db, workspace_id: str, version_id: str | None) -> str:
    """normalized_snapshot_sha256 of a version, or of the empty snapshot."""
    return snapshot_sha256(version_snapshot(db, workspace_id, version_id))


def version_snapshot(db, workspace_id: str, version_id: str | None) -> dict:
    version = db.get(OntologyVersionRecord, version_id) if version_id else None
    return snapshot_of(version) if version else empty_snapshot(workspace_id)


def session_response(db, item) -> dict:
    """A session as the API returns it: data plus proposal summary and the
    element-level changes relative to its base version."""
    data = session_data(item)
    data["import_source"] = import_source(db, item.workspace_id, item.id)
    key = _read_key(item)

    def base_diff():
        try:
            return element_changes(_base_snapshot(db, item), session_draft(item))
        except ValueError:  # an invalid draft field never blocks reading the session
            return []

    def summary():
        return pending_summary(db, item.workspace_id, item.id, item.draft_json)

    if key is None:
        changes = base_diff()
        return {**data, **summary(), "base_diff": changes, "unpublished_change_count": len(changes)}
    changes = session_reads.get(
        (*key, "base_diff", item.base_version_id, item.base_version_sha256), base_diff
    )
    return {
        **data,
        **session_reads.get(
            (*key, "pending", proposal_state(db, item.workspace_id, item.id)), summary
        ),
        "base_diff": changes,
        "unpublished_change_count": len(changes),
    }


def import_source(db, workspace_id, session_id):
    from ontofoundry_api.db_models import ImportRecord

    record = db.scalar(
        select(ImportRecord).where(
            ImportRecord.workspace_id == workspace_id, ImportRecord.session_id == session_id
        )
    )
    return {"adapter": record.adapter, "report_id": record.id} if record else None


def _read_key(item) -> tuple | None:
    """Derived parts of a session only change with its revision and draft hash."""
    if not item.draft_sha256:
        return None
    return ("session", item.id, item.revision, item.draft_sha256)


def _base_snapshot(db, item) -> dict:
    """The base version's snapshot; published versions never change."""
    if not item.base_version_id or not item.base_version_sha256:
        return version_snapshot(db, item.workspace_id, item.base_version_id)
    return version_snapshots.get(
        (item.base_version_id, item.base_version_sha256),
        lambda: version_snapshot(db, item.workspace_id, item.base_version_id),
    )


def _derived_views(draft):
    return _all_graph(draft)


def session_data(item):
    draft = session_draft(item)
    key = _read_key(item)
    if key is None:
        nodes, edges = _derived_views(draft)
    else:
        nodes, edges = session_reads.get((*key, "views"), lambda: _derived_views(draft))
    return {
        "id": item.id,
        "title": item.title,
        "workspace_id": item.workspace_id,
        "created_by": item.created_by,
        "base_version_id": item.base_version_id,
        "revision": item.revision,
        "base_version_sha256": item.base_version_sha256,
        "draft_sha256": item.draft_sha256 or draft_sha256(draft),
        "draft": draft,
        "material_ids": item.material_ids,
        "table_scope": item.table_scope,
        "linked_tables": item.linked_tables or [],
        "mode": item.mode,
        "task_status": item.task_status,
        "task_detail": item.task_detail,
        "dataagent_topic_id": item.dataagent_topic_id,
        "dataagent_task_id": (
            item.dataagent_task_id
            if item.task_status
            in (
                "submitting",
                "queued",
                "running",
                "waiting_input",
                "waiting_permission",
            )
            else None
        ),
        "dataagent_task_mode": item.dataagent_task_mode,
        "dataagent_run_token": item.dataagent_run_token,
        "uploaded_material_ids": item.uploaded_material_ids,
        "last_result_task_id": item.last_result_task_id,
        "result_state": item.result_state,
        "result_warnings": item.result_warnings,
        "result_claimed_at": item.result_claimed_at,
        "updated_at": item.updated_at,
        "abandoned_at": item.abandoned_at,
        "abandoned_by": item.abandoned_by,
        "graph": {
            "workspace_id": item.workspace_id,
            "version_id": item.base_version_id or "",
            "version_sha256": "",
            "nodes": nodes,
            "edges": edges,
        },
    }


def revise(db, item, revision, *, commit: bool = True, **values):
    item = lock_session(db, item.workspace_id, item.id)
    if "draft_json" in values:
        if values["draft_json"].get("schema_version") != "core-1":
            raise ServiceError(
                "只接受 core-1 草稿", code="VALIDATION_FAILED", status_code=422
            )
        values["draft_json"] = CoreDraft.model_validate(values["draft_json"]).model_dump(
            mode="json"
        )
        values["draft_sha256"] = draft_sha256(values["draft_json"])
    # Only a real change to the draft waits for the run and the review; saving
    # materials or settings carries the draft along unchanged.
    if values.get("draft_sha256", item.draft_sha256) != item.draft_sha256 or (
        "base_version_id" in values and values["base_version_id"] != item.base_version_id
    ):
        require_draft_edit(db, item)
    if "base_version_id" in values:
        values["base_version_sha256"] = version_snapshot_sha256(
            db, item.workspace_id, values["base_version_id"]
        )
    guard = [
        ModelingSessionRecord.id == item.id,
        ModelingSessionRecord.revision == revision,
    ]
    result = db.execute(
        update(ModelingSessionRecord)
        .where(*guard)
        .values(**values, revision=revision + 1, updated_at=utc_now())
    )
    if result.rowcount != 1:
        db.rollback()
        raise ServiceError(
            "此会话已在其他窗口更新，请刷新后重试",
            code="SESSION_REVISION_CHANGED",
            status_code=409,
        )
    if not commit:
        db.flush()
        db.refresh(item)
        return None
    db.commit()
    db.refresh(item)
    return session_response(db, item)


def validate_draft(draft, workspace):
    from ontofoundry_api.services.core_validation import validation_report

    return validation_report(draft)


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def check_resolutions(conflicts: list[dict], resolutions: dict[str, Any]) -> None:
    def refuse(message: str) -> ServiceError:
        return ServiceError(message, code="RESOLUTION_INVALID", status_code=422)

    by_key = {c["key"]: c for c in conflicts}
    if set(resolutions) != set(by_key):
        missing = sorted(set(by_key) - set(resolutions))
        extra = sorted(set(resolutions) - set(by_key))
        raise refuse(
            "解决方案必须恰好对应当前的冲突"
            + (f"；缺少 {missing}" if missing else "")
            + (f"；多余 {extra}" if extra else "")
        )
    for key, answer in resolutions.items():
        conflict = by_key[key]
        choice = answer.get("choice") if isinstance(answer, dict) else answer
        if choice not in conflict["allowed"]:
            raise refuse(
                f"{conflict['element_label']} / {conflict['path']} 不允许选择 {choice}"
            )
        if choice == "custom":
            if not isinstance(answer, dict) or "value" not in answer:
                raise refuse(
                    f"{conflict['element_label']} / {conflict['path']} 的自定义值缺失"
                )
            expected = {
                _json_type(v)
                for v in (conflict["latest"], conflict["draft"])
                if v is not None
            }
            if expected and _json_type(answer["value"]) not in expected:
                raise refuse(
                    f"{conflict['element_label']} / {conflict['path']} 的自定义值类型应为 "
                    + "、".join(sorted(expected))
                )


def revised_material_bookkeeping(item, material_ids):
    """Release unselected upload bookkeeping once no run is using it.

    A terminal run's proposal batch keeps its own material manifest, so this
    session-level copy only blocks deletion of documents the user unchecked.
    """
    from ontofoundry_api.services.session_gate import occupied

    if occupied(item):
        return {}
    selected = set(material_ids)
    values = {}
    uploaded = item.uploaded_material_ids or []
    if any(material_id not in selected for material_id in uploaded):
        values["uploaded_material_ids"] = [
            material_id for material_id in uploaded if material_id in selected
        ]
    manifest = item.run_manifest_json
    if manifest:
        materials = manifest.get("materials") or []
        kept = [entry for entry in materials if entry.get("id") in selected]
        if len(kept) != len(materials):
            values["run_manifest_json"] = {**manifest, "materials": kept}
    return values


def resolve_merge(
    workspace_id: str,
    session_id: str,
    body,
    db: Session,
    *,
    user_id: str | None = None,
):
    space = get_workspace(db, workspace_id)
    item = lock_session(db, workspace_id, session_id)
    require_draft_edit(db, item)
    expected_current = body.expected_current_version_id
    revision = body.expected_session_revision
    if space.current_version_id != expected_current:
        raise ServiceError(
            "最新版本又有变化，请重新预览",
            code="PREVIEW_OUTDATED",
            status_code=409,
            details={"current_version_id": space.current_version_id},
        )
    base = version_snapshot(db, workspace_id, item.base_version_id)
    latest = version_snapshot(db, workspace_id, space.current_version_id)
    draft = session_draft(item)
    # Resolutions must answer exactly the current conflicts, each with an
    # allowed choice and, for custom, a value of the field's own type.
    conflicts = three_way(base, latest, draft, workspace_id).conflicts
    check_resolutions(conflicts, body.resolutions)
    merge = three_way(base, latest, draft, workspace_id, body.resolutions)
    try:
        jsonschema.validate(merge.merged, CoreDraft.model_json_schema())
    except jsonschema.ValidationError as exc:
        raise ServiceError(
            "合并结果结构无效：" + exc.message, code="RESOLUTION_INVALID", status_code=422
        ) from exc
    if merge.conflicts:
        raise ServiceError(
            "仍有未解决的冲突",
            code="CONFLICTS_UNRESOLVED",
            status_code=422,
            details={
                "conflicts": merge.conflicts,
                "current_version_id": space.current_version_id,
            },
        )
    # Values typed while resolving are the user's own edits (§4.3); everything
    # else the merge brings in comes from the latest version, not from them.
    custom = _custom_elements(conflicts, body.resolutions)
    custom_items = _check_custom_resolutions(draft, merge.merged, custom)
    # The draft now starts from the current version: resolved conflicts are
    # its content, and the base moves so they are never asked again.
    draft_diffs = [
        d for d in element_changes(draft, merge.merged)
        if (d["element_kind"], d["element_id"]) not in custom
    ]
    revise(
        db,
        item,
        revision,
        commit=False,
        draft_json=merge.merged,
        base_version_id=space.current_version_id,
    )
    actor = user_id or item.created_by
    _record_draft_diffs(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        actor_id=actor,
        diffs=draft_diffs,
        at=utc_now(),
    )
    if custom_items:
        from types import SimpleNamespace

        from ontofoundry_api.services.changes import _record_human_changes

        # Accepted human proposals in the session's batch of unpublished edits,
        # with proposal and draft rows in the change log, like any save.
        _record_human_changes(db, item, SimpleNamespace(items=custom_items), actor, item.revision)
    db.commit()
    db.refresh(item)
    return session_response(db, item)


def _custom_elements(conflicts: list[dict], resolutions: dict[str, Any]) -> set[tuple[str, str]]:
    """Elements whose conflict was answered with a value of the user's own."""
    found = set()
    for conflict in conflicts:
        answer = resolutions.get(conflict["key"])
        choice = answer.get("choice") if isinstance(answer, dict) else answer
        if choice == "custom" and conflict.get("element_kind") and conflict.get("element_id"):
            found.add((conflict["element_kind"], str(conflict["element_id"])))
    return found


def _check_custom_resolutions(draft: dict, merged: dict, custom: set[tuple[str, str]]):
    """The user's own resolution values go through the accept checks (§4.3)."""
    if not custom:
        return []
    from ontofoundry_api.domain.accept_checks import Change, definition_issues
    from ontofoundry_api.services.changes import _items

    items = [i for i in _items(draft, merged) if (i.target_kind, str(i.target_id)) in custom]
    try:
        model = OntologyDraft.model_validate(merged)
    except ValidationError as exc:
        raise ServiceError("合并结果校验失败：" + str(exc), code="RESOLUTION_INVALID", status_code=422) from exc
    issues = definition_issues(model, [Change(i.target_kind, i.target_id, i.after, i.before) for i in items])
    if issues:
        raise ServiceError(
            "自定义的合并结果不完整：" + "；".join(issues),
            code="ACCEPT_CHECK_FAILED", status_code=422, details={"issues": issues},
        )
    return items


def _record_draft_diffs(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    actor_id: str,
    diffs: list[dict[str, Any]],
    at,
) -> None:
    from ontofoundry_api.services import change_log

    for change in diffs:
        action = {"created": "added", "updated": "updated", "deleted": "removed"}[
            change["change"]
        ]
        change_log.record_draft_event(
            db,
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            actor_kind="human",
            action=action,
            target_kind=change["element_kind"],
            target_id=change["element_id"],
            before=change["before"],
            after=change["after"],
            at=at,
        )


def sessions(
    workspace_id: str,
    db: Session,
):
    # Polled while a run is live: never load the drafts.
    rows = db.scalars(
        select(ModelingSessionRecord)
        .options(
            defer(ModelingSessionRecord.draft_json),
            defer(ModelingSessionRecord.candidates_json),
            defer(ModelingSessionRecord.run_manifest_json),
        )
        .where(ModelingSessionRecord.workspace_id == workspace_id)
        .order_by(ModelingSessionRecord.updated_at.desc())
    ).all()
    from ontofoundry_api.db_models import ImportRecord

    sources = {
        r.session_id: {"adapter": r.adapter, "report_id": r.id}
        for r in db.scalars(
            select(ImportRecord).where(
                ImportRecord.workspace_id == workspace_id,
                ImportRecord.session_id.is_not(None),
            )
        )
    }
    return rows, {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "import_source": sources.get(r.id),
                "updated_at": r.updated_at,
                "task_status": r.task_status,
                "base_version_id": r.base_version_id,
                # Both hashes are stored on every write, so this costs no
                # draft read: the draft differs from the version it started from.
                "has_unpublished_changes": bool(
                    r.draft_sha256 and r.draft_sha256 != r.base_version_sha256
                ),
            }
            for r in rows
        ]
    }


def create_session(
    workspace_id: str,
    body,
    db: Session,
    user,
):
    space = get_workspace(db, workspace_id)
    version = (
        db.get(OntologyVersionRecord, space.current_version_id)
        if space.current_version_id
        else None
    )
    draft = snapshot_of(version) if version else empty_snapshot(workspace_id)
    item = ModelingSessionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by=user.id,
        title=body.title,
        mode=body.mode,
        base_version_id=space.current_version_id,
        base_version_sha256=snapshot_sha256(draft),
        draft_json=draft,
        draft_sha256=snapshot_sha256(draft),
    )
    db.add(item)
    db.commit()
    return session_response(db, item)


def personal_session(workspace_id: str, db: Session, user):
    from ontofoundry_api.services.instance_store import lock_workspace

    space = lock_workspace(db, workspace_id)

    def existing():
        return db.scalar(select(ModelingSessionRecord).where(
            ModelingSessionRecord.workspace_id == workspace_id,
            ModelingSessionRecord.personal_owner_id == user.id,
        ))

    item = existing()
    if item is not None and item.abandoned_at is not None:
        item.personal_owner_id = None
        db.flush()
        item = None
    if item is None:
        draft = version_snapshot(db, workspace_id, space.current_version_id)
        item = ModelingSessionRecord(
            id=str(uuid4()), workspace_id=workspace_id, created_by=user.id,
            personal_owner_id=user.id, title="个人会话", mode="model",
            base_version_id=space.current_version_id,
            base_version_sha256=snapshot_sha256(draft), draft_json=draft,
            draft_sha256=snapshot_sha256(draft),
        )
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            item = existing()
            if item is None:
                raise
    return session_response(db, item)


def save_session(
    workspace_id: str,
    session_id: str,
    body,
    settings,
    db: Session,
    user,
):
    item = lock_session(db, workspace_id, session_id)
    values = {}
    if body.mode is not None and body.mode != item.mode:
        if item.dataagent_topic_id:
            raise ServiceError(
                "会话已开始对话，模式不能再修改",
                code="SESSION_MODE_LOCKED",
                status_code=409,
            )
        values["mode"] = body.mode
    if body.title is not None:
        values["title"] = body.title
    if body.material_ids is not None:
        from ontofoundry_api.db_models import MaterialRecord

        for material_id in body.material_ids:
            material = db.get(MaterialRecord, material_id)
            if not material or material.workspace_id != workspace_id:
                raise SessionRequestError(422, "材料不属于当前空间")
        values["material_ids"] = body.material_ids
        values.update(revised_material_bookkeeping(item, body.material_ids))
    if body.table_scope is not None or body.linked_tables is not None:
        from ontofoundry_api.services.dataset_sources import linked_table_details

        scope = body.table_scope or "selected"
        linked = (
            [t.model_dump() for t in body.linked_tables]
            if body.linked_tables is not None
            else item.linked_tables or []
        )
        if scope == "all":
            linked = []
        else:
            linked_table_details(db, workspace_id, linked)
        values.update(table_scope=scope, linked_tables=linked)
    result = revise(db, item, body.revision, **values)
    return result


def validate_session(
    workspace_id: str,
    session_id: str,
    db: Session,
):
    item = get_modeling_session(db, workspace_id, session_id)
    return validate_draft(item.draft_json, get_workspace(db, workspace_id))


def _check_merged_definitions(db, workspace_id, current_version_id, model):
    """Each side passed the accept checks, but their merge can still leave a bound
    object incomplete (another session bound a table while this one added a
    property). Re-check the definitions this publish changes, on the merged result."""
    from ontofoundry_api.domain.accept_checks import Change, definition_issues
    from ontofoundry_api.domain.instances import INSTANCE_KINDS

    latest = version_snapshot(db, workspace_id, current_version_id)
    merged = model.model_dump(mode="json")
    changes = [
        Change(change["kind"], change["id"], change.get("after"), change.get("before"))
        for change in _definition_changes(latest, merged)
        if change["kind"] not in INSTANCE_KINDS
    ]
    issues = definition_issues(model, changes)
    if issues:
        raise ServiceError(
            "发布后的模型不完整：" + "；".join(issues),
            code="ACCEPT_CHECK_FAILED",
            status_code=422,
            details={"issues": issues},
        )


def _definition_changes(before: dict, after: dict) -> list[dict]:
    """Elements added, changed or removed between two snapshots, by kind and id."""
    from ontofoundry_api.domain.models import PROPOSAL_COLLECTIONS

    found = []
    for kind, collection in PROPOSAL_COLLECTIONS.items():
        old = {str(e["id"]): e for e in before.get(collection) or []}
        new = {str(e["id"]): e for e in after.get(collection) or []}
        for identity in old.keys() | new.keys():
            if old.get(identity) != new.get(identity):
                found.append({"kind": kind.value, "id": identity, "before": old.get(identity), "after": new.get(identity)})
    return found


def publish_session(
    workspace_id: str,
    session_id: str,
    body,
    settings,
    db: Session,
    user,
):
    space = db.scalar(
        select(WorkspaceRecord).where(WorkspaceRecord.id == workspace_id).with_for_update()
    )
    item = db.scalar(
        select(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == session_id,
            ModelingSessionRecord.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if not item:
        raise ServiceError("建模会话不存在", code="SESSION_NOT_FOUND", status_code=404)
    require_draft_edit(db, item)
    if (
        body.expected_merged_snapshot_sha256 is None
        or "expected_current_version_id" not in body.model_fields_set
    ):
        raise ServiceError(
            "发布需要最新预览的版本和内容哈希", code="PREVIEW_OUTDATED", status_code=409
        )
    # All five active states, not just the two obvious ones: a run parked on
    # waiting_input or waiting_permission is still live, and publishing a draft
    # the agent is mid-way through rewriting would capture a half-applied model.
    if item.revision != body.session_revision or item.task_status in ACTIVE_RUN_STATUSES:
        if body.strict:
            raise ServiceError(
                "会话已变化或仍在生成，请重新预览",
                code="PREVIEW_OUTDATED",
                status_code=409,
                details={"current_version_id": space.current_version_id},
            )
        raise SessionRequestError(409, "会话已变化或仍在生成，请刷新后发布")
    from ontofoundry_api.services.instance_store import change_sequence

    if body.expected_instance_change_sequence != change_sequence(db, workspace_id):
        raise ServiceError(
            "实例集合在预览后已变化，请重新预览", code="PREVIEW_OUTDATED", status_code=409
        )
    if item.abandoned_at is not None:
        raise ServiceError("会话已放弃", code="SESSION_ABANDONED", status_code=409)
    if body.strict and space.current_version_id != body.expected_current_version_id:
        # Even a change that would merge cleanly is content the user has not
        # seen: never publish it silently (design §9.3).
        raise ServiceError(
            "最新版本在你预览后已变化，请重新预览",
            code="PREVIEW_OUTDATED",
            status_code=409,
            details={"current_version_id": space.current_version_id},
        )
    merge = three_way(
        version_snapshot(db, workspace_id, item.base_version_id),
        version_snapshot(db, workspace_id, space.current_version_id),
        session_draft(item),
        workspace_id,
    )
    merged = merge.merged
    if merge.conflicts:
        if body.strict:
            raise ServiceError(
                "当前版本与草稿存在冲突，请先解决",
                code="MERGE_CONFLICTS",
                status_code=409,
                details={
                    "conflicts": merge.conflicts,
                    "current_version_id": space.current_version_id,
                },
            )
        raise SessionRequestError(
            409,
            {
                "message": "当前版本与草稿存在冲突，请在编辑页合并后重试",
                "conflicts": [
                    {
                        "path": c["key"],
                        "base": c["base"],
                        "current": c["latest"],
                        "draft": c["draft"],
                    }
                    for c in merge.conflicts
                ],
                "current_version_id": space.current_version_id,
                "merged": merged,
            },
        )
    if body.strict and merge.merged_sha256 != body.expected_merged_snapshot_sha256:
        raise ServiceError(
            "待发布内容与预览不一致，请重新预览",
            code="PREVIEW_OUTDATED",
            status_code=409,
            details={"current_version_id": space.current_version_id},
        )
    # Session drafts can be edited directly, so publishing re-checks every new or
    # changed dataset: registered source and safe read-only SQL.
    from ontofoundry_api.services.join_validation import validate_join_columns

    validate_join_columns(
        db,
        workspace_id,
        version_snapshot(db, workspace_id, space.current_version_id),
        merged,
        settings,
    )
    try:
        model = OntologyDraft.model_validate(merged)
    except ValidationError as exc:
        raise ServiceError(
            "发布草稿校验失败：" + str(exc), code="VALIDATION_FAILED", status_code=422
        ) from exc
    _check_merged_definitions(db, workspace_id, space.current_version_id, model)
    try:
        from ontofoundry_api.services import change_log

        old_base_version_id = item.base_version_id
        before_draft = session_draft(item)
        final_draft = model.model_dump(mode="json")
        draft_diffs = element_changes(before_draft, final_draft)
        version = publish_draft(
            db,
            workspace_id=workspace_id,
            draft=model,
            user_id=user.id,
            message=body.message,
            session_id=session_id,
            commit=False,
        )
        item.human_batch_id = None
        item.base_version_id = version.id
        item.base_version_sha256 = snapshot_sha256(final_draft)
        # The session continues from exactly what was published: same
        # normalized form, so its draft hash equals the new base hash.
        item.draft_json = final_draft
        item.draft_sha256 = item.base_version_sha256
        item.revision += 1
        # Everything decided so far is now part of a version: closed (§4.4).
        item.published_revision = item.revision
        item.updated_at = utc_now()
        _record_draft_diffs(
            db,
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=user.id,
            diffs=draft_diffs,
            at=item.updated_at,
        )
        change_log.record_version_event(
            db,
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=user.id,
            actor_kind="human",
            version_id=version.id,
            before={"base_version_id": old_base_version_id} if old_base_version_id else None,
            after={
                "version_id": version.id,
                "version_number": version.version_number,
                "message": version.message,
            },
            at=item.updated_at,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SessionRequestError(409, "另一会话刚刚发布，请重新比较后重试") from exc
    return {"version": version_summary(version), "session": session_response(db, item)}


def preview_definition(
    workspace_id: str,
    session_id: str,
    body,
    settings,
    db: Session,
):
    """Exactly what publishing now would produce: the B/L/D merge of base,
    latest and draft, validated and compiled, with the values publish checks."""
    from ontofoundry_api.services.join_validation import dataset_checks

    item = lock_session(db, workspace_id, session_id)
    require_draft_edit(db, item)
    if item.revision != body.session_revision:
        raise ServiceError(
            "草稿已更新，请重新预览", code="SESSION_REVISION_CHANGED", status_code=409
        )
    space = get_workspace(db, workspace_id)
    merge = three_way(
        version_snapshot(db, workspace_id, item.base_version_id),
        version_snapshot(db, workspace_id, space.current_version_id),
        session_draft(item),
        workspace_id,
    )
    if merge.conflicts:
        raise ServiceError(
            f"与最新版本存在 {len(merge.conflicts)} 处冲突，请先解决",
            code="MERGE_CONFLICTS",
            status_code=409,
            details={
                "conflicts": merge.conflicts,
                "current_version_id": space.current_version_id,
            },
        )
    report = validate_draft(merge.merged, space)
    from ontofoundry_api.services.instance_store import publish_impact

    instance_impact = {"instance_change_sequence": 0, "affected_instances": []}
    if report["publishable"]:
        instance_impact = publish_impact(db, workspace_id, merge.merged, session_id)
        if instance_impact["affected_instances"]:
            report = {**report, "publishable": False}
    else:
        from ontofoundry_api.services.instance_store import change_sequence

        instance_impact["instance_change_sequence"] = change_sequence(db, workspace_id)
    current = current_version(db, workspace_id) if space.current_version_id else None
    changes = element_changes(merge.latest, merge.merged)
    base = (
        db.get(OntologyVersionRecord, item.base_version_id)
        if item.base_version_id
        else None
    )
    return {
        "revision": item.revision,
        "session_revision": item.revision,
        "base_version_id": item.base_version_id,
        "base_version_number": base.version_number if base else None,
        "current_version_id": space.current_version_id,
        "current_version_number": current.version_number if current else None,
        "next_version_number": (
            db.scalar(
                select(func.max(OntologyVersionRecord.version_number)).where(
                    OntologyVersionRecord.workspace_id == workspace_id
                )
            )
            or 0
        )
        + 1,
        "current_version_sha256": snapshot_sha256(merge.latest),
        "merged_snapshot_sha256": merge.merged_sha256,
        **instance_impact,
        "merged_model": merge.merged,
        "validation": report,
        "changes": changes,
        "labels": element_labels(merge.latest, merge.merged),
        "impacts": impacts(changes, merge.merged),
        "auto_merged": auto_merged(merge),
        "dataset_checks": dataset_checks(
            db, workspace_id, merge.latest, merge.merged, settings
        ),
    }


def published_snapshot(
    workspace_id: str,
    db: Session,
):
    space = get_workspace(db, workspace_id)
    version = (
        db.get(OntologyVersionRecord, space.current_version_id)
        if space.current_version_id
        else None
    )
    return snapshot_of(version) if version else empty_snapshot(workspace_id)
