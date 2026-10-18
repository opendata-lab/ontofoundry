"""Export reports identify core source elements and immutable delivered bytes."""

import hashlib
import json
import re
from uuid import uuid5

from ontofoundry_api.adapters.base import ExportResult, ReportBuilder
from ontofoundry_api.domain.core_canonical import draft_sha256


def json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode()


def file_stem(ctx):
    return re.sub(r"[^A-Za-z0-9_-]", "_", ctx.workspace_slug)[:100] or "ontology"


class ExportBuilder:
    def __init__(self, adapter, model):
        self.model = model
        self.report = ReportBuilder(adapter, model.workspace_id, draft_sha256(model))

    def issue(
        self,
        path,
        outcome,
        construct,
        rule,
        message,
        *,
        element=None,
        target_path=None,
        completion=False,
        severity=None,
    ):
        item = self.report.add(
            source_path=path,
            outcome=outcome,
            construct=construct,
            rule_id=rule,
            message=message,
            locator={
                "sha256": self.report.source_sha256,
                **({"element_id": str(element.id)} if element else {}),
            },
            original=element.model_dump_json(indent=2) if element else None,
            targets=[element.id] if element else [],
            completion=completion,
            severity=severity,
        )
        if target_path is not None:
            self.report.issues[-1] = item.model_copy(update={"target_path": target_path})

    def finish(self, value, filename):
        report = self.report.finish(self.model).report
        document = (
            None
            if value is None or any(i.outcome == "error" for i in report.issues)
            else json_bytes(value)
        )
        digest = (
            hashlib.sha256(document).hexdigest()
            if document is not None
            else report.content_sha256
        )
        report = report.model_copy(
            update={
                "direction": "export",
                "content_sha256": digest,
                "id": uuid5(
                    self.model.workspace_id,
                    "export-report:" + report.content_sha256 + ":" + digest,
                ),
            }
        )
        return ExportResult(
            document=document,
            media_type="application/json",
            filename=filename,
            report=report,
        )
