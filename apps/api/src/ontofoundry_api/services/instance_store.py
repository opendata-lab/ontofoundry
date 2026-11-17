"""Workspace instance persistence. All writes join the caller's transaction."""

from copy import deepcopy
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from ontofoundry_api.db_models import (
    DocumentInstanceRecord,
    InstanceDraftRecord,
    InstanceEvidenceRecord,
    InstanceHistoryRecord,
    InstanceLinkRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    WorkspaceRecord,
    utc_now,
)
from ontofoundry_api.domain.core import MaterialLink, MaterialObject
from ontofoundry_api.domain.evidence import EvidenceError, reconcile_draft_evidence
from ontofoundry_api.domain.instances import (
    INSTANCE_KINDS,
    combined_snapshot,
    instance_hash,
    interpretation,
    validate_instances,
)
from ontofoundry_api.domain.models import INSTANCE_COLLECTIONS, OntologyDraft
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services.errors import NotFoundError, ServiceError

RECORDS = {"material_object": DocumentInstanceRecord, "material_link": InstanceLinkRecord}
OWNERS = {"material_object": "instance", "material_link": "link"}


def fail(code, message, status=409, **details):
    raise ServiceError(message, code=code, status_code=status, details=details)


def lock_workspace(db, workspace_id):
    row = db.scalar(
        select(WorkspaceRecord)
        .where(WorkspaceRecord.id == workspace_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundError("工作空间不存在")
    return row


def change_sequence(db, workspace_id):
    return (
        db.scalar(
            select(WorkspaceRecord.instance_change_sequence).where(
                WorkspaceRecord.id == workspace_id
            )
        )
        or 0
    )


def _bump(db, workspace_id):
    db.execute(
        update(WorkspaceRecord)
        .where(WorkspaceRecord.id == workspace_id)
        .values(instance_change_sequence=WorkspaceRecord.instance_change_sequence + 1)
    )


def _evidence(row):
    if row.kind == "manual":
        at = row.created_at
        if at.tzinfo is None:
            from datetime import UTC

            at = at.replace(tzinfo=UTC)
        return {
            "id": row.id,
            "kind": "manual",
            "note": row.note or "",
            "created_by": row.created_by,
            "created_at": at.isoformat(),
        }
    return {
        "id": row.id,
        "kind": "material",
        "material_id": row.material_id,
        "material_sha256": row.material_sha256,
        "locator": {
            "line_start": row.line_start,
            "line_end": row.line_end,
            "heading": row.heading,
        },
        "quote": row.quote or "",
    }


def content(db, kind, row, entries=None):
    entries = (
        entries
        if entries is not None
        else db.scalars(
            select(InstanceEvidenceRecord)
            .where(
                InstanceEvidenceRecord.workspace_id == row.workspace_id,
                InstanceEvidenceRecord.owner_kind == OWNERS[kind],
                InstanceEvidenceRecord.owner_id == row.id,
            )
            .order_by(InstanceEvidenceRecord.id)
        ).all()
    )
    base = {"id": row.id, "evidence": [_evidence(e) for e in entries]}
    if kind == "material_object":
        return MaterialObject.model_validate(
            {**base, "type_id": row.type_id, "values": row.values}
        ).model_dump(mode="json")
    return MaterialLink.model_validate(
        {
            **base,
            "type_id": row.link_type_id,
            "source_id": row.source_instance_id,
            "target_id": row.target_instance_id,
        }
    ).model_dump(mode="json")


def baseline(db, workspace_id, session_id=None, *, include_deleted=False):
    sequence = change_sequence(db, workspace_id)
    items = []
    for kind, cls in RECORDS.items():
        condition = cls.state == "active"
        if session_id:
            condition = or_(
                condition, (cls.state == "staged") & (cls.session_id == session_id)
            )
        if include_deleted:
            condition = or_(
                condition,
                (cls.state == "deleted")
                & or_(cls.session_id.is_(None), cls.session_id == session_id),
            )
        rows = db.scalars(
            select(cls).where(cls.workspace_id == workspace_id, condition).order_by(cls.id)
        )
        rows = list(rows)
        evidence = {}
        if rows:
            for entry in db.scalars(
                select(InstanceEvidenceRecord)
                .where(
                    InstanceEvidenceRecord.workspace_id == workspace_id,
                    InstanceEvidenceRecord.owner_kind == OWNERS[kind],
                    InstanceEvidenceRecord.owner_id.in_([row.id for row in rows]),
                )
                .order_by(InstanceEvidenceRecord.id)
            ):
                evidence.setdefault(entry.owner_id, []).append(entry)
        drafts = session_drafts(db, workspace_id, session_id, kind) if session_id else {}
        for row in rows:
            draft = drafts.get(row.id) if row.state == "active" else None
            if draft is not None and draft.content_json is None:
                continue  # deleted in this session's draft
            element = draft.content_json if draft is not None else content(db, kind, row, evidence.get(row.id, []))
            revision = draft.revision if draft is not None else row.revision
            items.append(
                {
                    "target_kind": kind,
                    "target_id": row.id,
                    "revision": revision,
                    # A pending change reads like a staged instance in its session.
                    "state": "staged" if draft is not None else row.state,
                    "session_id": session_id if draft is not None else row.session_id,
                    "element": element,
                    "hash": instance_hash(element, revision),
                    **({"pending_change": True} if draft is not None else {}),
                }
            )
    if sequence != change_sequence(db, workspace_id):
        fail("INSTANCE_SET_CHANGED", "实例集合在读取期间已变化，请重新读取")
    return {"change_sequence": sequence, "items": items}


def session_drafts(db, workspace_id, session_id, kind=None) -> dict:
    """This session's pending changes to published instances, by target id."""
    query = select(InstanceDraftRecord).where(
        InstanceDraftRecord.workspace_id == workspace_id, InstanceDraftRecord.session_id == session_id,
    )
    if kind is not None:
        query = query.where(InstanceDraftRecord.kind == kind)
    return {d.target_id: d for d in db.scalars(query)}


def _draft_for(db, workspace_id, kind, target_id):
    return db.scalar(select(InstanceDraftRecord).where(
        InstanceDraftRecord.workspace_id == workspace_id,
        InstanceDraftRecord.kind == kind,
        InstanceDraftRecord.target_id == target_id,
    ).with_for_update())


def session_snapshot(db, workspace_id, session_id, draft):
    return combined_snapshot(draft, baseline(db, workspace_id, session_id))


def reconcile_evidence(previous, after, kind, *, lookup, actor, now):
    # Reuse the exact domain rules for immutability, authorship, hashes and lines.
    # The evidence reconciler accepts an explicit collection for instance owners.
    collection = INSTANCE_COLLECTIONS[kind]
    return reconcile_draft_evidence(
        {collection: [previous] if previous else []},
        {collection: [deepcopy(after)]},
        lookup=lookup,
        actor_id=actor,
        now=now,
        collections=(collection,),
    )[collection][0]


def _save_evidence(db, workspace_id, kind, element, actor, now):
    entries = db.scalars(
        select(InstanceEvidenceRecord).where(
            InstanceEvidenceRecord.workspace_id == workspace_id,
            InstanceEvidenceRecord.owner_kind == OWNERS[kind],
            InstanceEvidenceRecord.owner_id == element["id"],
        )
    ).all()
    existing = {e.id: e for e in entries}
    desired = {e["id"] for e in element["evidence"]}
    for row in entries:
        if row.id not in desired:
            db.delete(row)
    for value in element["evidence"]:
        collision = db.get(InstanceEvidenceRecord, value["id"])
        if collision and (
            collision.workspace_id != workspace_id
            or collision.owner_kind != OWNERS[kind]
            or collision.owner_id != element["id"]
        ):
            fail("EVIDENCE_ID_DUPLICATE", "证据 UUID 不能转移到其他实例", 422)
        row = existing.get(value["id"])
        if row is None:
            row = InstanceEvidenceRecord(
                id=value["id"],
                workspace_id=workspace_id,
                owner_kind=OWNERS[kind],
                owner_id=element["id"],
                kind=value["kind"],
                created_by=value.get("created_by", actor),
                created_at=datetime.fromisoformat(
                    value["created_at"].replace("Z", "+00:00")
                )
                if value.get("created_at")
                else now,
            )
            db.add(row)
        for field in ("material_id", "material_sha256", "quote", "note"):
            setattr(row, field, value.get(field))
        for field in ("line_start", "line_end", "heading"):
            setattr(row, field, value.get("locator", {}).get(field))


def write(
    db,
    workspace_id,
    session_id,
    kind,
    target_id,
    after,
    *,
    expected_revision,
    actor,
    proposal_item_id=None,
    state=None,
    operation=None,
    lookup=None,
    model=None,
    validated=False,
    cascades=None,
    next_revision=None,
    reconciled=False,
):
    """Compare-and-set content, evidence and history. Deleted IDs are never reused.

    A session's change to a published instance waits in its draft (AI-11): the
    published row is untouched until the session publishes (activate)."""
    if kind not in INSTANCE_KINDS:
        fail("INSTANCE_KIND_INVALID", "实例种类无效", 422)
    lock_workspace(db, workspace_id)
    if session_id:
        editing_session = db.get(ModelingSessionRecord, session_id)
        if editing_session is None or editing_session.workspace_id != workspace_id:
            raise NotFoundError("会话不属于当前工作空间")
        require_open_session(editing_session)
    cls = RECORDS[kind]
    row = db.scalar(
        select(cls)
        .where(cls.id == target_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is not None and (
        row.workspace_id != workspace_id
        or (row.state == "staged" and row.session_id != session_id)
    ):
        fail("INSTANCE_REVISION_CHANGED", "实例已变化或不属于当前会话")
    draft_mode = row is not None and row.state == "active" and session_id is not None and state != "active"
    pending = _draft_for(db, workspace_id, kind, target_id) if draft_mode else None
    if pending is not None and pending.session_id != session_id:
        fail("INSTANCE_PENDING_ELSEWHERE", "该实例在另一会话中有待发布的修改，请先在那个会话发布或撤销")
    current_revision = pending.revision if pending is not None else (row.revision if row else None)
    if (row is None and expected_revision is not None) or (
        row is not None and current_revision != expected_revision
    ):
        fail("INSTANCE_REVISION_CHANGED", "实例已被其他操作修改，请重新生成或审阅提案")
    if row is None and after is None:
        raise NotFoundError("实例不存在")
    published_element = content(db, kind, row) if row else None
    before_element = pending.content_json if pending is not None else published_element
    previous = (
        {
            "element": before_element,
            "state": "staged" if pending is not None else row.state,
            "revision": current_revision,
            "session_id": session_id if pending is not None else row.session_id,
        }
        if row
        else None
    )
    now = utc_now()
    if after is not None:
        shape = MaterialObject if kind == "material_object" else MaterialLink
        after = shape.model_validate(after).model_dump(mode="json")
        if after["id"] != target_id:
            fail("VALIDATION_FAILED", "实例 id 与目标不匹配", 422)
        try:
            # A draft being published was reconciled when it was accepted: its new
            # evidence, authors and times stay exactly as accepted.
            if not reconciled:
                after = reconcile_evidence(
                    before_element,
                    after,
                    kind,
                    lookup=lookup or (lambda _: None),
                    actor=actor,
                    now=now,
                )
        except EvidenceError as exc:
            raise ServiceError(str(exc), code=exc.code, status_code=422) from exc
        current = baseline(db, workspace_id, session_id)
        objects = {
            i["target_id"]: i["element"]
            for i in current["items"]
            if i["target_kind"] == "material_object"
        }
        if kind == "material_object":
            objects[target_id] = after
        effective = model
        if effective is None:
            editing = db.get(ModelingSessionRecord, session_id) if session_id else None
            effective = editing.draft_json if editing else published_model(db, workspace_id)
        if not isinstance(effective, OntologyDraft):
            effective = OntologyDraft.model_validate(effective)
        related = (
            [after]
            if kind == "material_link"
            else [
                i["element"]
                for i in current["items"]
                if i["target_kind"] == "material_link"
                and target_id in {i["element"]["source_id"], i["element"]["target_id"]}
            ]
        )
        needed = {e for link in related for e in (link["source_id"], link["target_id"])}
        if kind == "material_object":
            needed.add(target_id)
        if not validated:
            try:
                validate_instances(
                    effective,
                    [o for identity, o in objects.items() if identity in needed],
                    related,
                )
            except ValueError as exc:
                raise ServiceError(str(exc), code="VALIDATION_FAILED", status_code=422) from exc
        state = "staged" if draft_mode else state or state_for(
            effective,
            published_model(db, workspace_id),
            kind,
            after,
            objects,
            {i["target_id"] for i in current["items"] if i["state"] == "active"},
        )
    else:
        state = "deleted"
    if draft_mode:
        return _write_draft(
            db, workspace_id, session_id, kind, target_id, row, pending, after, published_element,
            previous, current_revision, actor=actor, proposal_item_id=proposal_item_id,
            operation=operation, cascades=cascades,
        )
    revision = next_revision or (row.revision + 1 if row else 1)
    values = {
        "state": state,
        "session_id": session_id if state == "staged" else None,
        "revision": revision,
        "updated_by": actor,
        "updated_at": now,
    }
    if after is not None:
        values.update(
            {"type_id": after["type_id"], "values": after["values"]}
            if kind == "material_object"
            else {
                "link_type_id": after["type_id"],
                "source_instance_id": after["source_id"],
                "target_instance_id": after["target_id"],
            }
        )
    if row is None:
        row = cls(
            id=target_id,
            workspace_id=workspace_id,
            created_by=actor,
            created_at=now,
            **values,
        )
        db.add(row)
    else:
        changed = db.execute(
            update(cls)
            .where(
                cls.id == target_id,
                cls.workspace_id == workspace_id,
                cls.revision == expected_revision,
            )
            .values(**values)
        )
        if changed.rowcount != 1:
            fail("INSTANCE_REVISION_CHANGED", "实例已被其他操作修改")
    try:
        db.flush()
    except IntegrityError as exc:
        raise ServiceError(
            "实例并发写入冲突", code="INSTANCE_REVISION_CHANGED", status_code=409
        ) from exc
    if after is not None:
        _save_evidence(db, workspace_id, kind, after, actor, now)
    result = {
        "element": after or before_element,
        "state": state,
        "revision": revision,
        "session_id": values["session_id"],
    }
    db.add(
        InstanceHistoryRecord(
            workspace_id=workspace_id,
            owner_kind=OWNERS[kind],
            owner_id=target_id,
            revision=revision,
            operation=operation
            or ("delete" if after is None else "update" if previous else "create"),
            before=previous,
            after=result,
            proposal_item_id=proposal_item_id,
            actor=actor,
            at=now,
        )
    )
    _bump(db, workspace_id)
    db.flush()
    # Deleting an endpoint invalidates its relations, preserving their evidence.
    if after is None and kind == "material_object":
        for link in db.scalars(
            select(InstanceLinkRecord).where(
                InstanceLinkRecord.workspace_id == workspace_id,
                InstanceLinkRecord.state != "deleted",
                or_(
                    InstanceLinkRecord.source_instance_id == target_id,
                    InstanceLinkRecord.target_instance_id == target_id,
                ),
            )
        ).all():
            link_result = write(
                db,
                workspace_id,
                link.session_id,
                "material_link",
                link.id,
                None,
                expected_revision=link.revision,
                actor=actor,
                proposal_item_id=proposal_item_id,
                operation="endpoint_deleted",
                cascades=cascades,
            )
            if cascades is not None:
                cascades.append(
                    {
                        "action": "removed",
                        "target_kind": "material_link",
                        "target_id": link.id,
                        "proposal_id": proposal_item_id,
                        "before": deepcopy(link_result["element"]),
                        "after": None,
                    }
                )
    return result


def published_model(db, workspace_id):
    space = db.get(WorkspaceRecord, workspace_id)
    version = (
        db.get(OntologyVersionRecord, space.current_version_id)
        if space.current_version_id
        else None
    )
    if version is not None:
        from ontofoundry_api.services.ontology_query import read_context

        return read_context(version).draft
    return OntologyDraft.model_validate(empty_snapshot(workspace_id))


def state_for(model, published, kind, element, objects, active_ids):
    """New/changed interpreting definitions, including link ends, stay staged."""
    try:
        relevant = (
            [element]
            if kind == "material_object"
            else [objects[element["source_id"]], objects[element["target_id"]]]
        )
        validate_instances(
            published, relevant, [] if kind == "material_object" else [element]
        )
        if interpretation(model, kind, element, objects) != interpretation(
            published, kind, element, objects
        ):
            return "staged"
        if (
            kind == "material_link"
            and not {element["source_id"], element["target_id"]} <= active_ids
        ):
            return "staged"
        return "active"
    except (ValueError, KeyError):
        return "staged"


def visible(db, workspace_id, model):
    """IS-09: live active content interpreted only by compatible definitions."""
    current = baseline(db, workspace_id)
    objects, links, filtered = [], [], 0
    published = published_model(db, workspace_id)
    all_objects = {
        i["target_id"]: i["element"]
        for i in current["items"]
        if i["target_kind"] == "material_object"
    }
    # Validate the definitions once; each instance below is then checked on its own.
    try:
        checked = validate_instances(model, [], [])
    except (ValueError, KeyError):
        checked = model  # every check below fails and filters, as before
    for item in current["items"]:
        if item["target_kind"] != "material_object":
            continue
        try:
            validate_instances(checked, [item["element"]], [])
            if interpretation(
                model, "material_object", item["element"], all_objects
            ) != interpretation(published, "material_object", item["element"], all_objects):
                raise ValueError("实例引用的定义与固定版本不兼容")
        except (ValueError, KeyError):
            filtered += 1
        else:
            objects.append(item)
    valid = {str(o["target_id"]): o["element"] for o in objects}
    for item in current["items"]:
        if item["target_kind"] != "material_link":
            continue
        try:
            # Only the endpoints matter, and every visible object was checked above.
            ends = {item["element"]["source_id"], item["element"]["target_id"]}
            validate_instances(
                checked, [valid[str(i)] for i in ends if str(i) in valid], [item["element"]]
            )
            if (
                interpretation(model, "material_link", item["element"], all_objects)["link"]
                != interpretation(published, "material_link", item["element"], all_objects)[
                    "link"
                ]
            ):
                raise ValueError("关系定义与固定版本不兼容")
        except (ValueError, KeyError):
            filtered += 1
        else:
            links.append(item)
    return {
        "objects": objects,
        "links": links,
        "filtered_count": filtered,
        "instance_change_sequence": current["change_sequence"],
        "warnings": [f"已过滤 {filtered} 条与本版本不兼容的实例"] if filtered else [],
    }


def publish_impact(db, workspace_id, draft, session_id=None):
    current = baseline(db, workspace_id, session_id)
    published = published_model(db, workspace_id)
    model = OntologyDraft.model_validate(draft)
    objects = {
        i["target_id"]: i["element"]
        for i in current["items"]
        if i["target_kind"] == "material_object"
    }
    affected = []
    for item in current["items"]:
        kind, element = item["target_kind"], item["element"]
        try:
            relevant = (
                [element]
                if kind == "material_object"
                else [
                    objects[i]
                    for i in (element["source_id"], element["target_id"])
                    if i in objects
                ]
            )
            validate_instances(
                model, relevant, [] if kind == "material_object" else [element]
            )
            if item["state"] == "active":
                if kind == "material_link":
                    from ontofoundry_api.domain.graph import DraftIndex

                    old_link = DraftIndex(published).links.get(UUID(element["type_id"]))
                    new_link = DraftIndex(model).links.get(UUID(element["type_id"]))
                    changed = (
                        old_link is None
                        or new_link is None
                        or (old_link.source_type_id, old_link.target_type_id)
                        != (new_link.source_type_id, new_link.target_type_id)
                    )
                else:
                    changed = interpretation(
                        published, kind, element, objects
                    ) != interpretation(model, kind, element, objects)
                if changed:
                    raise ValueError("发布修改了实例引用的定义")
        except (ValueError, KeyError) as exc:
            affected.append(
                {
                    "target_kind": kind,
                    "target_id": item["target_id"],
                    "revision": item["revision"],
                    "reason": str(exc),
                }
            )
    return {
        "instance_change_sequence": current["change_sequence"],
        "affected_instances": affected,
    }


def check_publish(db, workspace_id, draft, session_id=None):
    impact = publish_impact(db, workspace_id, draft, session_id)
    if impact["affected_instances"]:
        fail(
            "INSTANCE_REFERENCES_BLOCK_PUBLISH",
            "发布影响已有实例，请先处理实例",
            409,
            **impact,
        )
    return impact


def _next_revision(db, kind, target_id, current):
    """A revision above every one in the instance's history (drafts record theirs too)."""
    recorded = db.scalar(
        select(func.max(InstanceHistoryRecord.revision)).where(
            InstanceHistoryRecord.owner_kind == OWNERS[kind], InstanceHistoryRecord.owner_id == target_id,
        )
    )
    return max(current or 0, recorded or 0) + 1


def _write_draft(db, workspace_id, session_id, kind, target_id, row, pending, after, published_element,
                 previous, current_revision, *, actor, proposal_item_id, operation, cascades):
    """Keep a session's change to a published instance as a draft; the row stays as published."""
    from ontofoundry_api.domain.canonical import canonical

    now = utc_now()
    revision = _next_revision(db, kind, target_id, current_revision)
    reverted = after is not None and canonical(after) == canonical(published_element)
    if reverted:
        if pending is not None:
            db.delete(pending)
    elif pending is None:
        db.add(InstanceDraftRecord(
            id=str(uuid4()), workspace_id=workspace_id, session_id=session_id, kind=kind,
            target_id=target_id, revision=revision, content_json=after, updated_at=now,
        ))
    else:
        pending.revision, pending.content_json, pending.updated_at = revision, after, now
    state = "active" if reverted else ("staged" if after is not None else "deleted")
    # Back to the published content: readers see the published row and its revision.
    shown = row.revision if reverted else revision
    result = {"element": after or previous["element"], "state": state, "revision": shown, "session_id": session_id}
    db.add(InstanceHistoryRecord(
        workspace_id=workspace_id, owner_kind=OWNERS[kind], owner_id=target_id, revision=revision,
        operation=operation or ("delete" if after is None else "update"),
        before=previous, after=result, proposal_item_id=proposal_item_id, actor=actor, at=now,
    ))
    _bump(db, workspace_id)
    db.flush()
    # Deleting an object deletes its relations in the same draft.
    if after is None and kind == "material_object":
        for item in baseline(db, workspace_id, session_id)["items"]:
            element = item["element"]
            if item["target_kind"] != "material_link" or target_id not in {element["source_id"], element["target_id"]}:
                continue
            link_result = write(
                db, workspace_id, session_id, "material_link", item["target_id"], None,
                expected_revision=item["revision"], actor=actor, proposal_item_id=proposal_item_id,
                operation="endpoint_deleted", cascades=cascades,
            )
            if cascades is not None:
                cascades.append({
                    "action": "removed", "target_kind": "material_link", "target_id": item["target_id"],
                    "proposal_id": proposal_item_id, "before": deepcopy(link_result["element"]), "after": None,
                })
    return result


def _require_no_pending_links_elsewhere(db, workspace_id, session_id, object_id):
    """Deleting a published instance would also delete relations to it that another
    session has accepted but not published: refuse instead of touching their work."""
    touches = or_(InstanceLinkRecord.source_instance_id == object_id, InstanceLinkRecord.target_instance_id == object_id)
    staged = db.scalar(select(func.count()).select_from(InstanceLinkRecord).where(
        InstanceLinkRecord.workspace_id == workspace_id, InstanceLinkRecord.state == "staged",
        InstanceLinkRecord.session_id != session_id, touches))
    drafted = db.scalar(select(func.count()).select_from(InstanceDraftRecord).join(
        InstanceLinkRecord, InstanceLinkRecord.id == InstanceDraftRecord.target_id).where(
        InstanceDraftRecord.workspace_id == workspace_id, InstanceDraftRecord.kind == "material_link",
        InstanceDraftRecord.session_id != session_id, touches))
    if staged or drafted:
        fail("INSTANCE_REFERENCED_ELSEWHERE",
             "要删除的实例还有其他会话待发布的关系，请先在那个会话发布或撤销这些关系")


def activate(db, workspace_id, session_id, actor, model):
    current = baseline(db, workspace_id, session_id)
    for item in current["items"]:
        if item["state"] == "staged" and not item.get("pending_change"):
            write(
                db,
                workspace_id,
                session_id,
                item["target_kind"],
                item["target_id"],
                item["element"],
                expected_revision=item["revision"],
                actor=actor,
                state="active",
                operation="activate",
                model=model,
            )
    # Then the session's changes to published instances, relations first: an
    # object deleted later takes its remaining relations with it.
    drafts = sorted(session_drafts(db, workspace_id, session_id).values(), key=lambda d: d.kind != "material_link")
    for pending in drafts:
        cls = RECORDS[pending.kind]
        row = db.get(cls, pending.target_id)
        if pending.kind == "material_object" and pending.content_json is None:
            _require_no_pending_links_elsewhere(db, workspace_id, session_id, pending.target_id)
        if row is not None and row.state == "active":
            write(
                db, workspace_id, None, pending.kind, pending.target_id, pending.content_json,
                expected_revision=row.revision, actor=actor,
                state="active" if pending.content_json is not None else None,
                operation="activate", model=model, validated=True, reconciled=True,
                # Draft writes already used revisions in this instance's history.
                next_revision=_next_revision(db, pending.kind, pending.target_id, row.revision),
            )
        db.delete(pending)
    db.flush()


def abandon(db, workspace_id, session_id, actor):
    lock_workspace(db, workspace_id)
    session = db.scalar(
        select(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.workspace_id == workspace_id,
            ModelingSessionRecord.id == session_id,
        )
        .with_for_update()
    )
    if session is None:
        raise NotFoundError("会话不存在")
    if session.abandoned_at is not None:
        if session.abandoned_at.tzinfo is None:
            from datetime import UTC

            session.abandoned_at = session.abandoned_at.replace(tzinfo=UTC)
        return {
            "session_id": session_id,
            "abandoned_at": session.abandoned_at,
            "abandoned_by": session.abandoned_by,
        }
    current = baseline(db, workspace_id, session_id)
    # Relations first; endpoint deletion can otherwise invalidate them twice.
    for item in sorted(
        current["items"], key=lambda i: i["target_kind"] == "material_object"
    ):
        # Pending changes to published instances are simply dropped below.
        if item["state"] == "staged" and not item.get("pending_change"):
            write(
                db,
                workspace_id,
                session_id,
                item["target_kind"],
                item["target_id"],
                None,
                expected_revision=item["revision"],
                actor=actor,
                operation="abandon_session",
            )
    for pending in session_drafts(db, workspace_id, session_id).values():
        db.delete(pending)
    session.abandoned_at, session.abandoned_by = utc_now(), actor
    session.personal_owner_id = None
    session.dataagent_run_token = None
    session.task_status, session.result_state = "cancelled", "failed_permanent"
    session.run_manifest_json = {
        **(session.run_manifest_json or {}),
        "invalidated": "SESSION_ABANDONED",
    }
    session.revision += 1
    db.flush()
    return {
        "session_id": session_id,
        "abandoned_at": session.abandoned_at,
        "abandoned_by": actor,
    }


def history(db, workspace_id, kind, target_id, session_id=None):
    rows = db.scalars(
        select(InstanceHistoryRecord)
        .where(
            InstanceHistoryRecord.workspace_id == workspace_id,
            InstanceHistoryRecord.owner_kind == OWNERS[kind],
            InstanceHistoryRecord.owner_id == target_id,
        )
        .order_by(InstanceHistoryRecord.revision)
    ).all()

    # A snapshot that belongs to a session (staged, or a pending change to a
    # published instance) is that session's own until it publishes (AI-11).
    return [
        row
        for row in rows
        if all(
            not snapshot
            or snapshot.get("session_id") in (None, session_id)
            for snapshot in (row.before, row.after)
        )
    ]


def require_open_session(session):
    if session.abandoned_at is not None:
        fail("SESSION_ABANDONED", "会话已放弃")
