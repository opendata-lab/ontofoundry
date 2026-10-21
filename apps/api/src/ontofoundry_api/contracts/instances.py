"""Instance store contracts, separate from core-1 ontology definitions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from ontofoundry_api.domain.core import MaterialLink, MaterialObject, Strict


class InstanceBaselineItem(Strict):
    target_kind: Literal["material_object", "material_link"]
    target_id: UUID
    revision: int = Field(ge=1)
    state: Literal["staged", "active", "deleted"]
    session_id: UUID | None
    element: MaterialObject | MaterialLink
    hash: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def matching_target(self):
        expected = MaterialObject if self.target_kind == "material_object" else MaterialLink
        if not isinstance(self.element, expected) or self.element.id != self.target_id:
            raise ValueError("实例基线目标、种类与内容不一致")
        return self


class InstanceBaseline(Strict):
    change_sequence: int = Field(ge=0)
    items: list[InstanceBaselineItem]


class InstanceHistorySnapshot(Strict):
    element: MaterialObject | MaterialLink
    state: Literal["staged", "active", "deleted"]
    revision: int = Field(ge=1)
    session_id: UUID | None


class InstanceHistoryRead(Strict):
    owner_kind: Literal["instance", "link"]
    owner_id: UUID
    revision: int = Field(ge=1)
    operation: str
    before: InstanceHistorySnapshot | None
    after: InstanceHistorySnapshot | None
    proposal_item_id: UUID | None
    actor: str
    at: datetime


class AbandonSessionRead(Strict):
    session_id: UUID
    abandoned_at: datetime
    abandoned_by: str


class AffectedInstanceRead(Strict):
    target_kind: Literal["material_object", "material_link"]
    target_id: UUID
    revision: int = Field(ge=1)
    reason: str


class InstancePublishImpact(Strict):
    instance_change_sequence: int = Field(ge=0)
    affected_instances: list[AffectedInstanceRead]


def instances_schema():
    schema = TypeAdapter(
        InstanceBaseline | InstanceHistoryRead | AbandonSessionRead | InstancePublishImpact
    ).json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "ontofoundry.instances.v1.schema.json"
    schema["title"] = "OntoFoundry instance store v1"
    return schema
