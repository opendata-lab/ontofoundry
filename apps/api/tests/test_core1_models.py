"""Graph invariants and binding readiness over the actual design examples."""

from uuid import uuid4

import pytest
from core1_fixtures import example_draft, example_draft_json, example_names
from pydantic import ValidationError

from ontofoundry_api.domain.bindings import binding_readiness, resolve_binding
from ontofoundry_api.domain.core import (
    CoreDraft,
    DataMapping,
    DerivedSimple,
    DirectJoin,
    MaterialObject,
    ObjectType,
    Path,
    PathCondition,
    Property,
    SimpleMetric,
    empty_draft,
)
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.validation import validate_core_graph


def obj(draft, name):
    return next(o for o in draft.object_types if o.technical_name == name)


def dataset(draft, name):
    return next(d for d in draft.datasets if d.name == name)


@pytest.mark.parametrize("name", example_names())
def test_design_examples_are_valid_core_graphs(name):
    draft = example_draft(name)
    assert validate_core_graph(draft) is draft


def test_empty_draft_has_nine_collections():
    draft = empty_draft(uuid4())
    assert len(draft.model_dump()) == 11
    assert validate_core_graph(draft)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "3"},
        {"actions": []},
        {"hash_algorithm": "legacy"},
        {"semantic_models": []},
        {"ontology_requires": []},
    ],
)
def test_legacy_draft_shapes_are_rejected(change):
    with pytest.raises(ValidationError):
        CoreDraft.model_validate({**example_draft_json("09-empty"), **change})


@pytest.mark.parametrize(
    "extra", [{"dataset_id": str(uuid4())}, {"value_kind": "decimal"}, {"time_field": None}]
)
def test_ratio_rejects_readonly_fields(extra):
    raw = example_draft_json("13-dataset-metrics")
    ratio = next(m for m in raw["metrics"] if m["kind"] == "ratio")
    ratio.update(extra)
    with pytest.raises(ValidationError):
        CoreDraft.model_validate(raw)


def test_count_is_rows_not_nullable_column_count():
    raw = example_draft_json("13-dataset-metrics")
    count = next(m for m in raw["metrics"] if m.get("aggregation") == "count")
    count["measure"] = {"dataset_id": count["dataset_id"], "column": "repo"}
    with pytest.raises(ValidationError, match="计数"):
        CoreDraft.model_validate(raw)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda d: setattr(d.object_types[1], "id", d.object_types[0].id), "UUID"),
        (
            lambda d: setattr(
                d.object_types[1],
                "technical_name",
                d.object_types[0].technical_name.upper(),
            ),
            "技术名",
        ),
        (lambda d: setattr(d.properties[0], "owner_type_id", uuid4()), "归属"),
        (lambda d: setattr(d.object_types[0], "extends", uuid4()), "父对象"),
        (lambda d: setattr(d.object_types[0], "title_property_id", uuid4()), "标题"),
        (lambda d: setattr(d.mappings[0].sources[0], "dataset_id", uuid4()), "数据集"),
        (lambda d: setattr(d.metrics[0], "dataset_id", uuid4()), "数据集"),
    ],
)
def test_graph_rejects_invalid_references(mutation, match):
    draft = example_draft("01-basic-sales")
    mutation(draft)
    with pytest.raises(ValueError, match=match):
        validate_core_graph(draft)


def test_inheritance_cycle_is_rejected():
    draft = example_draft("06-inheritance")
    obj(draft, "party").extends = obj(draft, "person").id
    with pytest.raises(ValueError, match="环"):
        validate_core_graph(draft)


def test_inherited_namespace_cannot_be_shadowed():
    draft = example_draft("06-inheritance")
    parent = obj(draft, "party")
    child = obj(draft, "person")
    prop = next(p for p in draft.properties if p.owner_type_id == parent.id)
    draft.properties.append(
        prop.model_copy(update={"id": uuid4(), "owner_type_id": child.id})
    )
    with pytest.raises(ValueError, match="命名空间"):
        validate_core_graph(draft)


def test_properties_and_outgoing_links_share_namespace():
    draft = example_draft("01-basic-sales")
    link = draft.link_types[0]
    prop = next(p for p in draft.properties if p.owner_type_id == link.source_type_id)
    link.name = prop.technical_name
    with pytest.raises(ValueError, match="共享命名空间"):
        validate_core_graph(draft)


def test_child_cannot_extend_parent_business_identifier():
    draft = example_draft("06-inheritance")
    child = obj(draft, "person")
    next(p for p in draft.properties if p.owner_type_id == child.id).identifier = True
    with pytest.raises(ValueError, match="父标识"):
        validate_core_graph(draft)


