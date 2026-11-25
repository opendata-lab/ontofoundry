"""Session settings and human-save contracts (AI-01 through AI-04)."""

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter

from ontofoundry_api.contracts.dataset_sources import LinkedTable
from ontofoundry_api.contracts.read_models import AffectedItem
from ontofoundry_api.domain.core import CoreDraft, Strict

SessionMode = Literal["model", "chat"]


class SessionPatch(Strict):
    revision: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    material_ids: list[str] | None = None
    table_scope: Literal["all", "selected"] | None = None
    linked_tables: list[LinkedTable] | None = None
    mode: SessionMode | None = None


class ElementSavePreview(Strict):
    target_kind: Literal["object_type", "link_type", "metric", "dataset", "mapping", "value_type"]
    target_id: str
    expected_session_revision: int = Field(ge=0)
    draft: dict
    affected_items: list[AffectedItem] = Field(default_factory=list)


class ElementSave(ElementSavePreview):
    idempotency_key: str = Field(min_length=8, max_length=64)


class SessionRead(Strict):
    id: str
    title: str
    workspace_id: str
    created_by: str
    base_version_id: str | None
    revision: int
    base_version_sha256: str
    draft_sha256: str
    draft: CoreDraft
    material_ids: list[str]
    table_scope: Literal["all", "selected"]
    linked_tables: list[LinkedTable]
    mode: SessionMode
    task_status: str
    task_detail: str
    dataagent_topic_id: str | None
    dataagent_task_id: str | None
    dataagent_task_mode: str | None
    dataagent_run_token: str | None
    uploaded_material_ids: list[str]
    last_result_task_id: str | None
    result_state: str
    result_warnings: list[str]
    result_claimed_at: datetime | None
    updated_at: datetime
    abandoned_at: datetime | None
    abandoned_by: str | None
    graph: dict[str, JsonValue]
    import_source: dict[str, str] | None
    pending_proposal_count: int = Field(ge=0)
    latest_batch_id: str | None
    base_diff: list[dict[str, JsonValue]]
    unpublished_change_count: int = Field(ge=0)


ActorKind = Literal["human", "agent", "import"]
ChangeSubject = Literal["proposal", "draft", "version"]
ChangeAction = Literal[
    "created",
    "revised",
    "superseded",
    "accepted",
    "rejected",
    "restored",
    "back_to_pending",
    "added",
    "updated",
    "removed",
    "published",
]


class ChangeEventRead(Strict):
    id: str
    workspace_id: str
    session_id: str
    at: datetime
    actor_id: str
    actor_display_name: str | None = None
    actor_kind: ActorKind
    run_token: str | None = None
    subject: ChangeSubject
    action: ChangeAction
    target_kind: str | None = None
    target_id: str | None = None
    proposal_id: str | None = None
    batch_id: str | None = None
    version_id: str | None = None
    before: JsonValue = None
    after: JsonValue = None
    cause_id: str | None = None


class ChangeEventPageRead(Strict):
    items: list[ChangeEventRead]
    next_cursor: str | None = None


def session_writes_schema():
    schema = TypeAdapter(
        SessionPatch
        | ElementSavePreview
        | ElementSave
        | SessionRead
        | ChangeEventRead
        | ChangeEventPageRead
    ).json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "ontofoundry.session-writes.v1.schema.json"
    return schema
