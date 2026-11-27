"""Guard standalone DataAgent skill scripts against platform kind/collection drift.

Skill scripts run in isolation without importing `ontofoundry_api`, so they
carry their own kind/collection registries (`runpaths.py`, `show_element.py`,
`show_example.py`, `generate_output_schemas.py`). These tests verify every
registry against the platform's JSON schemas so adding a new element kind
fails immediately and points at every script to update.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REPO = BASE.parents[1]
CONTRACTS = REPO / "apps/api/src/ontofoundry_api/contracts"

sys.path.insert(0, str(BASE))
import generate_output_schemas  # noqa: E402
import runpaths  # noqa: E402
import show_element  # noqa: E402
import show_example  # noqa: E402


def _core_collections() -> set[str]:
    schema = json.loads((CONTRACTS / "ontofoundry.core-1.schema.json").read_text(encoding="utf-8"))
    return set(schema["properties"]) - {"schema_version", "workspace_id"}


def _proposal_target_kinds() -> set[str]:
    schema = json.loads((CONTRACTS / "ontofoundry.proposals.v1.schema.json").read_text(encoding="utf-8"))
    return set(schema["$defs"]["item"]["properties"]["target_kind"]["enum"])


def _schema_reference_like_fields() -> set[str]:
    schema = json.loads((CONTRACTS / "ontofoundry.core-1.schema.json").read_text(encoding="utf-8"))
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                for key in props:
                    if key == "extends" or key.endswith("_id") or key.endswith("_ids"):
                        found.add(key)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return found


def test_runpaths_collections_and_target_kinds_match_platform_schemas():
    core_collections = _core_collections()
    proposal_kinds = _proposal_target_kinds()

    assert set(runpaths.COLLECTIONS.values()) == core_collections
    assert runpaths.INSTANCE_KINDS == frozenset({"material_object", "material_link"})
    assert set(runpaths.COLLECTIONS) | set(runpaths.INSTANCE_KINDS) == proposal_kinds
    assert not (set(runpaths.COLLECTIONS) & set(runpaths.INSTANCE_KINDS))
    assert set(runpaths.TARGET_KINDS) == proposal_kinds


def test_generate_output_schemas_targets_partition_proposal_kinds():
    proposal_kinds = _proposal_target_kinds()
    discovery = generate_output_schemas.TARGETS["ontology-discovery"]
    extraction = generate_output_schemas.TARGETS["entity-extraction"]

    # ontology-discovery covers all core definition kinds; entity-extraction
    # covers only document instance kinds.
    assert discovery == set(runpaths.COLLECTIONS)
    assert extraction == set(runpaths.INSTANCE_KINDS)
    assert not (discovery & extraction)
    assert discovery | extraction == proposal_kinds


def test_show_example_parts_by_kind_covers_all_proposal_kinds():
    proposal_kinds = _proposal_target_kinds()
    assert set(show_example.PARTS_BY_KIND) == proposal_kinds
    for part in set(show_example.PARTS_BY_KIND.values()):
        assert (show_example.KIT / f"{part}.json").is_file()


def test_show_element_reference_fields_cover_core_schema_element_refs():
    schema_ref_fields = _schema_reference_like_fields()
    # Non-core-element identifiers in core-1:
    # - workspace_id: draft root workspace id
    # - connection_id: external datasource connection id
    # - material_id: uploaded material id inside evidence
    # - source_id / membership_source_id: local mapping source aliases within DataMapping
    non_element_refs = frozenset(
        {
            "workspace_id",
            "connection_id",
            "material_id",
            "source_id",
            "membership_source_id",
        }
    )
    assert non_element_refs <= schema_ref_fields
    assert not (show_element.REFERENCE_FIELDS & non_element_refs)
    assert show_element.REFERENCE_FIELDS == schema_ref_fields - non_element_refs
