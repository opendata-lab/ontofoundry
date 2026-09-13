"""Reject unusable live facts before creating references or encoding HTTP JSON."""

import json
import math
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder


def source_key(value):
    if (
        not isinstance(value, (str, int, float, Decimal, date, datetime, UUID))
        or isinstance(value, bool)
        or (isinstance(value, float) and not math.isfinite(value))
        or (isinstance(value, Decimal) and not value.is_finite())
        or not str(value).strip()
        or len(str(value)) > 2000
    ):
        raise HTTPException(
            422,
            {
                "code": "INVALID_SOURCE_KEY",
                "message": "源数据标识为空、过长或类型不受支持，请检查映射标识字段",
            },
        )
    return str(value)


def validate_source_rows(rows):
    keys = [source_key(row.get("__key")) for row in rows]
    if len(keys) != len(set(keys)):
        raise HTTPException(
            422,
            {
                "code": "DUPLICATE_SOURCE_KEY",
                "message": "查询结果中实例标识不唯一，请检查映射标识字段",
            },
        )
    try:
        # In particular, IEEE NaN/Infinity and non-finite Decimal must never make
        # REST return 500 while MCP silently emits nonstandard JSON numbers.
        json.dumps(jsonable_encoder(rows), allow_nan=False)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(
            422,
            {
                "code": "UNSUPPORTED_SOURCE_VALUE",
                "message": "源数据包含非有限数值或无法表示为 JSON 的值，请检查字段类型",
            },
        ) from exc
