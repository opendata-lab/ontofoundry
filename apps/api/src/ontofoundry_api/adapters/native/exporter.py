"""Native standalone definitions retain identities but do not embed material files."""

from datetime import UTC, datetime

from ontofoundry_api.adapters.exporting import ExportBuilder, file_stem
from ontofoundry_api.domain.validation import validate_core_graph


def export_document(model, ctx):
    report = ExportBuilder("ontofoundry-core-1", model)
    try:
        validate_core_graph(model)
    except ValueError as error:
        report.issue("", "error", "document", None, "核心模型校验失败：" + str(error))
        return report.finish(None, file_stem(ctx) + ".ontofoundry.json")
    report.issue(
        "",
        "converted",
        "document",
        None,
        "原生单文件保留模型定义、UUID 与证据引用；不包含材料原文，不是完整备份",
        severity="warning",
    )
    return report.finish(
        {
            "format": "ontofoundry",
            "schema_version": "core-1",
            "exported_at": ctx.exported_at or datetime.now(UTC).isoformat(),
            "draft": exchange_draft(model),
            "connection_names": {str(k): v for k, v in (ctx.connection_names or {}).items()},
        },
        file_stem(ctx) + ".ontofoundry.json",
    )


def exchange_draft(model):
    data = model.model_dump(mode="json")
    for dataset in data["datasets"]:
        dataset.pop("connection_id", None)
    return data
