"""P0: the frozen shape, pure migration and versioned hash boundary."""
import json
import runpy
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid5

import pytest
from pydantic import ValidationError
from test_ossie_import import mapped_draft
from test_t1_v2_model import action_draft, v1_demo

from ontofoundry_api.domain.canonical import (
    LEGACY_HASH_ALGORITHM,
    V3_HASH_ALGORITHM,
    CanonicalizationError,
    canonical,
    element_sha256,
    snapshot_sha256,
    verify_snapshot_sha256,
)
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.models_v3 import LinkTypeV3, RoleRef, SemanticModel
from ontofoundry_api.domain.snapshot import (
    as_v3_dict,
    draft_sha256,
    normalize_v2_to_v3,
    normalized_snapshot_sha256,
    read_snapshot,
    read_snapshot_json,
)
from ontofoundry_api.ossie import coverage
from ontofoundry_api.ossie.importer import OssieImportError, parse_ossie

WORKSPACE = UUID("11111111-1111-4111-8111-111111111111")
ROOT = Path(__file__).resolve().parents[3]


def uid(name):
    return str(uuid5(WORKSPACE, name))


def ref(kind, name):
    return {"kind": kind, "ref": uid(name) if kind in {"object_type", "value_type"} else name}


def native_draft():
    """All new collections; optional text, composite keys, recursive mixed slots."""
    expression = {"dialects": [{"dialect": "ANSI_SQL", "expression": "  e\u0301 + 1  "},
                               {"dialect": "ANSI_SQL", "expression": "  e\u0301 + 1  "}]}
    return {
        "schema_version": "3", "hash_algorithm": V3_HASH_ALGORITHM,
        "workspace_id": str(WORKSPACE), "ossie_name": "", "ossie_description": "",
        "document_origin": "imported", "native_presence": ["version", "name", "description", "ai_context", "ontology", "ontology_mappings"],
        "ai_context": {"synonyms": ["x", "x"], "ontofoundry": {"tags": ["b", "a", "b"], "evidence": [None], "extends": [None], "null": None}},
        "ontology_requires": ["x" * 1000, "x" * 1000],
        "object_types": [{"id": uid("object"), "concept": "  e\u0301  ", "extends": [ref("any", "Any")], "identify_by": [],
                          "origin": "imported", "position": 0, "native_presence": ["concept", "type", "extends", "identify_by", "relationships"]}],
        "value_types": [{"id": uid("value"), "concept": "Code", "extends": [ref("builtin", "String"), ref("builtin", "String")],
                         "position": 1, "origin": "imported", "native_presence": ["concept", "type", "extends"]}],
        "link_types": [{"id": uid("link"), "name": "  nary  ", "technical_name": "nary", "owner_ref": ref("value_type", "value"),
                        "roles": [{"id": uid("role0"), "name": "", "concept": ref("object_type", "object"), "position": 0},
                                  {"id": uid("role1"), "concept": ref("builtin", "Integer"), "position": 1},
                                  {"id": uid("role2"), "concept": ref("any", "Any"), "position": 2}],
                        "verbalizes": ["{Code}   {  e\u0301  }", "{Code}   {  e\u0301  }"],
                        "requires": [uid("rule")], "position": 0}],
        "rules": [{"id": uid("rule"), "owner_kind": "link_type", "owner_id": uid("link"), "rule_kind": "constraint", "expression": "x" * 1000}],
        "semantic_models": [{"id": uid("model"), "map_name": "", "map_description": "", "name": "model", "description": "",
                             "map_presence": ["name", "description", "semantic_model", "concept_mappings"],
                             "native_presence": ["name", "description", "ai_context", "datasets", "relationships", "metrics", "custom_extensions"],
                             "ai_context": "  e\u0301  ", "position": 0, "custom_extensions": [{"vendor_name": "ONTOFOUNDRY", "data": '{ "existing": null }'}]}],
        "datasets": [{"id": uid("dataset"), "semantic_model_id": uid("model"), "name": "ds", "source": " SELECT * FROM table ",
                      "primary_key": ["a", "b", "a"], "unique_keys": [["b", "a"], ["b", "a"]], "description": "",
                      "ai_context": {"examples": ["e", "e"]}, "custom_extensions": [], "native_presence": ["name", "source", "primary_key", "unique_keys", "fields"], "position": 0}],
        "dataset_fields": [{"id": uid("field"), "dataset_id": uid("dataset"), "name": "a", "expression": expression,
                            "dimension": {}, "label": "", "description": "", "datatype": "Integer", "position": 0}],
        "dataset_relationships": [{"id": uid("dataset_join"), "semantic_model_id": uid("model"), "name": "self", "from": "ds", "to": "ds",
                                   "from_columns": ["a", "b"], "to_columns": ["b", "a"], "position": 0}],
        "metrics": [{"id": uid("metric"), "semantic_model_id": uid("model"), "name": "sum", "expression": expression,
                     "datatype": "Decimal", "ai_context": {"null": None}, "position": 0}],
        "concept_mappings": [{"id": uid("cm"), "semantic_model_id": uid("model"), "concept_id": ref("builtin", "String"), "position": 0}],
        "mapping_nodes": [
            {"id": uid("objectroot"), "concept_mapping_id": uid("cm"), "slot": "object_mappings", "kind": "object", "position": 0, "expression": "  ds.a  "},
            {"id": uid("referent"), "concept_mapping_id": uid("cm"), "parent_id": uid("objectroot"), "slot": "referent_mappings", "kind": "referent", "relationship": "key", "position": 0},
            {"id": uid("referent2"), "concept_mapping_id": uid("cm"), "parent_id": uid("referent"), "slot": "referent_mappings", "kind": "referent", "relationship": "key2", "position": 0, "expression": "x" * 1000},
            {"id": uid("linkroot"), "concept_mapping_id": uid("cm"), "slot": "link_mappings", "kind": "link", "position": 0},
            {"id": uid("linkobject"), "concept_mapping_id": uid("cm"), "parent_id": uid("linkroot"), "slot": "object_mapping", "kind": "object", "position": 0, "concept": ref("any", "Any")},
            {"id": uid("child"), "concept_mapping_id": uid("cm"), "parent_id": uid("linkroot"), "slot": "children", "kind": "link", "position": 0, "relationship": "child"},
            {"id": uid("childobject"), "concept_mapping_id": uid("cm"), "parent_id": uid("child"), "slot": "object_mapping", "kind": "object", "position": 0},
        ],
        "extension_v4": {"version": "4", "ids": {"/ontology/0": uid("object")}, "concept_context": {uid("object"): {"synonyms": ["中文"]}},
                         "export_edits": [{"path": "/ai_context/ontofoundry", "was_present": True, "original": {"null": None}, "written": {"version": "4"}}]},
    }


