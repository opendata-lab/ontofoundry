"""Pure format translation contracts; persistence belongs to the import service."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from ontofoundry_api.domain.core import COLLECTIONS, CoreDraft, MaterialEvidence


class TranslationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["converted", "dropped", "error"]
    construct: str
    id: UUID
    rule_id: str | None = None
    severity: Literal["info", "warning", "error"]
    source_path: str
    source_locator: dict
    original: str | None = None
    target_element_ids: list[UUID] = Field(default_factory=list)
    completion_status: Literal["not_needed", "available"] = "not_needed"
    target_path: str | None = None
    message: str


class TranslationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    content_sha256: str
    direction: Literal["import", "export"]
    adapter: str
    counts: dict[str, int]
    issues: list[TranslationIssue]


@dataclass(frozen=True)
class ImportContext:
    workspace_id: UUID


@dataclass(frozen=True)
class PendingMaterialEvidence:
    collection: str
    element_id: UUID
    evidence: MaterialEvidence
    source_path: str


@dataclass(frozen=True)
class ImportResult:
    model: CoreDraft
    report: TranslationReport
    pending_material_evidence: tuple[PendingMaterialEvidence, ...] = ()


@dataclass(frozen=True)
class ExportContext:
    workspace_name: str
    workspace_slug: str
    workspace_description: str
    exported_at: str | None = None
    dataset_scopes: dict[UUID, str] | None = None


@dataclass(frozen=True)
class ExportResult:
    document: bytes | None
    media_type: str
    filename: str
    report: TranslationReport


@dataclass(frozen=True)
class RoundTripDiff:
    source_path: str
    target_path: str | None
    rule_id: str
    message: str


class FormatAdapter(Protocol):
    id: str
    label: str
    file_extensions: tuple[str, ...]

    def detect(self, raw: bytes) -> bool: ...
    def import_document(self, raw: bytes, ctx: ImportContext) -> ImportResult: ...
    def export_document(self, model: CoreDraft, ctx: ExportContext) -> ExportResult: ...
    def validate_document(self, document: bytes) -> list[TranslationIssue]: ...
    def diff_roundtrip(self, original: bytes, exported: bytes) -> list[RoundTripDiff]: ...


class ImportOnlyAdapter:
    def export_document(self, model: CoreDraft, ctx: ExportContext) -> ExportResult:
        raise NotImplementedError("导出在 P5 开放")

    def diff_roundtrip(self, original: bytes, exported: bytes) -> list[RoundTripDiff]:
        raise NotImplementedError("往返比较在 P5 开放")


def canonical_bytes(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


@dataclass
class ReportBuilder:
    adapter: str
    workspace_id: UUID
    source_sha256: str
    issues: list[TranslationIssue] = field(default_factory=list)

    def add(
        self,
        *,
        outcome,
        construct,
        source_path,
        message,
        locator=None,
        original=None,
        rule_id=None,
        targets=(),
        completion=False,
        severity=None,
    ):
        key = canonical_bytes([source_path, construct, rule_id, outcome, message]).decode()
        item = TranslationIssue(
            id=uuid5(self.workspace_id, "translation:" + key),
            outcome=outcome,
            construct=construct,
            rule_id=rule_id,
            severity=severity
            or (
                "error"
                if outcome == "error"
                else "warning"
                if outcome == "dropped"
                else "info"
            ),
            source_path=source_path,
            source_locator=locator or {"sha256": self.source_sha256},
            original=original,
            target_element_ids=list(targets),
            completion_status="available" if completion else "not_needed",
            message=message,
        )
        self.issues.append(item)
        return item

    def finish(self, model: CoreDraft, pending=()) -> ImportResult:
        payload = {
            "source_sha256": self.source_sha256,
            "adapter": self.adapter,
            "model": model.model_dump(mode="json"),
            "issues": [i.model_dump(mode="json") for i in self.issues],
        }
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        counts = {name: len(getattr(model, name)) for name in COLLECTIONS}
        counts.update(
            {
                outcome: sum(i.outcome == outcome for i in self.issues)
                for outcome in ("converted", "dropped", "error")
            }
        )
        return ImportResult(
            model,
            TranslationReport(
                id=uuid5(self.workspace_id, "report:" + digest),
                content_sha256=digest,
                direction="import",
                adapter=self.adapter,
                counts=counts,
                issues=list(self.issues),
            ),
            tuple(pending),
        )
