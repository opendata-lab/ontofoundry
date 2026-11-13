"""Cursor-paginated feedback and full gateway audit reads."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from ontofoundry_api.db_models import (
    OntologyFeedbackRecord,
    OntologyGatewayCallRecord,
    OntologyGatewayCallWorkspaceRecord,
    OntologyVersionRecord,
    UserRecord,
    WorkspaceRecord,
)
from ontofoundry_api.domain.graph import draft_index
from ontofoundry_api.services.access import authorization_fingerprint, require_manage
from ontofoundry_api.services.cursors import decode_cursor, encode_cursor
from ontofoundry_api.services.errors import NotFoundError, ServiceError
from ontofoundry_api.services.ontology_query import current_version, read_context


def record_page(db, query, model, settings, cursor, limit, context):
    _, after = decode_cursor(settings, cursor, context)
    if cursor:
        try:
            stamp = datetime.fromisoformat(after["created_at"])
            identity = after["id"]
            if not isinstance(identity, str):
                raise ValueError()
        except (ValueError, TypeError, KeyError) as exc:
            raise ServiceError("分页游标无效", code="INVALID_CURSOR", status_code=422) from exc
        query = query.where(or_(
            model.created_at < stamp,
            and_(model.created_at == stamp, model.id < identity),
        ))
    rows = list(db.scalars(
        query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
    ))
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = encode_cursor(
            settings, context, 0,
            {"created_at": last.created_at.isoformat(), "id": last.id},
        )
    return page, next_cursor


def list_feedback(db, workspace_id, principal, settings, *, cursor=None, limit=20):
    require_manage(db, workspace_id, principal)
    rows, next_cursor = record_page(
        db,
        select(OntologyFeedbackRecord).where(
            OntologyFeedbackRecord.workspace_id == workspace_id
        ),
        OntologyFeedbackRecord, settings, cursor, limit,
        ["feedback", workspace_id, authorization_fingerprint(db, workspace_id, principal)],
    )
    space = db.get(WorkspaceRecord, workspace_id)
    index = None
    if space and space.current_version_id:
        index = draft_index(read_context(current_version(db, workspace_id)).draft)
    items = []
    for row in rows:
        elements = []
        for identity in row.element_ids:
            element = index.elements.get(UUID(identity)) if index else None
            projection = {"id": identity}
            if element:
                projection.update(name=element[1].name, display_name=element[1].display_name)
            elements.append(projection)
        user = db.get(UserRecord, row.user_id)
        number = None
        if row.version_id:
            number = db.scalar(select(OntologyVersionRecord.version_number).where(
                OntologyVersionRecord.id == row.version_id,
            ))
        items.append({
            "id": row.id,
            "created_at": row.created_at,
            "user": {"id": user.id, "display_name": user.display_name},
            "kind": row.kind,
            "user_text": row.user_text,
            "agent_text": row.agent_text,
            "elements": elements,
            "version_number": number,
        })
    return {"items": items, "next_cursor": next_cursor}


def call_workspaces(db, call_id, *, detail=False):
    rows = db.execute(
        select(OntologyGatewayCallWorkspaceRecord, WorkspaceRecord.name)
        .outerjoin(
            WorkspaceRecord,
            WorkspaceRecord.id == OntologyGatewayCallWorkspaceRecord.workspace_id,
        )
        .where(OntologyGatewayCallWorkspaceRecord.call_id == call_id)
        .order_by(OntologyGatewayCallWorkspaceRecord.workspace_id)
    )
    return [
        {
            "id": row.workspace_id,
            "name": name,
            "version_number": row.version_number,
            **({"version_id": row.version_id} if detail else {}),
        }
        for row, name in rows
    ]


def call_item(db, row, *, detail=False):
    user = db.get(UserRecord, row.user_id)
    result = {
        key: getattr(row, key)
        for key in ("id", "created_at", "tool", "outcome", "error_code", "duration_ms")
    }
    result["user"] = {"id": user.id, "display_name": user.display_name}
    result["workspaces"] = call_workspaces(db, row.id, detail=detail)
    if detail:
        result.update({
            key: getattr(row, key)
            for key in ("request_id", "arguments", "response", "error_message")
        })
    else:
        args = row.arguments
        if row.tool == "search_ontology":
            summary = args.get("query", "—")
        elif row.tool == "get_ontology":
            summary = f"{len(args['ids'])} 个元素" if args.get("ids") else "—"
        elif row.tool == "submit_feedback":
            summary = args.get("kind", "—")
        else:
            summary = "—"
        result["summary"] = summary[:240]
    return result


def list_calls(
    db, principal, settings, *, user_id=None, workspace_id=None, tool=None,
    outcome=None, from_time=None, to_time=None, cursor=None, limit=20,
):
    query = select(OntologyGatewayCallRecord)
    if workspace_id is not None:
        # Drive the workspace filter through its (workspace_id, created_at) index.
        spaces = select(OntologyGatewayCallWorkspaceRecord.call_id).where(
            OntologyGatewayCallWorkspaceRecord.workspace_id == workspace_id
        )
        if from_time:
            spaces = spaces.where(OntologyGatewayCallWorkspaceRecord.created_at >= from_time)
        if to_time:
            spaces = spaces.where(OntologyGatewayCallWorkspaceRecord.created_at <= to_time)
        query = query.where(OntologyGatewayCallRecord.id.in_(spaces))
    for column, value in (("user_id", user_id), ("tool", tool), ("outcome", outcome)):
        if value is not None:
            query = query.where(getattr(OntologyGatewayCallRecord, column) == value)
    if from_time:
        query = query.where(OntologyGatewayCallRecord.created_at >= from_time)
    if to_time:
        query = query.where(OntologyGatewayCallRecord.created_at <= to_time)
    context = [
        "gateway_calls", principal.id, user_id, workspace_id, tool, outcome,
        from_time.isoformat() if from_time else None,
        to_time.isoformat() if to_time else None,
    ]
    rows, next_cursor = record_page(
        db, query, OntologyGatewayCallRecord, settings, cursor, limit, context
    )
    return {"items": [call_item(db, row) for row in rows], "next_cursor": next_cursor}


def get_call(db, call_id):
    row = db.get(OntologyGatewayCallRecord, call_id)
    if row is None:
        raise NotFoundError("调用记录不存在", code="GATEWAY_CALL_NOT_FOUND")
    return call_item(db, row, detail=True)
