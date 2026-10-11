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
    # Documents state numbers as text; a plain numeral is unambiguous, so it is
    # a valid value as written (checked, never converted). "约240元" is not.
    if kind == "integer":
        return type(value) is int or (
            isinstance(value, str) and bool(re.fullmatch(r"-?\d+", value))
        )
    if kind in ("decimal", "float"):
        return (
            type(value) is int
            or (type(value) is float and math.isfinite(value))
            or (isinstance(value, Decimal) and value.is_finite())
            or (isinstance(value, str) and bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value)))
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
            # Documents write "2026-01-20 10:12" or just the day; both are a
            # point in time at the precision the text gives.
            return bool(
                re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}"
                    r"(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?",
                    value,
                )
            ) and bool(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return False
    return False


def value_issues(draft: OntologyDraft, type_id, values: dict, path: str) -> list[dict]:
    issues = []
    for attribute in draft.effective_properties(type_id):
        value = values.get(attribute.technical_name)
        code = None
        # A fact taken from a document is identified by what the text says and
        # where; documents rarely carry system numbers. A missing value is
        # something to complete later, not a reason to block the model. A value
        # of the wrong kind, though, is wrong.
        if (attribute.required or attribute.identifier) and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            code, severity, message = (
                "INSTANCE_REQUIRED", "warning", f"{attribute.name} 待补全：原文未提供"
            )
        elif value is not None and not valid_value(attribute.value_kind, value):
            code, severity, message = (
                "INSTANCE_VALUE_TYPE",
                "error",
                f"{attribute.name} 必须是 {attribute.value_kind} 类型",
            )
        if code:
            issues.append(
                {
                    "severity": severity,
                    "code": code,
                    "path": f"{path}.{attribute.technical_name}",
                    "message": message,
                }
            )
    return issues


def instance_issues(draft: OntologyDraft) -> list[dict]:
    """Errors only: what makes an instance invalid and blocks accepting it."""
    return [issue for issue in _instance_findings(draft) if issue["severity"] == "error"]


def _instance_findings(draft: OntologyDraft) -> list[dict]:
    return [
        issue
        for index, obj in enumerate(draft.material_objects)
        for issue in value_issues(
            draft, obj.type_id, obj.values, f"$.material_objects[{index}].values"
        )
    ]


def completeness_warnings(draft: OntologyDraft) -> list[dict]:
    """A document often names a concept without saying what it records. That
    is a valid model, but it should be finished from a table or by hand."""
    # A parent that others extend is a category; it needs no fields of its own.
    parents = {str(parent) for item in draft.object_types for parent in draft.parent_ids(item)}
    return [
        {
            "severity": "warning",
            "code": "OBJECT_WITHOUT_PROPERTIES",
            "path": f"$.object_types[{index}]",
            "message": f"业务对象“{item.name}”还没有属性，可从数据表补全（自下而上）或人工添加",
        }
        for index, item in enumerate(draft.object_types)
        if str(item.id) not in parents and not draft.effective_properties(item.id)
    ]


def include_instance_validation(report: dict, draft: OntologyDraft) -> dict:
    findings = _instance_findings(draft)
    errors = [issue for issue in findings if issue["severity"] == "error"]
    warnings = [issue for issue in findings if issue["severity"] != "error"]
    return {
        **report,
        "errors": [*report.get("errors", []), *errors],
        "warnings": [*report.get("warnings", []), *warnings, *completeness_warnings(draft)],
        "instance_status": "failed" if errors else "passed",
        "publishable": report["publishable"] and not errors,
    }
