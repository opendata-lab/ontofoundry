"""Guard every element-kind and collection list in the backend against drift.

When a new core element kind is registered in `domain.core.COLLECTIONS` /
`domain.models.ElementKind`, these tests must fail and point at every list
that intentionally includes or excludes a subset of kinds so each module makes
an explicit decision.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path
from typing import get_args
from uuid import uuid4

from ontofoundry_api.adapters.native.legacy import LEGACY_NAMED_COLLECTIONS
from ontofoundry_api.api import mcp as mcp_api
from ontofoundry_api.api import ontology as ontology_api
from ontofoundry_api.contracts.materials import MaterialUsage
from ontofoundry_api.contracts.proposal_diagnostics import KIT_PARTS
from ontofoundry_api.contracts.proposals import NAMED_PROPOSAL_KINDS
from ontofoundry_api.contracts.read_models import CatalogItemRead, OntologyKind
from ontofoundry_api.contracts.session_writes import ElementSavePreview
from ontofoundry_api.domain import core, core_canonical, graph, models
from ontofoundry_api.domain.models import (
    COLLECTIONS,
    ELEMENT_MODELS,
    INSTANCE_COLLECTIONS,
    PROPOSAL_COLLECTIONS,
    ElementKind,
)
from ontofoundry_api.services import (
    catalog_reads,
    element_diff,
    element_save,
    import_matching,
    material_usage,
    mcp_ontology,
    modeling_input,
    ontology_query,
    ontology_search,
    proposal_alignment,
    proposal_revision,
    proposals,
    public_projection,
    version_diff,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRACT_KIT_DIR = REPO_ROOT / "integrations/dataagent/shared/references/extract-kit"

ALL_KINDS = frozenset(kind.value for kind in ElementKind)
CORE_KINDS = frozenset(kind.value for kind in COLLECTIONS)
INSTANCE_KINDS = frozenset(kind.value for kind in INSTANCE_COLLECTIONS)
CORE_COLLECTIONS = frozenset(core.COLLECTIONS)
ALL_COLLECTIONS = frozenset(PROPOSAL_COLLECTIONS.values())


def _assert_coverage(
    actual: set[str] | frozenset[str],
    registered: frozenset[str],
    excluded: frozenset[str],
) -> None:
    assert excluded <= registered, f"Unknown excluded entries: {sorted(excluded - registered)}"
    assert not (actual & excluded), (
        f"Entries listed as both covered and excluded: {sorted(actual & excluded)}"
    )
    assert set(actual) == set(registered - excluded), (
        f"Coverage mismatch: missing={sorted((registered - excluded) - set(actual))}, "
        f"extra={sorted(set(actual) - (registered - excluded))}"
    )


def test_core_and_model_registries_stay_in_sync():
    draft_list_fields = {
        name
        for name in core.CoreDraft.model_fields
        if name not in {"schema_version", "workspace_id"}
    }
    assert CORE_COLLECTIONS == draft_list_fields
    assert tuple(COLLECTIONS.values()) == core.COLLECTIONS
    assert CORE_KINDS | INSTANCE_KINDS == ALL_KINDS
    assert not (CORE_KINDS & INSTANCE_KINDS)
    assert set(PROPOSAL_COLLECTIONS) == set(ElementKind)
    assert set(ELEMENT_MODELS) == set(ElementKind)


def test_graph_index_preserves_iteration_order_without_top_level_import_cycle():
    source = Path(graph.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == "ontofoundry_api.domain.models"
        for node in top_level_imports
    ), "domain.graph must not import domain.models at module top level (models imports graph)"

    assert len(graph.INDEX_KIND_ORDER) == len(CORE_KINDS)
    _assert_coverage(set(graph.INDEX_KIND_ORDER), CORE_KINDS, frozenset())

    # Preserve exact `main` ordering: link_type is indexed before property when both share a name.
    obj_a_id, obj_b_id = uuid4(), uuid4()
    draft = core.CoreDraft(
        workspace_id=uuid4(),
        object_types=[
            core.ObjectType(id=obj_a_id, name="alpha"),
            core.ObjectType(id=obj_b_id, name="beta"),
        ],
        properties=[
            core.Property(
                id=uuid4(),
                owner_type_id=obj_a_id,
                name="shared",
                value_kind="string",
            )
        ],
        link_types=[
            core.LinkType(
                id=uuid4(),
                name="shared",
                source_type_id=obj_b_id,
                target_type_id=obj_a_id,
                multiplicity="many_to_one",
            )
        ],
    )
    index = graph.DraftIndex(draft)
    assert [kind for kind, _ in index.names["shared"]] == ["link_type", "property"]


def test_core_canonical_covers_all_core_collections():
    for collection in core.COLLECTIONS:
        assert core_canonical.SORTED.get(collection) == "id"


def test_catalog_reads_ontology_query_and_http_kind_filters():
    assert catalog_reads.COLLECTIONS is models.COLLECTIONS
    assert catalog_reads.RESOURCE_KINDS is ontology_query.RESOURCE_KINDS

    # Only top-level browsable resource kinds appear in catalog/type list endpoints;
    # properties/rules/mappings belong to owners, value_types use their own catalog,
    # and instances live in the instance store.
    _assert_coverage(
        set(catalog_reads.RESOURCE_KINDS),
        ALL_KINDS,
        frozenset({"property", "rule", "mapping", "value_type", *INSTANCE_KINDS}),
    )
    assert set(get_args(CatalogItemRead.model_fields["kind"].annotation)) == set(
        catalog_reads.RESOURCE_KINDS
    )

    # HTTP GET /types and GET /catalog derive their Query pattern from RESOURCE_KIND_PATTERN.
    expected_pattern = ontology_query.RESOURCE_KIND_PATTERN
    for endpoint in (ontology_api.types, ontology_api.catalog):
        param = inspect.signature(endpoint).parameters["kind"].default
        pattern = next(
            (meta.pattern for meta in param.metadata if hasattr(meta, "pattern")),
            None,
        )
        assert pattern == expected_pattern
    regex = re.compile(expected_pattern)
    for kind in ALL_KINDS:
        assert bool(regex.fullmatch(kind)) is (kind in ontology_query.RESOURCE_KINDS)

    # Catalog summary counts expose the top-level tabs (including value_types);
    # nested properties, rules and mappings are counted inside their owners.
    _assert_coverage(
        set(catalog_reads.CATALOG_COUNT_COLLECTIONS),
        CORE_COLLECTIONS,
        frozenset({"properties", "rules", "mappings"}),
    )

    # Version summary counts include every core collection except value_types.
    counted = set(ontology_query.VERSION_SUMMARY_COUNT_FIELDS.values()) | set(
        ontology_query.VERSION_SUMMARY_MAPPING_COUNT_FIELDS.values()
    )
    _assert_coverage(counted, CORE_COLLECTIONS, frozenset({"value_types"}))


def test_material_usage_and_contract_coverage():
    usage_count_fields = {
        name
        for name, field in MaterialUsage.model_fields.items()
        if field.annotation is int
    }
    assert set(material_usage.COLLECTIONS) == usage_count_fields

    # MaterialUsage counts both core definitions and document instances that cite
    # materials. Datasets and mappings have no `evidence` field; value_types are
    # not yet broken out in MaterialUsage v1.
    _assert_coverage(
        set(material_usage.COLLECTIONS.values()),
        ALL_KINDS,
        frozenset({"dataset", "mapping", "value_type"}),
    )
    for collection, kind in material_usage.COLLECTIONS.items():
        assert PROPOSAL_COLLECTIONS[ElementKind(kind)] == collection


def test_import_matching_natural_key_order():
    # `elements()` iterates core COLLECTIONS only (never instance kinds).
    assert len(import_matching.NATURAL_KEY_ORDER) == len(CORE_KINDS)
    _assert_coverage(set(import_matching.NATURAL_KEY_ORDER), CORE_KINDS, frozenset())
    assert import_matching.NATURAL_KEY_ORDER.index("object_type") < import_matching.NATURAL_KEY_ORDER.index("property")
    assert import_matching.NATURAL_KEY_ORDER.index("value_type") < import_matching.NATURAL_KEY_ORDER.index("property")
    assert import_matching.NATURAL_KEY_ORDER.index("value_type") < import_matching.NATURAL_KEY_ORDER.index("rule")
    assert import_matching.NATURAL_KEY_ORDER.index("link_type") < import_matching.NATURAL_KEY_ORDER.index("rule")

    # Behaviour guard: a same-name link_type with a different UUID must match before
    # its owned rule so the rule's natural key resolves to the existing rule UUID.
    ws_id = uuid4()
    base_src, base_tgt, base_link, base_rule = uuid4(), uuid4(), uuid4(), uuid4()
    inc_src, inc_tgt, inc_link, inc_rule = uuid4(), uuid4(), uuid4(), uuid4()
    base = core.CoreDraft(
        workspace_id=ws_id,
        object_types=[
            core.ObjectType(id=base_src, name="order"),
            core.ObjectType(id=base_tgt, name="customer"),
        ],
        link_types=[
            core.LinkType(
                id=base_link,
                name="belongs_to",
                source_type_id=base_src,
                target_type_id=base_tgt,
                multiplicity="many_to_one",
            )
        ],
        rules=[
            core.Rule(
                id=base_rule,
                name="must_match",
                owner_kind="link_type",
                owner_id=base_link,
                rule_kind="constraint",
                expression="true",
            )
        ],
    )
    incoming = core.CoreDraft(
        workspace_id=ws_id,
        object_types=[
            core.ObjectType(id=inc_src, name="order"),
            core.ObjectType(id=inc_tgt, name="customer"),
        ],
        link_types=[
            core.LinkType(
                id=inc_link,
                name="belongs_to",
                source_type_id=inc_src,
                target_type_id=inc_tgt,
                multiplicity="many_to_one",
            )
        ],
        rules=[
            core.Rule(
                id=inc_rule,
                name="must_match",
                owner_kind="link_type",
                owner_id=inc_link,
                rule_kind="constraint",
                expression="true",
            )
        ],
    )
    matched = import_matching.match_import(base, incoming, native=False)
    assert matched[str(inc_link)] == str(base_link)
    assert matched[str(inc_rule)] == str(base_rule)


def test_import_matching_rename_group_kinds():
    # Import rename-exchange grouping tracks named definitions currently checked
    # during pruning; mappings and instances have no `name`, and value_type is
    # currently excluded from rename-exchange pruning.
    _assert_coverage(
        import_matching.RENAME_GROUP_KINDS,
        ALL_KINDS,
        frozenset({"mapping", "value_type", *INSTANCE_KINDS}),
    )


def test_proposals_and_diagnostics_lists():
    # Proposal diagnostics map every registered ElementKind to a fixed extract-kit part
    # whose example JSON actually contains a `create` item for that kind.
    _assert_coverage(
        set(KIT_PARTS),
        ALL_KINDS,
        frozenset({"action"}),  # added in PR C (skills)
    )
    for kind, part in KIT_PARTS.items():
        items = json.loads((EXTRACT_KIT_DIR / f"{part}.json").read_text(encoding="utf-8"))
        create_kinds = {item["target_kind"] for item in items if item.get("operation") == "create"}
        assert kind in create_kinds, f"KIT_PARTS[{kind!r}] -> {part}.json has no create example for {kind!r}"

    # Proposal name-exchange grouping covers all named core kinds; mappings and
    # document instances have no unique `name` field.
    _assert_coverage(
        NAMED_PROPOSAL_KINDS,
        ALL_KINDS,
        frozenset({"mapping", *INSTANCE_KINDS}),
    )

    # Proposal KIND_LABELS currently omits value_type (preserved for zero behavior change).
    _assert_coverage(
        set(proposals.KIND_LABELS),
        ALL_KINDS,
        frozenset({"value_type"}),
    )

    # Similar-definition hints run only on named semantic concepts where near-duplicates
    # are common; rules, datasets, mappings, value_types and instances are excluded.
    _assert_coverage(
        proposal_alignment.SIMILAR_KINDS,
        ALL_KINDS,
        frozenset({"rule", "dataset", "mapping", "value_type", *INSTANCE_KINDS}),
    )

    # Proposal revision validates against ELEMENT_MODELS (covers all ElementKind values).
    assert proposal_revision.ELEMENT_MODELS is models.ELEMENT_MODELS


def test_element_diff_and_version_diff_lists():
    # Diff `owner_label` resolves single-owner elements; top-level kinds and
    # two-ended link/material_link elements have no single owner label.
    _assert_coverage(
        element_diff.OWNER_LABEL_KINDS,
        ALL_KINDS,
        frozenset({"object_type", "link_type", "metric", "dataset", "value_type", "material_link"}),
    )

    # Version diff `impacts` reports object-type reference impacts for mappings
    # and link_types only; other collections are compared via `changes` only.
    _assert_coverage(
        set(version_diff.IMPACT_COLLECTIONS),
        CORE_COLLECTIONS,
        frozenset({"object_types", "properties", "rules", "metrics", "datasets", "value_types"}),
    )


def test_element_save_scope_and_contract_kinds():
    save_kinds = frozenset(get_args(ElementSavePreview.model_fields["target_kind"].annotation))
    # Direct human save endpoints accept aggregate roots; properties and rules
    # are saved inside their owner's aggregate, actions are edited only through
    # proposals in v1, and instances use the instance store.
    _assert_coverage(
        save_kinds,
        ALL_KINDS,
        frozenset({"property", "rule", "action", *INSTANCE_KINDS}),
    )

    draft = core.empty_draft(uuid4()).model_dump(mode="json")
    for kind in save_kinds:
        scope = element_save.element_scope(draft, kind, str(uuid4()))
        assert set(scope) == CORE_COLLECTIONS


def test_search_ontology_lists_and_mcp_description():
    ontology_kinds = frozenset(get_args(OntologyKind))
    # Search and MCP get_ontology expose all core semantic/dataset definitions;
    # mappings are internal physical bindings and instances use object tools.
    _assert_coverage(
        ontology_kinds,
        ALL_KINDS,
        frozenset({"mapping", *INSTANCE_KINDS}),
    )
    # Search candidate recall covers the same set independently.
    _assert_coverage(
        set(ontology_search.SEARCHABLE_KINDS),
        ALL_KINDS,
        frozenset({"mapping", *INSTANCE_KINDS}),
    )
    assert mcp_ontology.Kind is OntologyKind

    # MCP search_ontology tool description enumerates the exact OntologyKind list.
    search_description = mcp_api.TOOLS["search_ontology"][1]
    assert "、".join(get_args(OntologyKind)) in search_description


def test_mcp_get_ontology_routing_lists():
    # Resource-projected kinds go through `resource_items` on by-ID reads and
    # lightweight summaries on list reads; nested/direct definitions, mappings
    # and instances are excluded.
    _assert_coverage(
        set(mcp_ontology.LIST_RESOURCE_KINDS),
        ALL_KINDS,
        frozenset({"property", "rule", "value_type", "mapping", *INSTANCE_KINDS}),
    )

    # Direct definition kinds are read straight from the snapshot on both list
    # and by-ID reads; resource-projected kinds, mappings and instances are excluded.
    _assert_coverage(
        set(mcp_ontology.DIRECT_ELEMENT_KINDS),
        ALL_KINDS,
        frozenset({"object_type", "link_type", "metric", "dataset", "action", "mapping", *INSTANCE_KINDS}),
    )

    listed = set(mcp_ontology.LIST_RESOURCE_KINDS)
    direct = set(mcp_ontology.DIRECT_ELEMENT_KINDS)
    assert not (listed & direct)
    assert listed | direct == set(get_args(OntologyKind))

    # Physical SQL projection applies only to mapped ontology concepts (objects,
    # links, metrics); datasets already carry physical metadata directly, and
    # actions are declarative definitions without SQL bindings.
    _assert_coverage(
        mcp_ontology.PHYSICAL_PROJECTION_KINDS,
        CORE_KINDS,
        frozenset({"property", "rule", "dataset", "mapping", "value_type", "action"}),
    )


def test_public_projection_modeling_input_and_legacy_lists():
    # Datasets and mappings have no `evidence` field; value_types are currently
    # excluded from authorized_snapshot evidence stripping.
    _assert_coverage(
        set(public_projection.EVIDENCE_CLEARED_COLLECTIONS),
        CORE_COLLECTIONS,
        frozenset({"datasets", "mappings", "value_types"}),
    )

    # `draft_empty` checks top-level collections only; properties, rules and
    # mappings cannot exist without an owner in one of these collections.
    _assert_coverage(
        set(modeling_input.DRAFT_EMPTY_COLLECTIONS),
        CORE_COLLECTIONS,
        frozenset({"properties", "rules", "mappings"}),
    )

    # Pre-core-1 legacy files only ever carried `technical_name` on these five
    # collections; newer collections never used the legacy naming format.
    _assert_coverage(
        set(LEGACY_NAMED_COLLECTIONS),
        CORE_COLLECTIONS,
        frozenset({"datasets", "mappings", "value_types", "actions"}),
    )
