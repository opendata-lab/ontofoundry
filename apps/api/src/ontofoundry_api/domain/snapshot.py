"""Strict stored core-1 snapshot boundary."""

from uuid import UUID

from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.models import OntologyDraft


def empty_snapshot(workspace_id: str | UUID) -> dict:
    return OntologyDraft(workspace_id=workspace_id).model_dump(mode="json")


def read_snapshot(data: dict, workspace_id: str | UUID | None = None) -> OntologyDraft:
    if not isinstance(data, dict) or data.get("schema_version") != "core-1":
        raise ValueError("只接受显式声明 schema_version=core-1 的快照")
    draft = OntologyDraft.model_validate(data)
    if workspace_id is not None and str(draft.workspace_id) != str(workspace_id):
        raise ValueError("快照不属于该工作空间")
    return draft


def read_snapshot_json(data: dict, workspace_id: str | UUID | None = None) -> dict:
    return read_snapshot(data, workspace_id).model_dump(mode="json")


def draft_sha256(data: dict) -> str:
    if data.get("schema_version") != "core-1":
        raise ValueError("只接受 core-1 草稿")
    return snapshot_sha256(data)


def normalized_snapshot_sha256(data: dict) -> str:
    return draft_sha256(data)