def test_single_identifier_must_be_unique():
    draft = example_draft("01-basic-sales")
    next(p for p in draft.properties if p.identifier).unique = False
    with pytest.raises(ValueError, match="unique"):
        validate_core_graph(draft)


def test_virtual_parent_and_inherited_binding_keep_original_ids():
    draft = example_draft("06-inheritance")
    index = DraftIndex(draft)
    asset, device = obj(draft, "asset"), obj(draft, "device")
    assert binding_readiness(draft, asset.id).status == "virtual"
    bound = resolve_binding(draft, device.id)
    assert "name" in bound.fields
    assert bound.link_bindings
    assert set(bound.link_bindings) <= {link.id for link in index.outgoing_links(asset.id)}
    assert index.title_property(device.id) == index.title_property(asset.id)
    assert index.effective_rules(obj(draft, "person").id)[0].id == draft.rules[0].id


def test_virtual_parent_cannot_hold_direct_fact():
    draft = example_draft("06-inheritance")
    draft.material_objects.append(
        MaterialObject(id=uuid4(), type_id=obj(draft, "asset").id)
    )
    with pytest.raises(ValueError, match="虚拟父"):
        validate_core_graph(draft)


def test_compatible_subtype_fact_endpoint_is_valid():
    draft = example_draft("06-inheritance")
    assert draft.material_links
    validate_core_graph(draft)


def test_bound_parent_cannot_have_independent_child():
    draft = example_draft("06-inheritance")
    child = next(
        m for m in draft.mappings if m.binding_mode == "shared_parent" and m.sources
    )
    child.binding_mode = "independent"
    child.sources[0].id = "main"
    child.membership_source_id = None
    with pytest.raises(ValueError, match="共用父"):
        validate_core_graph(draft)


def test_bound_parent_fields_cannot_be_overridden():
    draft = example_draft("06-inheritance")
    child = next(m for m in draft.mappings if m.type_id == obj(draft, "person").id)
    parent = next(m for m in draft.mappings if m.type_id == obj(draft, "party").id)
    child.fields["name"] = parent.fields["name"].model_copy()
    with pytest.raises(ValueError, match="覆盖"):
        validate_core_graph(draft)


def test_readiness_is_separate_from_structure():
    draft = example_draft("01-basic-sales")
    mapping = draft.mappings[0]
    mapping.sources[0].key_columns = []
    validate_core_graph(draft)
    assert binding_readiness(draft, mapping.type_id).status == "missing_key"
    partial = example_draft("10-partial")
    assert binding_readiness(partial, obj(partial, "city").id).status == "unbound"


def test_shared_parent_needs_membership_for_readiness():
    draft = example_draft("06-inheritance")
    vip = obj(draft, "vip_party")
    vip.derived_by = []
    validate_core_graph(draft)
    assert binding_readiness(draft, vip.id).status == "unbound"


def test_unknown_metadata_can_save_but_known_missing_column_cannot():
    draft = example_draft("01-basic-sales")
    source = draft.mappings[0].sources[0]
    ds = next(d for d in draft.datasets if d.id == source.dataset_id)
    ds.columns = None
    validate_core_graph(draft)
    assert binding_readiness(draft, draft.mappings[0].type_id).status == "unbound"
    ds.columns = [dataset(example_draft("01-basic-sales"), ds.name).columns[0]]
    with pytest.raises(ValueError, match="不存在列"):
        validate_core_graph(draft)


@pytest.mark.parametrize(
    "name,ds,column",
    [
        ("06-inheritance", "devices", "device_name"),
        ("06-inheritance", "vehicles", "responsible_id"),
        ("12-snapshot-and-trends", "component_state_daily", "snapshot_date"),
    ],
)
def test_registered_fixture_metadata_gaps_remain_negative_cases(name, ds, column):
    draft = example_draft(name)
    target = dataset(draft, ds)
    target.columns = [c for c in target.columns if c.name != column]
    with pytest.raises(ValueError, match="不存在列"):
        validate_core_graph(draft)


def test_direct_join_requires_declared_unique_target():
    draft = example_draft("11-multi-source-and-unique-link")
    link = next(link for link in draft.link_types if isinstance(link.data_join, DirectJoin))
    prop = next(
        p for p in draft.properties if p.id == link.data_join.target_property_ids[0]
    )
    assert prop.unique and not prop.identifier
    prop.unique = False
    with pytest.raises(ValueError, match="完整标识"):
        validate_core_graph(draft)


