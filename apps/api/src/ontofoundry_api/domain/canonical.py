"""Hash algorithm B from the proposal-first design (§4.5): domain canonicalization.

Only for v2 domain snapshots and single elements — `normalized_snapshot_sha256`,
`draft_sha256`, `element_sha256`, `merged_snapshot_sha256` and item fingerprints.
Version envelopes keep `ossie.compiler.sha256_json`; raw agent results are hashed
as bytes. The three never mix.

Two steps:
1. Semantic normalization, per field name, never guessed from data shape:
   collections keyed by id sort by id; set-like lists dedupe and sort; ordered
   lists keep their order; `None` values drop; strings become NFC. An array
   field that is not registered here raises, so adding one forces a decision.
2. Byte normalization with RFC 8785 (JCS): sorted keys, no whitespace, and the
   ECMAScript number format.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from decimal import Decimal
from typing import Any

SORTED_BY_ID = frozenset(
    {
        "object_types",
        "properties",
        "link_types",
        "rules",
        "actions",
        "material_objects",
        "material_links",
        "mappings",
        "evidence",
    }
)
SETS = frozenset({"tags", "extends", "precondition_rule_ids", "ontology_requires"})
ORDERED = frozenset({"verbalizes", "parameters", "effects"})


class CanonicalizationError(ValueError):
    pass


def _normalize(value: Any, field: str | None) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", key): _normalize(item, key)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        items = [_normalize(item, None) for item in value]
        if field in SORTED_BY_ID:
            return sorted(items, key=lambda item: str(item["id"]))
        if field in SETS:
            unique = {jcs(item): item for item in items}
            return [unique[key] for key in sorted(unique)]
        if field in ORDERED:
            return items
        raise CanonicalizationError(f"未登记的数组字段：{field!r}")
    return value


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
        text = digits[0] + ("." + digits[1:] if k > 1 else "") + ("e+" if e > 0 else "e-") + str(abs(e))
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
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + jcs(value[k]) for k in keys) + "}"
    raise CanonicalizationError(f"无法规范化的值类型：{type(value).__name__}")


def canonical(value: Any, field: str | None = None) -> str:
    return jcs(_normalize(value, field))


def domain_sha256(value: Any, field: str | None = None) -> str:
    return hashlib.sha256(canonical(value, field).encode("utf-8")).hexdigest()


def snapshot_sha256(snapshot: dict) -> str:
    """`normalized_snapshot_sha256` / `draft_sha256` / `merged_snapshot_sha256`."""
    return domain_sha256(snapshot)


def element_sha256(element: dict) -> str:
    """`element_sha256`: an element exactly as stored in the draft."""
    return domain_sha256(element)