def test_full_v3_contract_preserves_native_text_and_presence_after_reload():
    data = native_draft()
    draft = OntologyDraft.model_validate(data)
    stored = draft.model_dump(mode="json")
    assert type(draft.link_types[0]) is LinkTypeV3
    assert draft.link_types[0].source_type_id is None
    assert draft.link_types[0].target_type_id is None
    assert draft.link_types[0].target_role_name is None
    assert stored["ai_context"] == data["ai_context"]
    assert stored["object_types"][0]["concept"] == data["object_types"][0]["concept"]
    assert stored["dataset_fields"][0]["expression"] == data["dataset_fields"][0]["expression"]
    assert stored["dataset_fields"][0]["dimension"] == {}
    assert stored["datasets"][0]["unique_keys"] == data["datasets"][0]["unique_keys"]
    assert "from_" not in stored["dataset_relationships"][0]
    assert stored["extension_v4"]["export_edits"][0]["original"] == {"null": None}
    assert as_v3_dict(stored) == stored
    assert OntologyDraft.model_validate(stored).model_dump(mode="json") == stored


def test_unary_and_binary_views_and_role_order():
    owner = ref("object_type", "object")
    unary = LinkTypeV3(id=uid("unary"), name="unary", owner_ref=owner)
    assert unary.source_type_id is None
    binary = LinkTypeV3(id=uid("binary"), name="binary", owner_ref=owner, roles=[RoleRef(id=uid("end"), name="target", concept=owner)])
    assert binary.source_type_id == UUID(uid("object"))
    assert binary.target_type_id == UUID(uid("object"))
    assert binary.target_role_name == "target"
    value_binary = binary.model_copy(update={"owner_ref": OntologyDraft.model_validate(native_draft()).link_types[0].owner_ref})
    assert value_binary.source_type_id is None


