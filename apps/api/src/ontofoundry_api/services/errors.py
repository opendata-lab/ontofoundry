class ServiceError(Exception):
    """Rendered as {"error": {"code", "message", **details}}.

    `details` carries structured fields such as `items`, `conflicts` or
    `current_version_id`; it can never replace `code` or `message`.
    """

    status_code = 400
    code = "SERVICE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}


class NotFoundError(ServiceError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(ServiceError):
    status_code = 409
    code = "CONFLICT"


class PublishValidationError(ServiceError):
    status_code = 422
    code = "CORE_VALIDATION_FAILED"

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report
        self.details = {"errors": report.get("errors", [])}


class DatasetSourceError(ServiceError):
    status_code = 422
    code = "DATASET_SOURCE_INVALID"


class MetadataSyncError(ServiceError):
    status_code = 422
    code = "METADATA_SYNC_FAILED"
