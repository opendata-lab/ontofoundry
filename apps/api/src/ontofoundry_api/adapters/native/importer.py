"""Native imports preserve identities; material lookup is injected, never a DB session."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError

from ontofoundry_api.adapters.base import (
    ImportContext,
    ImportOnlyAdapter,
    ImportResult,
    PendingMaterialEvidence,
    ReportBuilder,
)
from ontofoundry_api.adapters.documents import parse_document
from ontofoundry_api.domain.core import (
    COLLECTIONS,
    CoreDraft,
    MaterialEvidence,
    empty_draft,
)
from ontofoundry_api.domain.evidence import EvidenceError, check_material_evidence
from ontofoundry_api.domain.validation import validate_core_graph

MaterialResolver = Callable[[str], tuple[UUID, list[str]] | None]


class NativeAdapter(ImportOnlyAdapter):
    def export_document(self, model, ctx):
        from ontofoundry_api.adapters.native.exporter import export_document

        return export_document(model, ctx)

    id = "ontofoundry-core-1"
    label = "OntoFoundry 原生单文件"
    file_extensions = (".ontofoundry.json",)

    def detect(self, raw: bytes) -> bool:
        return b'"ontofoundry"' in raw[:1024]

    def import_document(self, raw: bytes, ctx: ImportContext) -> ImportResult:
        report = ReportBuilder(self.id, ctx.workspace_id, hashlib.sha256(raw).hexdigest())
        bundled = ()
        if raw.startswith(b"PK"):
            from .package import unpack

            try:
                raw, bundled = unpack(raw)
            except (ValueError, UnicodeError, KeyError, TypeError) as error:
                report.add(
                    outcome="error",
                    construct="document",
                    source_path="",
                    message="原生完整包校验失败：" + str(error),
                )
                return report.finish(empty_draft(ctx.workspace_id))
        source = parse_document(raw, report)
        empty = empty_draft(ctx.workspace_id)
        if source is None:
            return report.finish(empty)
        value = source.value
        try:
            if not isinstance(value, dict) or set(value) - {"connection_names"} != {
                "format",
                "schema_version",
                "exported_at",
                "draft",
            }:
                raise ValueError(
                    "原生单文件必须恰好包含 format、schema_version、exported_at、draft"
                )
            if value["format"] != "ontofoundry" or value["schema_version"] != "core-1":
                raise ValueError("仅支持 ontofoundry core-1 单文件，不支持其他模型版本")
            datetime.fromisoformat(value["exported_at"].replace("Z", "+00:00"))
            data = deepcopy(value["draft"])
            for dataset in data.get("datasets", []):
                hint = value.get("connection_names", {}).get(dataset["id"])
                matches = [c for c in ctx.connections if c["name"] == hint]
                dataset["connection_id"] = matches[0]["id"] if len(matches) == 1 else None
                if len(matches) == 1:
                    dataset["dialect"] = matches[0]["kind"]
            from .legacy import convert_names

            model = validate_core_graph(
                CoreDraft.model_validate(convert_names(data, report))
            )
            model.workspace_id = ctx.workspace_id
        except (ValueError, TypeError, AttributeError, ValidationError) as error:
            report.add(
                outcome="error",
                construct="document",
                source_path="",
                locator=source.locator(""),
                original=source.original(""),
                message=f"原生模型校验失败：{error}",
            )
            return report.finish(empty)
        pending = []
        for collection in COLLECTIONS:
            for position, element in enumerate(getattr(model, collection)):
                path = f"/draft/{collection}/{position}"
                for index, evidence in enumerate(getattr(element, "evidence", [])):
                    if not isinstance(evidence, MaterialEvidence):
                        continue
                    ep = f"{path}/evidence/{index}"
                    pending.append(
                        PendingMaterialEvidence(collection, element.id, evidence, ep)
                    )
                    report.add(
                        outcome="dropped",
                        construct="material_evidence",
                        source_path=ep,
                        locator=source.locator(ep),
                        original=source.original(ep),
                        message="单文件不含材料；目标空间未解析到同 SHA 材料，暂不导入该证据",
                    )
                if hasattr(element, "evidence"):
                    element.evidence = [
                        e for e in element.evidence if not isinstance(e, MaterialEvidence)
                    ]
                report.add(
                    outcome="converted",
                    construct=collection,
                    source_path=path,
                    locator=source.locator(path),
                    original=source.original(path),
                    targets=[element.id],
                    message="保留原生定义及 UUID，使用目标工作空间",
                )
        return replace(
            report.finish(validate_core_graph(model), pending), bundled_materials=bundled
        )

    def validate_document(self, document: bytes):
        return [
            issue
            for issue in self.import_document(
                document, ImportContext(UUID(int=0))
            ).report.issues
            if issue.outcome == "error"
        ]


def resolve_material_evidence(
    result: ImportResult, lookup: MaterialResolver
) -> ImportResult:
    """Return a new result after resolving same-content materials in the destination."""
    model = result.model.model_copy(deep=True)
    report = ReportBuilder(
        result.report.adapter,
        model.workspace_id,
        next((i.source_locator["sha256"] for i in result.report.issues), ""),
    )
    by_path = {p.source_path: p for p in result.pending_material_evidence}
    for issue in result.report.issues:
        pending = by_path.get(issue.source_path)
        if pending is None:
            report.issues.append(issue)
            continue
        found = lookup(pending.evidence.material_sha256)
        if found is None:
            report.issues.append(issue)
            continue
        material_id, lines = found
        evidence = pending.evidence.model_copy(update={"material_id": str(material_id)})
        try:
            check_material_evidence(
                evidence.model_dump(mode="json"),
                lambda _, sha=evidence.material_sha256, text=lines: (sha, text),
                pending.source_path,
            )
        except EvidenceError as error:
            report.issues.append(issue.model_copy(update={"message": str(error)}))
            continue
        element = next(
            e for e in getattr(model, pending.collection) if e.id == pending.element_id
        )
        element.evidence.append(evidence)
        report.issues.append(
            issue.model_copy(
                update={
                    "outcome": "converted",
                    "severity": "info",
                    "target_element_ids": [element.id],
                    "message": "按 SHA 复用目标空间材料，保留证据 UUID、原文和行号",
                }
            )
        )
    return report.finish(validate_core_graph(model))
