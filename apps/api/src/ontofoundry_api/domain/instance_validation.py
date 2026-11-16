"""Value checks shared by publication and previews; never coerce business facts."""

import math
import re
from datetime import date, datetime
from decimal import Decimal

from ontofoundry_api.domain.models import OntologyDraft

KIND_NAMES = {"string": "文本", "boolean": "布尔值", "date": "日期", "datetime": "日期时间"}
NUMBER_KINDS = {"integer", "decimal", "float"}


def valid_value(kind: str, value, *, numeral_text: bool = True) -> bool:
    """`numeral_text`: whether a plain numeral written as text counts as a number.

    Database rows carry decimals as text to keep their precision, so reads allow it.
    Document instances are written by agents and people and must state numbers as
    numbers, so a stored value compares and computes as one."""
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return type(value) is int or (
            numeral_text and isinstance(value, str) and bool(re.fullmatch(r"-?\d+", value))
        )
    if kind in ("decimal", "float"):
        return (
            type(value) is int
            or (type(value) is float and math.isfinite(value))
            or (isinstance(value, Decimal) and value.is_finite())
            or (
                numeral_text
                and isinstance(value, str)
                and bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value))
            )
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


def value_issues(
    draft: OntologyDraft, type_id, values: dict, path: str, *, numeral_text: bool = True
) -> list[dict]:
    issues = []
    for attribute in draft.effective_properties(type_id):
        value = values.get(attribute.name)
        code = None
        # A fact taken from a document is identified by what the text says and
        # where; documents rarely carry system numbers. A missing value is
        # something to complete later, not a reason to block the model. A value
        # of the wrong kind, though, is wrong.
        if (attribute.required or attribute.identifier) and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            code, severity, message = (
                "INSTANCE_REQUIRED",
                "warning",
                f"{attribute.display_name or attribute.name} 待补全：原文未提供",
            )
        elif value is not None and not valid_value(
            attribute.value_kind, value, numeral_text=numeral_text
        ):
            kind = attribute.value_kind.value
            expected = {"integer": "整数", "decimal": "数字", "float": "数字"}.get(kind) or KIND_NAMES.get(kind, kind)
            if kind in NUMBER_KINDS and isinstance(value, str):
                expected += f"，不能写成文本 {value!r}"
            code, severity, message = (
                "INSTANCE_VALUE_TYPE",
                "error",
                f"{attribute.display_name or attribute.name}（{attribute.name}）必须是{expected}",
            )
        if code:
            issues.append(
                {
                    "severity": severity,
                    "code": code,
                    "path": f"{path}.{attribute.name}",
                    "message": message,
                }
            )
    return issues


def instance_issues(draft: OntologyDraft) -> list[dict]:
    """Errors only: what makes an instance invalid and blocks accepting it."""
    return [issue for issue in _instance_findings(draft) if issue["severity"] == "error"]


def _instance_findings(draft: OntologyDraft) -> list[dict]:
    return []


def completeness_warnings(draft: OntologyDraft) -> list[dict]:
    """A document often names a concept without saying what it records. That
    is a valid model, but it should be finished from a table or by hand."""
    # A parent that others extend is a category; it needs no fields of its own.
    parents = {
        str(parent) for item in draft.object_types for parent in draft.parent_ids(item)
    }
    return [
        {
            "severity": "warning",
            "code": "OBJECT_WITHOUT_PROPERTIES",
            "path": f"$.object_types[{index}]",
            "message": f"业务对象“{item.display_name or item.name}”还没有属性，可从数据表补全（自下而上）或人工添加",
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
