"""Check declared join columns using the core graph and collected metadata only."""

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.errors import ServiceError


def validate_join_columns(db, workspace_id, before, after, settings):
    try:
        validate_core_graph(CoreDraft.model_validate(after))
    except ValueError as exc:
        raise ServiceError(
            "定义引用校验失败：" + str(exc), code="JOIN_COLUMN_NOT_FOUND", status_code=422
        ) from exc
