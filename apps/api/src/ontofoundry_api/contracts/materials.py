"""Derived material usage for workspace source management."""

from datetime import datetime
from typing import Literal

from ontofoundry_api.domain.core import Strict


class MaterialUsage(Strict):
    object_types: int = 0
    link_types: int = 0
    properties: int = 0
    rules: int = 0
    metrics: int = 0
    material_objects: int = 0
    material_links: int = 0
    references: list[str]
    can_delete: bool


class ManagedMaterial(Strict):
    id: str
    name: str
    origin: Literal["upload", "table_receipt", "conversation_request"]
    sha256: str
    byte_size: int
    chunk_count: int
    created_at: datetime
    archived_at: datetime | None
    usage: MaterialUsage


class MaterialOverview(Strict):
    items: list[ManagedMaterial]
