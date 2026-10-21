"""Reviewed source and directed round-trip expectations, keyed by exact fixture paths."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImportCase:
    source: str
    counts: dict[str, int]
    rules: frozenset[str]


OSSIE_IMPORT_CASES = (
    ImportCase(
        "ossie_synthetic/storybook-lending.ossie.json",
        {"object_types": 6, "properties": 2, "link_types": 3, "datasets": 0, "metrics": 0},
        frozenset({"RT-27", "RT-28"}),
    ),
    ImportCase(
        "ossie_synthetic/library-lending.ossie.json",
        {
            "object_types": 20,
            "properties": 33,
            "link_types": 27,
            "datasets": 8,
            "metrics": 7,
        },
        frozenset({"RT-43", "RT-56", "RT-69"}),
    ),
    ImportCase(
        "core1_ossie/03-nary-source.ossie.json",
        {"object_types": 3, "properties": 5, "link_types": 2},
        frozenset({"RT-27", "RT-28"}),
    ),
    ImportCase(
        "core1_ossie/06-inheritance-source.ossie.json",
        {"object_types": 2, "properties": 1, "link_types": 1},
        frozenset({"RT-67"}),
    ),
    ImportCase(
        "core1_ossie/07-document-source.ossie.json",
        {"object_types": 1, "properties": 1},
        frozenset({"RT-26"}),
    ),
)


@dataclass(frozen=True)
class RoundTripCase:
    source: str
    dropped_mapping_owners: frozenset[str]
    field_aliases: dict[str, dict[str, str]]
    allowed_reexport_differences: dict[str, str]


SYNTHETIC_ROUNDTRIPS = (
    RoundTripCase("ossie_synthetic/storybook-lending.ossie.json", frozenset(), {}, {}),
    RoundTripCase(
        "ossie_synthetic/library-lending.ossie.json",
        frozenset(
            {
                "fable_volume",
                "fable_catalog",
                "fable_curator",
                "fable_reading_room",
                "fable_aisle",
                "fable_loan_policy",
                "fable_shelf",
                "fable_loan_ticket",
            }
        ),
        {
            "fable_inventory_snapshot": {
                "folio_key": "raw_folio_code",
                "folio_title": "raw_folio_title",
            }
        },
        {
            "/ontology_mappings/0/semantic_model/datasets/3/fields/4/name": "RT-40",
            "/ontology_mappings/0/semantic_model/datasets/3/fields/4/ai_context": "RT-46",
            "/ontology_mappings/0/semantic_model/datasets/3/fields/5/name": "RT-40",
            # Export now derives datatype from the property type (DS-09).
            "/ontology_mappings/0/semantic_model/datasets/3/fields/4/datatype": "DS-09",
            "/ontology_mappings/0/semantic_model/datasets/3/fields/5/datatype": "DS-09",
            "/ontology_mappings/0/semantic_model/metrics/0/expression/dialects/0/expression": "RT-47",
            "/ontology_mappings/0/semantic_model/metrics/1/expression/dialects/0/expression": "RT-47",
        },
    ),
)