@pytest.mark.parametrize(("collection", "index", "field", "value", "message"), [
    ("mapping_nodes", 5, "slot", "referent_mappings", "slot"),
    ("mapping_nodes", 1, "relationship", None, "referent"),
    ("mapping_nodes", 1, "parent_id", uid("missing"), "父节点"),
    ("mapping_nodes", 5, "parent_id", uid("child"), "循环"),
    ("mapping_nodes", 6, "parent_id", uid("objectroot"), "object 子节点|slot"),
    ("mapping_nodes", 2, "position", -1, "greater"),
    ("link_types", 0, "owner_ref", ref("object_type", "missing"), "概念引用"),
    ("semantic_models", 0, "unexpected", True, "Extra"),
    ("dataset_fields", 0, "dataset_id", uid("missing"), "dataset_id"),
    ("dataset_fields", 0, "datatype", "Unknown", "Input"),
    ("dataset_relationships", 0, "from_columns", ["a"], "数量"),
    ("dataset_relationships", 0, "to", "missing", "端点"),
    ("concept_mappings", 0, "semantic_model_id", uid("missing"), "semantic_model_id"),
    ("rules", 0, "owner_id", uid("missing"), "归属"),
    ("object_types", 0, "origin", "imported", "position"),
])
def test_v3_invalid_graph_rejected(collection, index, field, value, message):
    data = native_draft()
    data[collection][index][field] = value
    if field == "origin":
        data[collection][index]["position"] = None
    with pytest.raises(ValidationError, match=message):
        OntologyDraft.model_validate(data)


@pytest.mark.parametrize("problem", ["missing_object", "duplicate_object", "duplicate_role", "unresolved_ref", "order", "inheritance"])
def test_v3_graph_constraints(problem):
    data = native_draft()
    if problem == "missing_object":
        data["mapping_nodes"].pop(6)
    elif problem == "duplicate_object":
        data["mapping_nodes"].append({**data["mapping_nodes"][4], "id": uid("extra"), "position": 1})
    elif problem == "duplicate_role":
        data["link_types"][0]["roles"][1]["id"] = uid("role0")
    elif problem == "unresolved_ref":
        data["link_types"][0]["roles"][0]["client_ref"] = "new"
    elif problem == "order":
        data["link_types"][0]["roles"].reverse()
    else:
        data["object_types"][0]["extends"] = [ref("object_type", "object")]
    with pytest.raises(ValidationError):
        OntologyDraft.model_validate(data)


def test_native_presence_and_nested_dimension_distinguish_absent_from_empty():
    a = native_draft()
    b = deepcopy(a)
    b["object_types"][0]["native_presence"].remove("identify_by")
    assert snapshot_sha256(as_v3_dict(a)) != snapshot_sha256(as_v3_dict(b))
    b = deepcopy(a)
    b["dataset_fields"][0]["dimension"] = {"is_time": False}
    assert as_v3_dict(b)["dataset_fields"][0]["dimension"] == {"is_time": False}
    assert snapshot_sha256(as_v3_dict(a)) != snapshot_sha256(as_v3_dict(b))


