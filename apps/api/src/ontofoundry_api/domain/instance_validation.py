"""Value checks shared by publication and previews; never coerce business facts."""

import math
import re
from datetime import date, datetime
from decimal import Decimal

from ontofoundry_api.domain.models import OntologyDraft


def valid_value(kind: str, value) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return type(value) is int
    if kind in ("decimal", "float"):
        return (
            type(value) is int
            or (type(value) is float and math.isfinite(value))
            or (isinstance(value, Decimal) and value.is_finite())
        )
    if kind == "date" and type(value) is date:
        return True
    if kind == "datetime" and isinstance(value, datetime):
        return True
    if not isinstance(value, str):
        return False
    try:
        if kind == "date":
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and bool(
                date.fromisoformat(value)
            )
        if kind == "datetime":
            return bool(re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value)) and bool(
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            )
    except ValueError:
        return False
    return False


def value_issues(draft: OntologyDraft, type_id, values: dict, path: str) -> list[dict]:
    issues = []
    for attribute in draft.effective_attributes(type_id):
        value = values.get(attribute.technical_name)
        code = None
        if (attribute.required or attribute.identifier) and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            code, message = "INSTANCE_REQUIRED", f"{attribute.name} 不能为空"
        elif value is not None and not valid_value(attribute.value_kind, value):
            code, message = (
                "INSTANCE_VALUE_TYPE",
                f"{attribute.name} 必须是 {attribute.value_kind} 类型",
            )
        if code:
            issues.append(
                {
                    "severity": "error",
                    "code": code,
                    "path": f"{path}.{attribute.technical_name}",
                    "message": message,
                }
            )
    return issues


def instance_issues(draft: OntologyDraft) -> list[dict]:
    return [
        issue
        for index, obj in enumerate(draft.objects)
        for issue in value_issues(
            draft, obj.type_id, obj.values, f"$.objects[{index}].values"
        )
    ]


def include_instance_validation(report: dict, draft: OntologyDraft) -> dict:
    issues = instance_issues(draft)
    return {
        **report,
        "errors": [*report.get("errors", []), *issues],
        "instance_status": "failed" if issues else "passed",
        "publishable": report["publishable"] and not issues,
    }
