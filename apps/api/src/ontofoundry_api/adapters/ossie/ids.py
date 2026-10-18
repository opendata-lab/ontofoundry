"""Stable source identities and scoped names from the core-1 adapter contract."""

import re
from uuid import UUID, uuid5


def source_id(workspace_id: UUID, key: str) -> UUID:
    return uuid5(workspace_id, "ossie:" + key)


def technical_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", name)[:220] or "element"
    if base[0].isdigit():
        base = "_" + base
    result = base
    suffix = 2
    while result.casefold() in used:
        result = f"{base}_{suffix}"
        suffix += 1
    used.add(result.casefold())
    return result


def display_name(name: str, used: set[str]) -> str:
    base = name.strip()[:220] or "未命名"
    result = base
    suffix = 2
    while result.casefold() in used:
        result = f"{base}（{suffix}）"
        suffix += 1
    used.add(result.casefold())
    return result
