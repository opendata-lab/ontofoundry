class ServiceError(Exception):
    status_code = 400
    code = "SERVICE_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(ServiceError):
    status_code = 409
    code = "CONFLICT"


class PublishValidationError(ServiceError):
    status_code = 422
    code = "OSSIE_VALIDATION_FAILED"

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report