@pytest.mark.parametrize("path", ["roles", "verbalizes", "extends", "unique_keys", "dialects", "null", "unicode"])
def test_v3_native_json_hash_changes_for_meaningful_changes(path):
    before = as_v3_dict(native_draft())
    after = deepcopy(before)
    if path == "roles":
        after["link_types"][0]["roles"].reverse()
    elif path == "verbalizes":
        after["link_types"][0]["verbalizes"].pop()
    elif path == "extends":
        after["value_types"][0]["extends"].pop()
    elif path == "unique_keys":
        after["datasets"][0]["unique_keys"][0].reverse()
    elif path == "dialects":
        after["dataset_fields"][0]["expression"]["dialects"].pop()
    elif path == "null":
        del after["ai_context"]["ontofoundry"]["null"]
    else:
        after["object_types"][0]["concept"] = "  é  "
    assert snapshot_sha256(after) != snapshot_sha256(before)


def test_v3_hash_only_normalizes_registered_domain_paths():
    raw = {"ai_context": {"tags": ["b", "a", "b"], "extends": [None], "evidence": [None], "null": None, "e\u0301": "e\u0301"}}
    assert json.loads(canonical(raw, hash_algorithm=V3_HASH_ALGORITHM)) == raw
    a = as_v3_dict(native_draft())
    b = deepcopy(a)
    b["mapping_nodes"].reverse()
    b["link_types"][0]["tags"] = ["b", "a", "a"]
    a["link_types"][0]["tags"] = ["a", "b"]
    assert snapshot_sha256(a) == snapshot_sha256(b)
    element = a["link_types"][0]
    assert element_sha256(element, hash_algorithm=V3_HASH_ALGORITHM, collection="link_types") == element_sha256(b["link_types"][0], hash_algorithm=V3_HASH_ALGORITHM, collection="link_types")
    with pytest.raises(CanonicalizationError, match="collection"):
        element_sha256(element, hash_algorithm=V3_HASH_ALGORITHM)
    with pytest.raises(CanonicalizationError, match="未知"):
        canonical({}, hash_algorithm="future")
    with pytest.raises(CanonicalizationError, match="hash_algorithm"):
        snapshot_sha256({"schema_version": "3"})


def test_legacy_hash_vectors_and_verification_keep_the_original_algorithm():
    legacy = OntologyDraft(workspace_id="44444444-4444-4444-8444-444444444444").model_dump(mode="json")
    expected = "84ff0cdfd63bf311fb8a75b043702c54ec156e1da0f94f57643dfe7337c0eb73"
    assert snapshot_sha256(legacy) == expected
    assert verify_snapshot_sha256(legacy, expected)
    assert snapshot_sha256(legacy, hash_algorithm=LEGACY_HASH_ALGORITHM) == expected
    assert not verify_snapshot_sha256(as_v3_dict(legacy), expected)
    old = {"tags": ["b", "a", "a"], "x": None, "name": "e\u0301"}
    assert canonical(old) == '{"name":"é","tags":["a","b"]}'
    with pytest.raises(CanonicalizationError, match="未登记"):
        canonical({"unregistered": [1]})


@pytest.mark.parametrize("source", ["v1", "v2", "actions", "empty"])
def test_read_migration_is_pure_deterministic_and_idempotent(source):
    data = v1_demo() if source == "v1" else mapped_draft().model_dump(mode="json") if source == "v2" else action_draft().model_dump(mode="json") if source == "actions" else OntologyDraft(workspace_id=WORKSPACE).model_dump(mode="json")
    original = deepcopy(data)
    old_hash = normalized_snapshot_sha256(data)
    migrated = read_snapshot_json(data, target_version="3")
    assert data == original
    assert read_snapshot_json(data, target_version="3") == migrated
    assert as_v3_dict(migrated) == migrated
    assert read_snapshot_json(migrated, target_version="3") == migrated
    assert normalized_snapshot_sha256(data) == old_hash
    assert draft_sha256(data) == draft_sha256(original)
    assert read_snapshot_json(data)["schema_version"] == "2"
    assert migrated["mappings"] == []
    assert migrated["ossie_name"] is None and migrated["ossie_description"] is None
    assert migrated["document_origin"] == "migrated"
    with pytest.raises(ValueError, match="schema_version"):
        read_snapshot(migrated)
    with pytest.raises(ValueError, match="工作空间"):
        read_snapshot(migrated, uid("foreign"), target_version="3")
    with pytest.raises(ValueError, match="schema_version"):
        read_snapshot(data, target_version="future")


