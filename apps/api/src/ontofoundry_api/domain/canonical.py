"""Hash algorithm B from the proposal-first design (§4.5): domain canonicalization.

The legacy algorithm remains frozen for v1/v2. The path-aware v3 algorithm is
explicitly versioned below. Only for domain snapshots and single elements — `normalized_snapshot_sha256`,
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


# Frozen algorithm names: absence of hash_algorithm means the historical B
# algorithm (v1 snapshots are first normalized to v2 at the snapshot boundary).
LEGACY_HASH_ALGORITHM = "ontofoundry-domain-v2"
V3_HASH_ALGORITHM = "ontofoundry-domain-v3"
V3_COLLECTIONS = SORTED_BY_ID | frozenset({
    "value_types", "semantic_models", "datasets", "dataset_fields",
    "dataset_relationships", "metrics", "concept_mappings", "mapping_nodes",
})


def _normalize_v3(value: Any, path: tuple[str, ...] = ()) -> Any:
    """Path policy: only registered domain paths have semantic normalization.

    Native JSON is the default, including inside arbitrary vendor keys named
    tags/extends/evidence. No null dropping, NFC, inference, sorting or dedup.
    Top-level ID collections sort by ID; original ordering lives in position.
    Roles, rule references, keys, dialects and mapping trees remain ordered.
    """
    if isinstance(value, dict):
        return {key: _normalize_v3(item, (*path, key)) for key, item in value.items()}
    if isinstance(value, list):
        items = [_normalize_v3(item, (*path, "*")) for item in value]
        collection = path[0] if path else None
        # A top-level collection, or element_sha256(..., field=collection).
        if len(path) == 1 and collection in V3_COLLECTIONS:
            return sorted(items, key=lambda item: str(item["id"]))
        domain_element = len(path) == 3 and path[0] in V3_COLLECTIONS and path[1] == "*"
        if domain_element and path[2] == "evidence":
            return sorted(items, key=lambda item: str(item["id"]))
        if (domain_element and path[2] in {"tags", "native_presence", "map_presence"}) or path in {
            ("native_presence",), ("core_presence",),
        } or (len(path) == 3 and path[:2] == ("extension_v4", "tags")):
            # These paths contain platform metadata, never native Ossie arrays.
            unique = {jcs(item): item for item in items}
            return [unique[key] for key in sorted(unique)]
        return items
    # Only platform display labels/tags normalize Unicode. All SQL/native
    # concept names/readings/vendor text and their object keys stay verbatim.
    domain_element = len(path) >= 3 and path[0] in V3_COLLECTIONS and path[1] == "*"
    if isinstance(value, str) and (
        path[:2] == ("extension_v4", "display_names")
        or (len(path) >= 3 and path[:2] == ("extension_v4", "tags"))
    ):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, str) and domain_element and (
        path[2] == "tags" or (path[0] in {"object_types", "value_types", "rules"} and path[2] in {"name", "technical_name"})
    ):
        return unicodedata.normalize("NFC", value)
    return value


def canonical(
    value: Any, field: str | None = None, *, hash_algorithm: str = LEGACY_HASH_ALGORITHM,
) -> str:
    if hash_algorithm == LEGACY_HASH_ALGORITHM:
        return jcs(_normalize(value, field))
    if hash_algorithm == V3_HASH_ALGORITHM:
        return jcs(_normalize_v3(value, (field,) if field else ()))
    raise CanonicalizationError(f"未知 hash_algorithm：{hash_algorithm}")


def domain_sha256(
    value: Any, field: str | None = None, *, hash_algorithm: str = LEGACY_HASH_ALGORITHM,
) -> str:
    payload = canonical(value, field, hash_algorithm=hash_algorithm)
    # Domain separation for the new algorithm; never alter historical bytes.
    if hash_algorithm == V3_HASH_ALGORITHM:
        payload = hash_algorithm + "\n" + payload
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_sha256(snapshot: dict, *, hash_algorithm: str | None = None) -> str:
    """Select the stored algorithm, never infer it from a migrated snapshot."""
    stored = snapshot.get("hash_algorithm")
    if stored and hash_algorithm is not None and stored != hash_algorithm:
        raise CanonicalizationError("请求的 hash_algorithm 与快照记录不一致")
    algorithm = hash_algorithm or stored or LEGACY_HASH_ALGORITHM
    if snapshot.get("schema_version") == "3" and stored != V3_HASH_ALGORITHM:
        raise CanonicalizationError("schema_version 3 缺少匹配的 hash_algorithm")
    return domain_sha256(snapshot, hash_algorithm=algorithm)


def element_sha256(
    element: dict, *, hash_algorithm: str = LEGACY_HASH_ALGORITHM,
    collection: str | None = None,
) -> str:
    """v3 element hashing must supply its collection to select the path policy."""
    if hash_algorithm == V3_HASH_ALGORITHM:
        if collection not in V3_COLLECTIONS:
            raise CanonicalizationError("v3 元素哈希必须提供已登记的 collection")
        payload = _normalize_v3(element, (collection, "*"))
        return hashlib.sha256((hash_algorithm + "\n" + jcs(payload)).encode("utf-8")).hexdigest()
    return domain_sha256(element, hash_algorithm=hash_algorithm)


def verify_snapshot_sha256(snapshot: dict, expected: str) -> bool:
    """Verify stored bytes with their own algorithm, before v3 migration."""
    if str(snapshot.get("schema_version") or "1") == "1" and "workspace_id" in snapshot:
        from ontofoundry_api.domain.snapshot import normalized_snapshot_sha256

        return normalized_snapshot_sha256(snapshot) == expected
    return snapshot_sha256(snapshot) == expected
