"""Every delivered file passes the pinned official schema and semantic validator."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from core1_fixtures import example_draft, example_names

from ontofoundry_api.adapters.archive import read_archive, read_ossie
from ontofoundry_api.adapters.base import ExportContext
from ontofoundry_api.adapters.ossie.exporter import BASES
from ontofoundry_api.adapters.ossie.importer import OssieAdapter
from ontofoundry_api.adapters.ossie.validator import validate_schema, validate_semantics


def context(model, *, scopes=True):
    return ExportContext(
        "虚构业务",
        "fictional-business",
        "虚构验收",
        dataset_scopes={d.id: "fictional-connection" for d in model.datasets}
        if scopes
        else {},
    )


def export(model, **kwargs):
    return OssieAdapter().export_document(model, context(model, **kwargs))


@pytest.mark.parametrize("name", example_names())
def test_example_delivery_is_officially_valid_or_explicitly_unavailable(name):
    model = example_draft(name)
    result = export(model)
    if name in {"09-empty", "13-dataset-metrics"}:
        assert result.document is None
        assert any(
            i.outcome == "error" and i.source_path == "/object_types"
            for i in result.report.issues
        )
    else:
        assert result.document is not None, [
            i.model_dump() for i in result.report.issues if i.outcome == "error"
        ]
        value = json.loads(read_ossie(result.document)[0])
        assert not validate_schema(value)
        assert not [i for i in validate_semantics(value) if i["severity"] == "error"]
        datasets = [
            d
            for m in value.get("ontology_mappings", [])
            for d in m["semantic_model"]["datasets"]
        ]
        metrics = [
            v
            for m in value.get("ontology_mappings", [])
            for v in m["semantic_model"].get("metrics", [])
        ]
        assert len(datasets) == len(model.datasets)
        assert len(metrics) == len(model.metrics)
        assert len({d["name"] for d in datasets}) == len(datasets)
        assert result.document == export(model).document


def test_identifiers_use_builtin_concepts_and_object_names_avoid_builtins():
    model = example_draft("01-basic-sales")
    prop = next(p for p in model.properties if p.identifier and p.value_type_id is None)
    owner = next(o for o in model.object_types if o.id == prop.owner_type_id)
    result = export(model)
    assert result.document is not None
    ontology = json.loads(read_ossie(result.document)[0])["ontology"]
    # No helper ValueType is invented for an identifier on a built-in type.
    assert [c for c in ontology if c["type"] == "ValueType"] == []
    component = next(c for c in ontology if c["concept"] == owner.name)
    relation = next(r for r in component["relationships"] if r["name"] == prop.name)
    assert prop.name in component["identify_by"]
    assert relation["roles"] == [{"concept": BASES[str(prop.value_kind)]}]
    model.object_types[0].name = "sTrInG"
    assert export(model).document is None


def test_self_relation_keeps_explicit_role_names_and_both_readings():
    model = example_draft("05-self-and-parallel-links")
    result = export(model)
    value = json.loads(read_ossie(result.document)[0])
    for link in model.link_types:
        if link.source_type_id != link.target_type_id:
            continue
        source = next(o for o in model.object_types if o.id == link.source_type_id)
        component = next(c for c in value["ontology"] if c["concept"] == source.name)
        relation = next(r for r in component["relationships"] if r["name"] == link.name)
        assert relation["roles"][0]["name"] == link.target_role_name
        assert len(relation["verbalizes"]) == len(link.verbalizes)
        target = source.name + ":" + link.target_role_name
        assert all("{" + target + "}" in reading for reading in relation["verbalizes"])
        assert json.loads(read_archive(result.document)["ontofoundry-extension.json"])[
            "link_role_names"
        ][source.name + "." + link.name] == {
            "source_role_name": link.source_role_name,
            "target_role_name": link.target_role_name,
        }


def test_invalid_core_metric_cannot_be_silently_omitted():
    model = example_draft("01-basic-sales")
    metric = model.metrics[0]
    metric.dataset_id = uuid4()
    result = export(model)
    assert result.document is None
    assert any(i.outcome == "error" and i.rule_id == "RT-61" for i in result.report.issues)


def test_unknown_connections_do_not_get_guessed_from_similar_table_names():
    model = example_draft("01-basic-sales")
    result = export(model, scopes=False)
    assert result.document is not None
    value = json.loads(read_ossie(result.document)[0])
    assert len(value["ontology_mappings"]) == len(model.datasets)
    assert all(
        r["from"] == r["to"]
        for m in value["ontology_mappings"]
        for r in m["semantic_model"]["relationships"]
    )
    assert any(
        i.rule_id == "RT-53" and i.outcome == "dropped" for i in result.report.issues
    )


def test_conflicting_source_keys_are_omitted_and_do_not_fabricate_identity():
    model = example_draft("01-basic-sales")
    source = model.mappings[0].sources[0]
    clone = deepcopy(model.mappings[0])
    clone.id = uuid4()
    # Test the key collector independently: the core graph itself prevents two mappings per type.
    clone.sources[0].key_columns = ["fiction_other_key"]
    from ontofoundry_api.adapters.exporting import ExportBuilder
    from ontofoundry_api.adapters.ossie.export_mappings import MappingExporter

    model.mappings.append(clone)
    writer = MappingExporter(model, context(model), ExportBuilder("ossie-0.2", model))
    assert "primary_key" not in writer.datasets[source.dataset_id]
    assert any(i.rule_id == "RT-64" for i in writer.report.report.issues)


def test_fact_losses_are_per_instance_and_metadata_notice_is_once_without_reusing_rt26():
    model = example_draft("07-instances-and-evidence")
    result = export(model)
    losses = [
        i
        for i in result.report.issues
        if i.construct in {"material_objects", "material_links"}
    ]
    assert len(losses) == len(model.material_objects) + len(model.material_links)
    assert all(
        i.outcome == "dropped" and i.rule_id is None and len(i.target_element_ids) == 1
        for i in losses
    )
    assert sum(i.construct == "EvidenceMetadata" for i in result.report.issues) == 1
    assert all(i.rule_id != "RT-19" for i in result.report.issues)
