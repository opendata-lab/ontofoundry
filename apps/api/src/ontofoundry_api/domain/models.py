"""Public core-1 runtime models. No historical format conversions."""

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from ontofoundry_api.domain.core import *  # noqa: F403
from ontofoundry_api.domain.core import (
    CoreDraft,
    DataMapping,
    Dataset,
    ExpressionMetric,
    LinkType,
    MaterialLink,
    MaterialObject,
    ObjectType,
    Property,
    RatioMetric,
    Rule,
    SimpleMetric,
    Strict,
    _display_name,
)
from ontofoundry_api.domain.graph import DraftIndex


class ElementKind(StrEnum):
    OBJECT_TYPE = "object_type"
    PROPERTY = "property"
    LINK_TYPE = "link_type"
    RULE = "rule"
    METRIC = "metric"
    DATASET = "dataset"
    MAPPING = "mapping"
    MATERIAL_OBJECT = "material_object"
    MATERIAL_LINK = "material_link"


COLLECTIONS = dict(
    zip(
        ElementKind,
        (
            "object_types",
            "properties",
            "link_types",
            "rules",
            "metrics",
            "datasets",
            "mappings",
            "material_objects",
            "material_links",
        ),
        strict=True,
    )
)
ELEMENT_MODELS = dict(
    zip(
        ElementKind,
        (
            ObjectType,
            Property,
            LinkType,
            Rule,
            SimpleMetric | RatioMetric | ExpressionMetric,
            Dataset,
            DataMapping,
            MaterialObject,
            MaterialLink,
        ),
        strict=True,
    )
)


class OntologyDraft(CoreDraft):
    @model_validator(mode="after")
    def graph_valid(self):
        from ontofoundry_api.domain.validation import validate_core_graph

        validate_core_graph(self)
        return self

    def type_by_id(self):
        return DraftIndex(self).objects

    def properties_of(self, type_id):
        return [p for p in self.properties if p.owner_type_id == type_id]

    def effective_properties(self, type_id):
        return DraftIndex(self).effective_properties(type_id)

    def rules_of(self, owner_id, kind=None):
        return [
            r
            for r in self.rules
            if r.owner_id == owner_id and (kind is None or r.rule_kind == kind)
        ]

    def ancestors(self, type_id):
        index = DraftIndex(self)
        return [index.objects[i] for i in index.ancestors(type_id)]

    def parent_ids(self, item):
        return [item.extends] if item.extends is not None else []

    def descendants(self, type_id):
        return {
            o.id for o in self.object_types if type_id in DraftIndex(self).lineage(o.id)
        }

    def element_kind_of(self):
        return {
            e.id: kind
            for kind, collection in COLLECTIONS.items()
            for e in getattr(self, collection)
        }


class WorkspaceCreate(Strict):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9-]*$")
    description: str = Field(default="", max_length=1200)
    _normalize_name = field_validator("name")(_display_name)
