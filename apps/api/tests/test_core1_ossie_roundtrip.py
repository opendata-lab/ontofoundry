"""Directed semantic round trips assert transformations, rather than report presence alone."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from core1_fixtures import example_draft
from rt_cases import OSSIE_IMPORT_CASES
from test_core1_ossie_export import export

from ontofoundry_api.adapters.archive import read_ossie
from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.ossie.importer import OssieAdapter
from ontofoundry_api.domain.core import ExpressionMetric, SimpleMetric
from ontofoundry_api.domain.validation import validate_core_graph


def roundtrip(model):
    result = export(model)
    assert result.document is not None, [
        i.message for i in result.report.issues if i.outcome == "error"
    ]
    restored = OssieAdapter().import_document(
        result.document, ImportContext(model.workspace_id)
    )
    return result, restored


def property_projection(model):
    objects = {o.id: o.name for o in model.object_types}
    return {
        (objects[p.owner_type_id], p.name): (
            p.name,
            str(p.value_kind),
            p.identifier,
            p.unique,
            p.required,
            tuple(p.synonyms),
        )
        for p in model.properties
    }


@pytest.mark.parametrize(
    "name",
    [
        "01-basic-sales",
        "02-many-to-many",
        "03-n-ary-reified",
        "04-composite-key",
        "05-self-and-parallel-links",
        "06-inheritance",
        "08-rules",
    ],
)
def test_business_definitions_survive_supported_ontology_exchange(name):
    model = example_draft(name)
    _, restored = roundtrip(model)
    assert property_projection(restored.model) == property_projection(model)
    old = {o.id: o.name for o in model.object_types}
    new = {o.id: o.name for o in restored.model.object_types}
    assert {(o.name, old.get(o.extends)) for o in model.object_types} == {
        (o.name, new.get(o.extends)) for o in restored.model.object_types
    }
    assert {
        (
            old[link.source_type_id],
            old[link.target_type_id],
            link.name,
            str(link.multiplicity),
            link.source_role_name,
            link.target_role_name,
            tuple(link.verbalizes),
        )
        for link in model.link_types
    } == {
        (
            new[link.source_type_id],
            new[link.target_type_id],
            link.name,
            str(link.multiplicity),
            link.source_role_name,
            link.target_role_name,
            tuple(link.verbalizes),
        )
        for link in restored.model.link_types
    }
    assert sorted(r.expression for r in restored.model.rules) == sorted(
        r.expression for r in model.rules
    )


def metric_container():
    model = example_draft("13-dataset-metrics")
    # A separate explicit business container; the original object-free example is unchanged.
    obj = example_draft("10-partial").object_types[0].model_copy(deep=True)
    obj.extends, obj.derived_by, obj.title_property_id = None, [], None
    model.object_types = [obj]
    return model


def test_dataset_metrics_one_to_one_and_count_case_roundtrip():
    model = metric_container()
    exported, restored = roundtrip(model)
    original = {m.name: m for m in model.metrics}
    returned = {m.name: m for m in restored.model.metrics}
    assert original.keys() == returned.keys()
    datasets = {d.id: d.name for d in model.datasets}
    back_datasets = {d.id: d.name for d in restored.model.datasets}
    for name, metric in original.items():
        actual = returned[name]
        assert metric.kind == actual.kind
        if isinstance(metric, SimpleMetric):
            assert metric.aggregation == actual.aggregation
            assert datasets[metric.dataset_id] == back_datasets[actual.dataset_id]
            assert (metric.measure.column if metric.measure else None) == (
                actual.measure.column if actual.measure else None
            )
            assert [(f.column.column, f.operator, f.values) for f in metric.filters] == [
                (f.column.column, f.operator, f.values) for f in actual.filters
            ]
    file = json.loads(read_ossie(exported.document)[0])
    expressions = {
        m["name"]: m["expression"]["dialects"][0]["expression"]
        for scope in file["ontology_mappings"]
        for m in scope["semantic_model"]["metrics"]
    }
    for name, metric in original.items():
        if isinstance(metric, SimpleMetric) and str(metric.aggregation) == "count":
            text = expressions[name]
            assert "IS NULL THEN 1 ELSE 1 END" in text and "COUNT(*)" not in text


def test_count_star_expression_keeps_other_algorithm_literal_and_declared_source():
    model = metric_container()
    dataset = model.datasets[0]
    model.metrics = [
        ExpressionMetric(
            id=uuid4(),
            kind="expression",
            display_name="虚构表达式",
            name="fiction_expression",
            dataset_id=dataset.id,
            expression="COUNT(*) + LENGTH('COUNT(*)::literal')",
            value_kind="integer",
        )
    ]
    exported, restored = roundtrip(model)
    actual = restored.model.metrics[0]
    assert actual.kind == "expression" and "COUNT(*)::literal" in actual.expression
    assert "IS NULL THEN 1 ELSE 1 END" in actual.expression
    assert restored.model.datasets[0].name == dataset.name
    model.datasets[0].columns = None
    assert export(model).document is None


def test_nullable_column_count_is_never_changed_into_row_count():
    model = metric_container()
    dataset = model.datasets[0]
    column = dataset.columns[0].name
    model.metrics = [
        ExpressionMetric(
            id=uuid4(),
            kind="expression",
            display_name="可空列计数",
            name="nullable_count",
            dataset_id=dataset.id,
            expression=f'COUNT("{dataset.name}"."{column}")',
            value_kind="integer",
        )
    ]
    _, restored = roundtrip(model)
    assert restored.model.metrics[0].kind == "expression"
    assert "CASE" not in restored.model.metrics[0].expression.upper()


def test_ratio_without_declared_components_remains_one_expression():
    model = metric_container()
    model.metrics = [m for m in model.metrics if m.kind == "ratio"]
    # Build a direct expression after removing structured component definitions.
    dataset = model.datasets[0]
    model.metrics = [
        ExpressionMetric(
            id=uuid4(),
            display_name="虚构比率",
            name="fraction",
            kind="expression",
            dataset_id=dataset.id,
            expression=f'SUM("{dataset.name}"."{dataset.columns[-1].name}") / NULLIF(COUNT(*), 0)',
            value_kind="decimal",
        )
    ]
    _, restored = roundtrip(model)
    assert (
        len(restored.model.metrics) == 1 and restored.model.metrics[0].kind == "expression"
    )


@pytest.mark.parametrize(
    "name",
    [
        "01-basic-sales",
        "02-many-to-many",
        "04-composite-key",
        "11-multi-source-and-unique-link",
    ],
)
def test_mapping_columns_main_identity_and_flat_auxiliary_sources_survive(name):
    from ontofoundry_api.domain.bindings import resolve_binding

    model = example_draft(name)
    exported, restored = roundtrip(model)
    for obj in model.object_types:
        original = resolve_binding(model, obj.id)
        returned_obj = next(o for o in restored.model.object_types if o.name == obj.name)
        returned = resolve_binding(restored.model, returned_obj.id)
        assert (original.main is None) == (returned.main is None)
        if original.main is None:
            continue
        original_ds = {d.id: d.table_name for d in model.datasets}
        returned_ds = {d.id: d.table_name for d in restored.model.datasets}

        def columns(binding, datasets):
            return {
                key: (datasets[binding.sources[field.source_id].dataset_id], field.column)
                for key, field in binding.fields.items()
                if field.kind == "column"
            }

        assert columns(original, original_ds) == columns(returned, returned_ds)
        assert (
            original_ds[original.main.dataset_id] == returned_ds[returned.main.dataset_id]
        )
    if name == "11-multi-source-and-unique-link":
        value = json.loads(read_ossie(exported.document)[0])
        scope = value["ontology_mappings"][0]
        customer = next(
            d for d in scope["semantic_model"]["datasets"] if d["name"] == "customers"
        )
        assert ["code"] in customer["unique_keys"]
        assert any(
            r["to_columns"] == ["code"] for r in scope["semantic_model"]["relationships"]
        )
        # Physical uniqueness remains usable, but customer_code cannot stand in for customer_id.
        assert restored.model.link_types[0].data_join is None
        assert any(
            i.rule_id == "RT-53" and i.outcome == "dropped" for i in exported.report.issues
        )


def test_snapshot_history_keys_and_time_loss_do_not_forge_same_day_joins():
    model = example_draft("12-snapshot-and-trends")
    exported, restored = roundtrip(model)
    scope = json.loads(read_ossie(exported.document)[0])["ontology_mappings"][0][
        "semantic_model"
    ]
    assert len(scope["datasets"]) == 3
    assert all(d["primary_key"][-1] == "snapshot_date" for d in scope["datasets"])
    assert not scope["relationships"]
    # The extension file restores snapshot dates and time fields; the pure Ossie
    # file still loses the structure, so RT-60 stays reported on export.
    assert [d.snapshot_date_column for d in restored.model.datasets] == [
        d.snapshot_date_column for d in model.datasets
    ]
    assert all(d.dialect is None for d in restored.model.datasets)
    assert [m.time_field.column for m in restored.model.metrics] == [
        m.time_field.column for m in model.metrics
    ]
    assert all("快照日期列" in d.description for d in restored.model.datasets)
    assert sum(i.rule_id == "RT-60" for i in exported.report.issues) == 6


def test_member_branches_and_expression_preserve_union_and_paths():
    model = example_draft("06-inheritance")
    exported, restored = roundtrip(model)
    first = {o.name: o for o in model.object_types}
    second = {o.name: o for o in restored.model.object_types}
    from ontofoundry_api.adapters.ossie.exporter import membership
    from ontofoundry_api.domain.graph import DraftIndex

    for name, obj in first.items():
        if obj.derived_by:
            assert membership(model, obj, DraftIndex(model)) == membership(
                restored.model, second[name], DraftIndex(restored.model)
            )
    assert any(i.rule_id == "RT-67" for i in exported.report.issues)


def test_or_branches_reverse_exists_and_each_inheritance_level_survive():
    from test_core1_ossie_import import document, entity, rel, run

    from ontofoundry_api.adapters.ossie.exporter import membership
    from ontofoundry_api.domain.graph import DraftIndex

    source = run(
        document(
            entity(
                "customer",
                relationships=[
                    rel("level", "String"),
                    rel(
                        "contact",
                        "customer",
                        roles=[{"concept": "customer", "name": "related"}],
                        verbalizes=["{customer} contact {customer:related}"],
                        multiplicity="ManyToOne",
                    ),
                ],
            ),
            entity(
                "vip",
                extends=["customer"],
                derived_by=[
                    "customer.level = 'VIP'",
                    "EXISTS (customer.contact.REVERSE(contact))",
                ],
            ),
            entity("special", extends=["vip"], derived_by=["vip.level = 'SPECIAL'"]),
        )
    ).model
    _, restored = roundtrip(source)
    returned = {o.name: o for o in restored.model.object_types}
    for obj in source.object_types:
        if obj.derived_by:
            assert membership(source, obj, DraftIndex(source)) == membership(
                restored.model, returned[obj.name], DraftIndex(restored.model)
            )
    assert len(returned["vip"].derived_by) == 2
    assert len(returned["special"].derived_by) == 1


@pytest.mark.parametrize("selected", ["orders", "customers"])
def test_row_count_remembers_explicit_dataset_among_multiple_candidates(selected):
    model = example_draft("01-basic-sales")
    ds = next(d for d in model.datasets if d.name == selected)
    model.metrics = [
        SimpleMetric(
            id=uuid4(),
            display_name="虚构行数",
            name="fiction_rows",
            kind="simple",
            dataset_id=ds.id,
            aggregation="count",
        )
    ]
    _, restored = roundtrip(model)
    assert restored.model.metrics[0].kind == "simple"
    assert (
        next(
            d.name
            for d in restored.model.datasets
            if d.id == restored.model.metrics[0].dataset_id
        )
        == selected
    )


def test_constant_expression_source_cannot_be_silently_discarded():
    model = metric_container()
    model.metrics = [
        ExpressionMetric(
            id=uuid4(),
            display_name="虚构常量",
            name="constant",
            kind="expression",
            dataset_id=model.datasets[0].id,
            expression="1 + 1",
            value_kind="integer",
        )
    ]
    result = export(model)
    assert result.document is None
    assert any(
        i.rule_id == "RT-61"
        and i.outcome == "error"
        and i.target_element_ids == [model.metrics[0].id]
        for i in result.report.issues
    )


def test_field_alias_collision_keeps_physical_columns_and_metric_scope():
    model = example_draft("01-basic-sales")
    mapping = next(m for m in model.mappings if "amount" in m.fields)
    mapping.fields["amount"].column = "amount_col"
    dataset = next(d for d in model.datasets if d.id == mapping.sources[0].dataset_id)
    dataset.columns.append(dataset.columns[0].model_copy(update={"name": "amount_col"}))
    exported, restored = roundtrip(model)
    raw = next(
        d
        for scope in json.loads(read_ossie(exported.document)[0])["ontology_mappings"]
        for d in scope["semantic_model"]["datasets"]
        if d["name"] == dataset.name
    )
    fields = {
        f["name"]: f["expression"]["dialects"][0]["expression"] for f in raw["fields"]
    }
    assert fields["amount"] == '"amount_col"'
    assert fields["amount_col"] == '"amount"'
    assert any(i.rule_id == "RT-40" for i in exported.report.issues)
    returned_dataset = next(d for d in restored.model.datasets if d.name == dataset.name)
    returned_metric = next(
        m for m in restored.model.metrics if m.name == model.metrics[0].name
    )
    assert returned_metric.dataset_id == returned_dataset.id
    assert returned_metric.measure.column == model.metrics[0].measure.column


@pytest.mark.parametrize("case", OSSIE_IMPORT_CASES, ids=lambda c: c.source)
def test_original_ossie_cases_roundtrip_supported_core_subset(case):
    raw = (Path(__file__).parent / "fixtures" / case.source).read_bytes()
    first = OssieAdapter().import_document(
        raw, ImportContext(UUID("44444444-4444-4444-8444-444444444444"))
    )
    _, second = roundtrip(first.model)
    assert property_projection(first.model) == property_projection(second.model)
    assert {o.name for o in first.model.object_types} == {
        o.name for o in second.model.object_types
    }
    assert {m.name for m in first.model.metrics} == {m.name for m in second.model.metrics}
    assert len(first.model.datasets) == len(second.model.datasets)
    validate_core_graph(second.model)


@pytest.mark.parametrize(
    "operator,values",
    [
        ("eq", [3]),
        ("ne", [3]),
        ("gt", [3]),
        ("ge", [3]),
        ("lt", [3]),
        ("le", [3]),
        ("between", [1, 3]),
        ("in", [1, 3]),
        ("not_in", [1, 3]),
        ("is_null", []),
        ("not_null", []),
    ],
)
def test_each_fixed_filter_survives_row_count_case(operator, values):
    from ontofoundry_api.domain.core import Condition

    model = metric_container()
    dataset = model.datasets[0]
    reference = {"dataset_id": dataset.id, "column": "commit_count"}
    model.metrics = [
        SimpleMetric(
            id=uuid4(),
            display_name="虚构条件行数",
            name="filtered_rows",
            kind="simple",
            dataset_id=dataset.id,
            aggregation="count",
            filters=[Condition(column=reference, operator=operator, values=values)],
        )
    ]
    _, returned = roundtrip(model)
    actual = returned.model.metrics[0]
    assert actual.kind == "simple" and actual.aggregation == "count"
    assert actual.filters[0].operator == operator and actual.filters[0].values == values
    assert actual.filters[0].column.column == "commit_count"


def test_computed_property_keeps_algorithm_and_resolved_physical_columns():
    import sqlglot
    from sqlglot import exp

    from ontofoundry_api.domain.expressions import resolve_field_expression

    model = example_draft("04-composite-key")
    _, restored = roundtrip(model)

    def formulas(draft):
        objects = {o.id: o.name for o in draft.object_types}
        datasets = {d.id: d.table_name for d in draft.datasets}
        result = {}
        for mapping in draft.mappings:
            for key, field in mapping.fields.items():
                if field.kind != "expression":
                    continue
                resolved = resolve_field_expression(draft, mapping, field.expression)
                text = resolved.text
                for ref in reversed(resolved.references):
                    text = (
                        text[: ref.start]
                        + exp.column(
                            ref.column, table=datasets[ref.dataset_id], quoted=True
                        ).sql()
                        + text[ref.end :]
                    )
                result[objects[mapping.type_id], key] = sqlglot.parse_one(text).sql()
        return result

    assert formulas(model)
    assert formulas(model) == formulas(restored.model)
