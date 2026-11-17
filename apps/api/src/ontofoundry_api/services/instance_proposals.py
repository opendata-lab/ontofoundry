"""Instance side of mixed proposal acceptance/undo, in the decision transaction."""

from copy import deepcopy

from sqlalchemy import select

from ontofoundry_api.db_models import InstanceHistoryRecord
from ontofoundry_api.domain.instances import INSTANCE_KINDS, definitions, validate_instances
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services import instance_store
from ontofoundry_api.services.errors import ServiceError


def check_undo(db, workspace_id, session_id, item, *, after_newer_undo=False, newer_undo_starts_at=None):
    """``after_newer_undo``: a newer change to the same instance is undone first in
    this request, so this one must end where that one started; the database is not
    at this item's revision yet."""
    cls = instance_store.RECORDS[item.target_kind]
    row = db.scalar(
        select(cls)
        .where(cls.workspace_id == workspace_id, cls.id == item.target_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    pending = instance_store.session_drafts(db, workspace_id, session_id, item.target_kind).get(item.target_id)
    current = pending.revision if pending is not None else (row.revision if row is not None else None)
    if after_newer_undo:
        current = newer_undo_starts_at
    if (
        row is None
        or current != item.accepted_instance_revision
        or (row.state == "staged" and row.session_id != session_id)
    ):
        raise ServiceError(
            "实例在接受后又被修改，不能直接撤销",
            code="PROPOSAL_UNDO_CONFLICT",
            status_code=409,
        )
    link_drafts = instance_store.session_drafts(db, workspace_id, session_id, "material_link")
    for entry in cascade_history(db, workspace_id, item):
        linked = db.get(instance_store.RECORDS["material_link"], entry.owner_id)
        draft = link_drafts.get(entry.owner_id)
        if (
            linked is None
            or linked.workspace_id != workspace_id
            or (draft.revision if draft is not None else linked.revision) != entry.revision
        ):
            raise ServiceError(
                "关联关系在删除后又被修改，不能直接撤销",
                code="PROPOSAL_UNDO_CONFLICT",
                status_code=409,
            )


def cascade_history(db, workspace_id, item):
    return db.scalars(
        select(InstanceHistoryRecord).where(
            InstanceHistoryRecord.workspace_id == workspace_id,
            InstanceHistoryRecord.proposal_item_id == item.id,
            InstanceHistoryRecord.operation == "endpoint_deleted",
        )
    ).all()


def apply_changes(db, workspace_id, session_id, combined, accepted, undone, actor, lookup, *, instance_states=None, cascades_out=None):
    model = OntologyDraft.model_validate(definitions(combined))
    objects = {o["id"]: o for o in combined.get("material_objects", [])}
    links = list(combined.get("material_links", []))
    cascades = [
        entry
        for item in undone
        if item.target_kind in INSTANCE_KINDS
        for entry in cascade_history(db, workspace_id, item)
    ]
    links += [entry.before["element"] for entry in cascades]
    links = [
        link for link in links if {link["source_id"], link["target_id"]} <= set(objects)
    ]
    changing = [i for i in [*undone, *accepted] if i.target_kind in INSTANCE_KINDS]
    written: dict[str, int] = {}  # revision each instance is at after this request's earlier writes
    # Several changes to one instance undone together: only the end state matters, so
    # write the oldest one's inverse once, from the revision the newest one left.
    oldest_undo, newest_revision = {}, {}
    for item in undone:
        if item.target_kind in INSTANCE_KINDS:
            oldest_undo[item.target_id] = item
            newest_revision.setdefault(item.target_id, item.accepted_instance_revision)
    ids = {i.target_id for i in changing if i.target_kind == "material_object"}
    changed_links = [
        e
        for e in links
        if e["id"] in {i.target_id for i in changing}
        or {e["source_id"], e["target_id"]} & ids
    ]
    ids.update(
        endpoint for e in changed_links for endpoint in (e["source_id"], e["target_id"])
    )
    try:
        validate_instances(
            model, [o for key, o in objects.items() if key in ids], changed_links
        )
    except ValueError as exc:
        raise ServiceError(str(exc), code="VALIDATION_FAILED", status_code=422) from exc
    current = instance_store.baseline(db, workspace_id, session_id)
    active = {i["target_id"] for i in current["items"] if i["state"] == "active"}
    for item, undo in [*((i, True) for i in undone), *((i, False) for i in accepted)]:
        if item.target_kind not in INSTANCE_KINDS:
            continue
        if undo and oldest_undo.get(item.target_id) is not item:
            item.accepted_instance_revision = None
            continue
        if undo:
            written.setdefault(item.target_id, newest_revision[item.target_id])
        after = item.before_json if undo else item.after_json
        # Accepting never makes an instance visible: it waits for the session's
        # publish (AI-11). The store keeps a new instance staged and a change to
        # a published one in the session's draft.
        state = "staged" if after else None
        result = instance_store.write(
            db,
            workspace_id,
            session_id,
            item.target_kind,
            item.target_id,
            after,
            expected_revision=written.get(item.target_id, item.accepted_instance_revision)
            if undo
            else item.expected_instance_revision,
            actor=actor,
            proposal_item_id=item.id,
            state=state,
            operation="undo" if undo else item.operation,
            lookup=lookup,
            model=model,
            validated=instance_states is not None,
            cascades=cascades_out,
        )
        written[item.target_id] = result["revision"]
        item.accepted_instance_revision = result["revision"] if not undo else None
        if state == "active":
            active.add(item.target_id)
        else:
            active.discard(item.target_id)
    for entry in cascades:
        before = entry.before
        restored = instance_store.write(
            db,
            workspace_id,
            before["session_id"] or session_id,
            "material_link",
            entry.owner_id,
            before["element"],
            expected_revision=entry.revision,
            actor=actor,
            proposal_item_id=entry.proposal_item_id,
            # A published relation only had its delete pending: undoing drops it.
            state=None if before["state"] == "active" else before["state"],
            operation="undo_endpoint_delete",
            lookup=lookup,
            model=model,
        )
        if cascades_out is not None:
            cascades_out.append(
                {
                    "action": "added",
                    "target_kind": "material_link",
                    "target_id": entry.owner_id,
                    "proposal_id": entry.proposal_item_id,
                    "before": None,
                    "after": deepcopy(restored["element"]),
                }
            )
    return model.model_dump(mode="json")
