"""Core-1 semantic normalization; independent of legacy snapshot algorithms.

Array strategies are explicit by domain field. Ordered key/path/condition arrays
remain ordered. No Unicode changes to SQL, user values, columns or source IDs.
Raw upload bytes and translation-report hashes do not use this module.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel

from ontofoundry_api.domain.canonical import CanonicalizationError, jcs
from ontofoundry_api.domain.core import COLLECTIONS, CoreDraft

SORTED = {
    **dict.fromkeys(COLLECTIONS, "id"),
    "evidence": "id",
    "sources": "id",
    "columns": "name",
}
SETS = frozenset({"tags", "synonyms"})
ORDERED = frozenset(
    {
        "derived_by",
        "conditions",
        "links",
        "values",
        "filters",
        "key_columns",
        "source_property_ids",
        "target_property_ids",
        "property_ids",
        "source_columns",
        "target_columns",
    }
)


def _normalize(value: Any, field: str | None = None) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(item, key) for key, item in value.items()}
    if not isinstance(value, list):
        return value
    items = [_normalize(item) for item in value]
    if field in SORTED:
        return sorted(items, key=lambda item: item[SORTED[field]])
    if field in SETS:
        unique = {jcs(item): item for item in items}
        return [unique[key] for key in sorted(unique)]
    if field in ORDERED:
        return items
    raise CanonicalizationError(f"未登记的 core-1 数组字段：{field!r}")


def canonical(value: CoreDraft | dict) -> str:
    draft = value if isinstance(value, CoreDraft) else CoreDraft.model_validate(value)
    return jcs(_normalize(draft.model_dump(mode="json")))


def draft_sha256(value: CoreDraft | dict) -> str:
    return hashlib.sha256(("ontofoundry-core-1\n" + canonical(value)).encode()).hexdigest()


def element_sha256(value: BaseModel | dict, collection: str) -> str:
    if collection not in COLLECTIONS:
        raise CanonicalizationError("core-1 元素必须指定已登记集合")
    # Parse via the authoritative union, including metric discriminators.
    draft = CoreDraft.model_validate(
        {
            "workspace_id": "00000000-0000-0000-0000-000000000000",
            collection: [
                value.model_dump(mode="json") if isinstance(value, BaseModel) else value
            ],
        }
    )
    item = getattr(draft, collection)[0].model_dump(mode="json")
    return hashlib.sha256(
        ("ontofoundry-core-1\n" + jcs(_normalize(item))).encode()
    ).hexdigest()