def test_mapping_migration_keeps_keys_expressions_joins_and_new_identity_kinds():
    data = mapped_draft().model_dump(mode="json")
    migrated = normalize_v2_to_v3(data)
    assert len(migrated["semantic_models"]) == 1
    assert len(migrated["datasets"]) == 2
    names = {d["id"]: d["name"] for d in migrated["datasets"]}
    assert {(names[f["dataset_id"]], f["name"]) for f in migrated["dataset_fields"]} == {
        ("supplier", "supplier_code"), ("supplier", "supplier_name"), ("supplier", "code"),
        ("material", "material_code"), ("material", "code"), ("material", "supplier_code"),
    }
    assert len(migrated["dataset_relationships"]) == 1
    assert len(migrated["concept_mappings"]) == 2
    assert {i["slot"] for i in migrated["mapping_nodes"]} == {"object_mappings", "link_mappings", "object_mapping", "children"}
    source_by_name = {i["name"]: i["source"] for i in migrated["datasets"]}
    assert source_by_name == {"material": "materials", "supplier": "public.suppliers"}
    ext = json.loads(migrated["semantic_models"][0]["custom_extensions"][0]["data"])
    assert ext == {"connection_alias": "erp"}
    new_ids = set(migrated["extension_v4"]["ids"].values())
    for old in data["mappings"]:
        assert old["id"] not in new_ids
        assert migrated["extension_v4"]["legacy_mapping_ids"][old["id"]] in new_ids
    # Independence includes the already-v3 path, not just the migration path.
    clone = as_v3_dict(migrated)
    clone["datasets"][0]["primary_key"].append("new")
    assert clone != migrated


@pytest.mark.parametrize("multiplicity", ["one_to_one", "many_to_one", "one_to_many", "many_to_many"])
def test_legacy_binary_direction_role_names_and_platform_cardinality_survive(multiplicity):
    data = mapped_draft().model_dump(mode="json")
    old = data["link_types"][0]
    old.update(multiplicity=multiplicity, source_role_name="source", target_role_name="target", identifier=False)
    migrated = read_snapshot(data, target_version="3")
    link = migrated.link_types[0]
    assert str(link.source_type_id) == old["source_type_id"]
    assert str(link.target_type_id) == old["target_type_id"]
    assert link.target_role_name == "target" and link.source_role_name == "source"
    assert link.legacy_multiplicity == multiplicity
    assert str(link.owner_ref.ref) == old["target_type_id" if multiplicity == "one_to_many" else "source_type_id"]
    assert link.multiplicity == ("OneToOne" if multiplicity == "one_to_one" else None if multiplicity == "many_to_many" else "ManyToOne")


def test_cross_connection_join_is_preserved_in_read_only_bridge_model():
    data = mapped_draft().model_dump(mode="json")
    data["mappings"][1]["connection_alias"] = "other"
    draft = read_snapshot(data, target_version="3")
    assert len(draft.semantic_models) == 3
    assert len(draft.dataset_relationships) == 1
    bridge = next(i for i in draft.semantic_models if i.name.startswith("legacy_join_"))
    extension = json.loads(bridge.custom_extensions[0].data)
    assert extension["read_only_reason"] == "cross_connection"
    assert set(extension["legacy_connection_aliases"].values()) == {"erp", "other"}


