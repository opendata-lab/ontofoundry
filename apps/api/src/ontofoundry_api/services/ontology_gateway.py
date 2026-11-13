"""User-scoped gateway tools, reusing the single-workspace ontology readers."""

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator
from sqlalchemy import and_, select

from ontofoundry_api.contracts.read_models import OntologySearchRequest
from ontofoundry_api.db_models import (
    OntologyFeedbackRecord,
    OntologyVersionRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
)
from ontofoundry_api.domain.core import Strict
from ontofoundry_api.domain.graph import draft_index
from ontofoundry_api.services.access import can_read_workspace
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.mcp_ontology import BUDGET, GetOntology, size
from ontofoundry_api.services.mcp_ontology import invoke as read_tool
from ontofoundry_api.services.ontology_query import current_version, read_context

VERSIONS_META = "io.github.opendata-lab.ontofoundry/versions"
MAX_SEARCH_WORKSPACES = 10
VERSION_FIELDS = ("workspace_id", "version_id", "version_number")


class ListSpaces(Strict):
    pass


class SearchOntology(OntologySearchRequest):
    workspace_ids: list[str] | None = None


class GatewayGetOntology(GetOntology):
    workspace_id: str


class SubmitFeedback(Strict):
    workspace_id: str
    kind: Literal["correction", "suggestion"]
    user_text: str = Field(min_length=1, max_length=4000)
    agent_text: str = Field(min_length=1, max_length=4000)
    element_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("user_text", "agent_text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("反馈文本不能为空")
        return value


INPUTS = {
    "list_spaces": ListSpaces,
    "search_ontology": SearchOntology,
    "get_ontology": GatewayGetOntology,
    "submit_feedback": SubmitFeedback,
}


@dataclass
class GatewayContext:
    versions: list[dict] = field(default_factory=list)
    workspace_ids: list[str] = field(default_factory=list)
    spaces: list[dict] | None = None


def directory(db, principal, *, members_only=False):
    # Select only the published version number; the directory never loads snapshots.
    query = (
        select(
            WorkspaceRecord,
            WorkspaceMemberRecord.role,
            OntologyVersionRecord.version_number,
        )
        .outerjoin(WorkspaceMemberRecord, and_(
            WorkspaceMemberRecord.workspace_id == WorkspaceRecord.id,
            WorkspaceMemberRecord.user_id == principal.id,
        ))
        .outerjoin(
            OntologyVersionRecord,
            OntologyVersionRecord.id == WorkspaceRecord.current_version_id,
        )
    )
    if members_only:
        query = query.where(WorkspaceMemberRecord.role.is_not(None))
    else:
        query = query.where(
            WorkspaceMemberRecord.role.is_not(None)
            | WorkspaceRecord.is_public
            | principal.is_platform_admin
        )
    return [
        {
            "workspace_id": space.id,
            "name": space.name,
            "role": role or ("admin" if principal.is_platform_admin else "public"),
            "version_id": space.current_version_id,
            "version_number": number,
        }
        for space, role, number in db.execute(
            query.order_by(WorkspaceRecord.name, WorkspaceRecord.id)
        )
        if can_read_workspace(db, space.id, principal)
    ]


def prepare_targets(db, principal, name, args, context):
    if name == "list_spaces" or (name == "search_ontology" and args.workspace_ids is None):
        context.spaces = directory(db, principal, members_only=name == "search_ontology")
        context.workspace_ids = [space["workspace_id"] for space in context.spaces]
        return [{key: space[key] for key in VERSION_FIELDS} for space in context.spaces]
    if name == "search_ontology":
        context.workspace_ids = list(dict.fromkeys(args.workspace_ids))
    else:
        context.workspace_ids = [args.workspace_id]
    return audit_workspaces(context)


def workspace_version(db, workspace_id, principal, context):
    if not can_read_workspace(db, workspace_id, principal):
        raise ServiceError(
            "空间不存在或不可阅读", code="workspace_unavailable", status_code=404
        )
    space = db.get(WorkspaceRecord, workspace_id)
    number = None
    if space.current_version_id:
        number = db.scalar(select(OntologyVersionRecord.version_number).where(
            OntologyVersionRecord.id == space.current_version_id,
        ))
    version = {
        "workspace_id": workspace_id,
        "version_id": space.current_version_id,
        "version_number": number,
    }
    context.versions.append(version)
    return version


def invoke(db, principal, name, args, settings, context):
    if name == "list_spaces":
        spaces = context.spaces
        if spaces is None:
            spaces = directory(db, principal)
        context.workspace_ids = [space["workspace_id"] for space in spaces]
        context.versions = [{key: space[key] for key in VERSION_FIELDS} for space in spaces]
        return {"spaces": spaces, "permissions": sorted(principal.scopes)}
    if name == "search_ontology":
        if args.workspace_ids is None:
            spaces = context.spaces
            if spaces is None:
                spaces = directory(db, principal, members_only=True)
            ids = [space["workspace_id"] for space in spaces]
        else:
            ids = list(dict.fromkeys(args.workspace_ids))
        context.workspace_ids = ids
        # Check every explicit target before returning any group.
        for wid in ids:
            workspace_version(db, wid, principal, context)
        if len(ids) > MAX_SEARCH_WORKSPACES:
            raise ServiceError(
                "检索空间超过上限，请缩小空间范围",
                code="search_limit_exceeded",
                details={"reason": "workspace_count", "limit": MAX_SEARCH_WORKSPACES},
            )
        if args.cursor and len(ids) != 1:
            raise ServiceError(
                "翻页时请只指定游标所属空间", code="invalid_arguments", status_code=422
            )
        ids.sort(key=lambda wid: (db.get(WorkspaceRecord, wid).name, wid))
        options = args.model_dump(mode="json", exclude={"workspace_ids"})
        groups = [read_tool(db, wid, principal, name, options, settings) for wid in ids]
        if sum(size(group) for group in groups) > BUDGET:
            raise ServiceError(
                "检索结果超过响应预算，请缩小 limit 或空间范围",
                code="search_limit_exceeded",
                details={"reason": "response_size"},
            )
        return {"groups": groups}
    wid = args.workspace_id
    context.workspace_ids = [wid]
    version = workspace_version(db, wid, principal, context)
    if name == "get_ontology":
        return read_tool(
            db, wid, principal, name,
            args.model_dump(mode="json", exclude={"workspace_id"}), settings,
        )
    element_ids = list(dict.fromkeys(str(identity) for identity in args.element_ids))
    if element_ids:
        index = None
        if version["version_id"]:
            draft = read_context(current_version(db, wid, version["version_id"])).draft
            index = draft_index(draft)
        if index is None or any(UUID(identity) not in index.elements for identity in element_ids):
            raise ServiceError(
                "相关元素须属于该空间的当前发布版本",
                code="invalid_arguments", status_code=422,
            )
    item = OntologyFeedbackRecord(
        id=str(uuid4()),
        workspace_id=wid,
        user_id=principal.id,
        token_id=principal.service_token_id.removeprefix("pat:"),
        kind=args.kind,
        user_text=args.user_text,
        agent_text=args.agent_text,
        element_ids=element_ids,
        version_id=version["version_id"],
    )
    db.add(item)
    db.commit()
    return {
        "feedback_id": item.id,
        "workspace_id": wid,
        "version_id": item.version_id,
        "created_at": item.created_at,
    }


def audit_workspaces(context):
    known = {version["workspace_id"]: version for version in context.versions}
    return [
        known.get(wid, {"workspace_id": wid, "version_id": None, "version_number": None})
        for wid in dict.fromkeys(context.workspace_ids)
    ]
