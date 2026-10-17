"""Interface read contracts, kept separate from the core semantic schema."""

from uuid import UUID

from pydantic import Field, TypeAdapter

from ontofoundry_api.domain.core import (
    BindingMode,
    DataJoin,
    DerivedBranch,
    FieldBinding,
    MappingSource,
    Strict,
)


class MembershipRead(Strict):
    type_id: UUID
    mapping_id: UUID
    binding_mode: BindingMode
    membership_source_id: str | None
    derived_by: list[DerivedBranch]


class EffectiveLinkRead(Strict):
    link_type_id: UUID
    source_type_id: UUID
    target_type_id: UUID
    data_join: DataJoin | None


class EffectiveBindingRead(Strict):
    type_id: UUID
    sources: list[MappingSource]
    fields: dict[str, FieldBinding]
    memberships: list[MembershipRead]
    links: list[EffectiveLinkRead] = Field(default_factory=list)


class AffectedItem(Strict):
    target_kind: str
    target_id: str
    expected_target_hash: str


class AffectedItemImpact(AffectedItem):
    reason: str


class ElementSaveImpact(Strict):
    current_version_id: str | None
    session_revision: int | None
    affected_items: list[AffectedItemImpact]


def read_models_schema():
    schema = TypeAdapter(
        MembershipRead | EffectiveLinkRead | EffectiveBindingRead | ElementSaveImpact
    ).json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "ontofoundry.api-read.v1.schema.json"
    schema["title"] = "OntoFoundry interface read models v1"
    return schema
