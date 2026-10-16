"""Core-1 canonicalization and RFC 8785 byte serialization."""

import hashlib
import json
import math
from decimal import Decimal
from typing import Any


class CanonicalizationError(ValueError):
    pass


def _number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        raise CanonicalizationError("JCS 不允许 NaN 或 Infinity")
    if value == 0:
        return "0"  # also -0
    # repr is the shortest round-trip form, the same digits ECMAScript picks;
    # only the layout differs, so rebuild it with the ES rules.
    _, digit_tuple, exponent = Decimal(repr(abs(value))).normalize().as_tuple()
    digits = "".join(map(str, digit_tuple))
    k, n = len(digits), len(digits) + exponent
    if k <= n <= 21:
        text = digits + "0" * (n - k)
    elif 0 < n <= 21:
        text = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        text = "0." + "0" * -n + digits
    else:
        e = n - 1
        text = (
            digits[0]
            + ("." + digits[1:] if k > 1 else "")
            + ("e+" if e > 0 else "e-")
            + str(abs(e))
        )
    return ("-" if value < 0 else "") + text


def jcs(value: Any) -> str:
    """RFC 8785 serialization of already-normalized JSON data."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(jcs(item) for item in value) + "]"
    if isinstance(value, dict):
        # JCS orders keys by UTF-16 code units.
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return (
            "{"
            + ",".join(
                json.dumps(k, ensure_ascii=False) + ":" + jcs(value[k]) for k in keys
            )
            + "}"
        )
    raise CanonicalizationError(f"无法规范化的值类型：{type(value).__name__}")


def canonical(value: Any, field: str | None = None) -> str:
    from ontofoundry_api.domain.core_canonical import _normalize

    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return jcs(_normalize(value, field))


def domain_sha256(value: Any, field: str | None = None) -> str:
    return hashlib.sha256(
        ("ontofoundry-core-1\n" + canonical(value, field)).encode()
    ).hexdigest()


def snapshot_sha256(snapshot: dict) -> str:
    from ontofoundry_api.domain.core_canonical import draft_sha256

    return draft_sha256(snapshot)


def element_sha256(element: dict, *, collection: str) -> str:
    from ontofoundry_api.domain.core_canonical import element_sha256 as digest

    return digest(element, collection)


def verify_snapshot_sha256(snapshot: dict, expected: str) -> bool:
    return snapshot_sha256(snapshot) == expected