def instance_draft():
    data = native_draft()
    data["material_objects"] = [{"id": uid("fact_object"), "type_id": uid("object"), "name": "object"}]
    data["material_links"] = [{"id": uid("fact"), "type_id": uid("link"), "role_values": [
        {"role_id": str(uuid5(UUID(uid("link")), "role:owner")), "value": "Code1"},
        {"role_id": uid("role0"), "object_id": uid("fact_object")},
        {"role_id": uid("role1"), "value": 7},
        {"role_id": uid("role2"), "object_id": uid("fact_object")},
    ]}]
    return data


def test_nary_role_values_include_owner_and_validate_types():
    data = instance_draft()
    assert len(OntologyDraft.model_validate(data).material_links[0].role_values) == 4
    for case in ("missing_owner", "wrong_type", "object_as_value", "binary_view"):
        broken = deepcopy(data)
        values = broken["material_links"][0]["role_values"]
        if case == "missing_owner":
            values.pop(0)
        elif case == "wrong_type":
            values[2]["value"] = True
        elif case == "object_as_value":
            values[0]["object_id"] = uid("fact_object")
        else:
            broken["material_links"][0]["source_id"] = uid("fact_object")
        with pytest.raises(ValidationError):
            OntologyDraft.model_validate(broken)


def test_explicit_nary_multiplicity_is_validated_without_inference():
    data = instance_draft()
    second = deepcopy(data["material_links"][0])
    second["id"] = uid("fact2")
    second["role_values"][2]["value"] = 8
    data["material_links"].append(second)
    OntologyDraft.model_validate(data)  # multiplicity absent: no assumption
    data["link_types"][0]["multiplicity"] = "ManyToOne"
    with pytest.raises(ValidationError, match="基数"):
        OntologyDraft.model_validate(data)


def test_version_boundary_remains_explicit_and_extension_v4_is_strict():
    data = native_draft()
    data["extension_v4"]["version"] = "3"
    with pytest.raises(ValidationError):
        OntologyDraft.model_validate(data)
    with pytest.raises(ValidationError, match="schema_version"):
        OntologyDraft(workspace_id=WORKSPACE, schema_version="3")
    with pytest.raises(ValidationError, match="schema_version"):
        OntologyDraft(workspace_id=WORKSPACE, ai_context={})
    assert not hasattr(SemanticModel, "workspace_id")


def test_matrix_covers_all_pinned_properties_and_fixture_occurrences():
    script = runpy.run_path(str(ROOT / "scripts/ossie_coverage_matrix.py"))
    rows = list(script["catalog"]())
    assert len(rows) == 93
    assert sum(r[2] != "$value" for r in rows) == 87
    for source, schema in script["SCHEMAS"].items():
        assert set(schema["$defs"]) <= {r[1] for r in rows if r[0] == source}
    assert script["OUTPUT"].read_text() == script["render"]([ROOT / "apps/api/tests/fixtures/ossie_synthetic" / (stem + ".ossie.json") for stem in ("storybook-lending", "library-lending")])
    fixture = ROOT / "apps/api/tests/fixtures/ossie_synthetic/library-lending.ossie.json"
    document = json.loads(fixture.read_text())
    counts = script["occurrences"](document)
    assert counts["core", "Dataset", "name"] == 8
    assert counts["core", "Field", "name"] == 41
    assert counts["core", "Relationship", "name"] == 5
    assert counts["core", "Metric", "name"] == 8
    assert counts["core", "$root", "semantic_model"] == 0
    # Empty fields count as present, not as zero population.
    minimal = {"ontology": [{"concept": "", "relationships": [{"roles": [], "verbalizes": []}]}]}
    assert script["occurrences"](minimal)["ontology", "Relationship", "roles"] == 1
    assert coverage.UNSUPPORTED_OSSIE_PATHS == {}