def test_mapping_table_sides_can_have_different_widths():
    draft = example_draft("04-composite-key")
    assert any(
        len(link.data_join.source_columns) != len(link.data_join.target_columns)
        for link in draft.link_types
        if link.data_join and link.data_join.kind == "mapping_table"
    )
    validate_core_graph(draft)


def test_sum_text_and_ratio_cross_dataset_are_invalid():
    draft = example_draft("01-basic-sales")
    metric = next(m for m in draft.metrics if getattr(m, "aggregation", None) == "sum")
    metric.measure.column = "status"
    with pytest.raises(ValueError, match="数值"):
        validate_core_graph(draft)
    draft = example_draft("01-basic-sales")
    ratio = next(m for m in draft.metrics if m.kind == "ratio")
    other_dataset = next(
        d
        for d in draft.datasets
        if d.id != next(c.dataset_id for c in draft.metrics if c.id == ratio.numerator_id)
    )
    other_count = SimpleMetric(
        id=uuid4(),
        name="客户数",
        technical_name="customer_count",
        kind="simple",
        dataset_id=other_dataset.id,
        aggregation="count",
    )
    draft.metrics.append(other_count)
    ratio.denominator_id = other_count.id
    with pytest.raises(ValueError, match="同一数据集"):
        validate_core_graph(draft)


def test_condition_type_and_null_rules():
    draft = example_draft("13-dataset-metrics")
    condition = next(m for m in draft.metrics if getattr(m, "filters", None)).filters[0]
    condition.values = [False]
    with pytest.raises(ValueError, match="类型"):
        validate_core_graph(draft)
    with pytest.raises(ValidationError):
        PathCondition(path=Path(property_id=uuid4()), operator="not_in", values=[None])
    with pytest.raises(ValidationError):
        PathCondition(path=Path(property_id=uuid4()), operator="between", values=[1])


def test_twenty_sources_and_main_not_first():
    draft = example_draft("11-multi-source-and-unique-link")
    mapping = next(m for m in draft.mappings if len(m.sources) > 1)
    template = mapping.sources[1]
    mapping.sources.extend(
        template.model_copy(update={"id": f"extra_{i}"}) for i in range(21)
    )
    mapping.sources.reverse()
    validate_core_graph(draft)
    assert resolve_binding(draft, mapping.type_id).main.id == "main"


def test_multilevel_membership_and_typed_scalar_path():
    draft = empty_draft(uuid4())
    parent = ObjectType(id=uuid4(), name="客户", technical_name="customer")
    prop = Property(
        id=uuid4(),
        owner_type_id=parent.id,
        name="年龄",
        technical_name="age",
        value_kind="integer",
    )
    adult = ObjectType(
        id=uuid4(),
        name="成年客户",
        technical_name="adult",
        extends=parent.id,
        derived_by=[
            DerivedSimple(
                kind="simple",
                conditions=[
                    PathCondition(
                        path=Path(property_id=prop.id), operator="ge", values=[18]
                    )
                ],
            )
        ],
    )
    local = ObjectType(
        id=uuid4(),
        name="本地成年客户",
        technical_name="local_adult",
        extends=adult.id,
        derived_by=[{"kind": "expression", "expression": "adult.age < 65"}],
    )
    draft.object_types = [parent, adult, local]
    draft.properties = [prop]
    validate_core_graph(draft)
    assert DraftIndex(draft).lineage(local.id) == [local.id, adult.id, parent.id]


def test_virtual_sources_stop_at_first_bound_descendant():
    draft = example_draft("06-inheritance")
    device = obj(draft, "device")
    subtype = ObjectType(
        id=uuid4(),
        name="在用设备",
        technical_name="active_device",
        extends=device.id,
        derived_by=[{"kind": "expression", "expression": "device.device_no IS NOT NULL"}],
    )
    draft.object_types.append(subtype)
    draft.mappings.append(
        DataMapping(id=uuid4(), type_id=subtype.id, binding_mode="shared_parent")
    )
    validate_core_graph(draft)
    virtual = resolve_binding(draft, obj(draft, "asset").id)
    assert set(virtual.virtual_types) == {device.id, obj(draft, "vehicle").id}
    assert binding_readiness(draft, subtype.id).status == "bound"


def test_known_unknown_physical_type_stays_incomplete():
    draft = example_draft("01-basic-sales")
    for column in draft.datasets[0].columns:
        column.physical_type = "external_custom_type"
    validate_core_graph(draft)
    mapping = next(
        m for m in draft.mappings if m.sources[0].dataset_id == draft.datasets[0].id
    )
    assert binding_readiness(draft, mapping.type_id).status == "unbound"
