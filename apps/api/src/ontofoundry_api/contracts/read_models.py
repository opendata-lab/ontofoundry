"""Interface read contracts, kept separate from the core semantic schema."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, TypeAdapter

from ontofoundry_api.domain.core import (
    Aggregation,
    BindingMode,
    ColumnReference,
    Condition,
    DataJoin,
    DerivedBranch,
    FieldBinding,
    MappingSource,
    Multiplicity,
    Strict,
    ValueKind,
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


class TableRowsRead(Strict):
    """First rows of one synced source table, read-only and bounded."""

    columns: list[str]
    items: list[dict[str, JsonValue]]
    limit: int = Field(ge=1, le=100)


OntologyKind = Literal[
    "object_type", "property", "link_type", "rule", "metric", "dataset", "value_type"
]


class OntologySearchRequest(Strict):
    query: str = Field(max_length=240)
    kinds: list[OntologyKind] | None = None
    expand: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class SearchRetrievalRead(Strict):
    keyword: bool
    vector: bool


class SearchViaRead(Strict):
    id: UUID
    relation: Literal[
        "metric_dataset_bound_type",
        "metric_numerator",
        "metric_denominator",
        "object_title_property",
        "object_link_type",
        "property_owner",
        "link_source_type",
        "link_target_type",
    ]


class SearchTextMatchRead(Strict):
    by: Literal["name_in_query", "query_in_name", "description", "vector"]
    text: str


class SearchExpansionMatchRead(Strict):
    by: Literal["expansion"]
    via: SearchViaRead


class SearchReferenceRead(Strict):
    id: UUID
    name: str
    display_name: str | None = None


class SearchDatasetRead(Strict):
    id: UUID
    name: str


class SearchMetricDefinitionRead(Strict):
    kind: Literal["simple", "ratio", "expression"]
    aggregation: Aggregation | None = None
    measure: ColumnReference | None = None
    time_field: ColumnReference | None = None
    filters: list[Condition] | None = None
    expression: str | None = None
    numerator_id: UUID | None = None
    denominator_id: UUID | None = None


class SearchItemRead(Strict):
    id: UUID
    kind: OntologyKind
    display_name: str | None
    name: str
    summary: str
    matched_synonyms: list[str]
    match: Annotated[
        SearchTextMatchRead | SearchExpansionMatchRead, Field(discriminator="by")
    ]
    owner_id: UUID | None = None
    owner_kind: str | None = None
    synonyms: list[str] | None = None
    title_property_id: UUID | None = None
    owner: SearchReferenceRead | None = None
    value_kind: ValueKind | None = None
    value_type_id: UUID | None = None
    identifier: bool | None = None
    source: SearchReferenceRead | None = None
    target: SearchReferenceRead | None = None
    source_type_id: UUID | None = None
    target_type_id: UUID | None = None
    source_role_name: str | None = None
    target_role_name: str | None = None
    multiplicity: Multiplicity | None = None
    definition: SearchMetricDefinitionRead | None = None
    dataset: SearchDatasetRead | None = None


class OntologySearchRead(Strict):
    workspace_id: UUID
    version_id: UUID | None
    items: list[SearchItemRead]
    total: int = Field(ge=0)
    next_cursor: str | None
    retrieval: SearchRetrievalRead
    unmatched_terms: list[str]


def read_models_schema():
    schema = TypeAdapter(
        MembershipRead
        | EffectiveLinkRead
        | EffectiveBindingRead
        | ElementSaveImpact
        | TableRowsRead
        | OntologySearchRead
    ).json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "ontofoundry.api-read.v1.schema.json"
    schema["title"] = "OntoFoundry interface read models v1"
    return schema