def test_unsupported_guard_only_rejects_registered_paths_and_reports_indices(monkeypatch):
    document = {"ontology": [{"relationships": [{"roles": []}, {"roles": [{"concept": "Any"}]}]}]}
    assert list(coverage.unsupported_constructs(document)) == []
    monkeypatch.setattr(coverage, "UNSUPPORTED_OSSIE_PATHS", {("ontology", "*", "relationships", "*", "roles", "*", "concept"): "frozen test reason"})
    with pytest.raises(OssieImportError, match=r"\$\.ontology\[0\]\.relationships\[1\]\.roles\[0\]\.concept.*frozen test reason"):
        parse_ossie(document, workspace_id=str(WORKSPACE))


def test_versioned_structural_schemas_do_not_enable_v3_api_saves_in_p0():
    import jsonschema

    schema = OntologyDraft.model_json_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(native_draft(), schema)
    jsonschema.validate(mapped_draft().model_dump(mode="json"), schema)
    jsonschema.validate(native_draft(), OntologyDraft.model_json_schema(draft_version="3"))
    with pytest.raises(ValueError, match="schema_version"):
        OntologyDraft.model_json_schema(draft_version="future")


def test_nested_concept_client_reference_is_only_allowed_before_persistence():
    role = RoleRef.model_validate({"id": uid("pending_role"), "concept": {"kind": "object_type", "ref": {"client_ref": "created.object"}}})
    assert role.model_dump(mode="json")["concept"]["ref"] == {"client_ref": "created.object"}
    data = native_draft()
    data["link_types"][0]["roles"][0] = role.model_dump(mode="json")
    with pytest.raises(ValidationError, match="client_ref"):
        OntologyDraft.model_validate(data)


def test_fixed_v3_hash_vector_and_old_v1_verification():
    expected = "223da43c623e8903742ecf1e3d424f9e29dac35ea11888dffae378b53904c0dd"
    assert snapshot_sha256(as_v3_dict(native_draft())) == expected
    legacy = v1_demo()
    assert verify_snapshot_sha256(legacy, normalized_snapshot_sha256(legacy))


def test_migration_preserves_joins_for_same_relationship_name_under_different_owners():
    data = mapped_draft().model_dump(mode="json")
    first = next(i for i in data["link_types"] if i["data_join"] is not None)
    other = {**deepcopy(first), "id": uid("same_named_join"), "multiplicity": "one_to_many", "identifier": False}
    data["link_types"].append(other)
    migrated = read_snapshot(data, target_version="3")
    joins = migrated.dataset_relationships
    assert len(joins) == 2
    assert len({i.id for i in joins}) == 2
    assert len({i.name for i in joins}) == 2
    assert {i.from_ for i in joins} == {joins[0].from_}
    assert as_v3_dict(migrated.model_dump(mode="json")) == migrated.model_dump(mode="json")


def test_v3_extension_projection_cannot_override_the_single_element_truth():
    data = native_draft()
    data["extension_v4"]["display_names"] = {uid("object"): "different"}
    with pytest.raises(ValidationError, match="显示名"):
        OntologyDraft.model_validate(data)
    with pytest.raises(CanonicalizationError, match="不一致"):
        snapshot_sha256(as_v3_dict(native_draft()), hash_algorithm=LEGACY_HASH_ALGORITHM)


def test_v3_platform_evidence_still_uses_existing_evidence_validation():
    data = native_draft()
    data["link_types"][0]["evidence"] = [{"id": uid("bad_evidence"), "kind": "unknown"}]
    with pytest.raises(ValidationError):
        OntologyDraft.model_validate(data)


def test_v2_cannot_store_native_v3_elements_even_through_python_constructor():
    native_object = OntologyDraft.model_validate(native_draft()).object_types[0]
    native_object.name = "Object"
    native_object.technical_name = "object"
    native_object.extends = []
    with pytest.raises(ValidationError, match="schema_version 2"):
        OntologyDraft(workspace_id=WORKSPACE, object_types=[native_object])
