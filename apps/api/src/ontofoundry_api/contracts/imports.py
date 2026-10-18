"""Import workflow wire models; core definitions keep their existing schema."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from ontofoundry_api.adapters.base import TranslationReport
from ontofoundry_api.domain.core import Dataset, Strict


class ImportConfirm(Strict):
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_current_version_id: UUID | None
    idempotency_key: str = Field(min_length=8, max_length=64)


class ImportConfirmed(Strict):
    session_id: UUID
    batch_id: UUID
    report_id: UUID


class ImportBlocked(Strict):
    target_id: UUID
    reason: str


class ImportProposalSummary(Strict):
    create: int
    update: int
    unchanged: int
    blocked: list[ImportBlocked]


class ImportCompletion(Strict):
    issue_id: UUID
    message: str
    original: str | None
    source_path: str
    source_locator: dict[str, Any]
    kind: Literal["count_dataset", "dataset_metadata", "source_definition"]
    datasets: list[dict[str, str]]
    dataset: Dataset | None = None
    status: Literal["available", "proposed", "accepted"]


class ImportPreview(Strict):
    import_id: UUID
    adapter: str
    filename: str
    report: TranslationReport
    content_sha256: str
    raw_sha256: str
    formatted_sha256: str | None
    material_id: UUID | None
    base_version_id: UUID | None
    proposal_summary: ImportProposalSummary
    id_map: dict[str, str]
    current_blocked: list[ImportBlocked] = Field(default_factory=list)
    document_error: bool
    completion: list[ImportCompletion]
    confirmed: ImportConfirmed | None = None


class ImportCompletionRequest(Strict):
    issue_id: UUID
    expected_session_revision: int = Field(ge=0)
    expected_draft_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=64)
    dataset_id: UUID | None = None
    definition: dict[str, Any] | None = None
    dataset: Dataset | None = None


def imports_schema():
    return TypeAdapter(
        ImportPreview | ImportConfirm | ImportConfirmed | ImportCompletionRequest
    ).json_schema()
