"""Directed source-to-core semantics, including original A/B files and failure isolation."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from rt_cases import OSSIE_IMPORT_CASES

from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.documents import SourceDocument
from ontofoundry_api.adapters.ossie.importer import OssieAdapter
from ontofoundry_api.domain.core import (
    COLLECTIONS,
    ExpressionMetric,
    RatioMetric,
    SimpleMetric,
)
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.validation import validate_core_graph

CTX = ImportContext(UUID("44444444-4444-4444-8444-444444444444"))
FIXTURES = Path(__file__).parent / "fixtures"


def rel(name, target=None, *, source="customer", **kwargs):
    return {
        "name": name,
        "verbalizes": [
            "{" + source + "} " + name + (" {" + target + "}" if target else "")
        ],
        **({"roles": [{"concept": target}]} if target else {}),
        **kwargs,
    }


def entity(name, **kwargs):
    return {"concept": name, "type": "EntityType", **kwargs}


def document(*objects, **kwargs):
    return {
        "version": "0.2.0.dev0",
        "name": "fictional_workspace",
        "ontology": list(objects),
        **kwargs,
    }


def expression(text):
    return {"dialects": [{"dialect": "ANSI_SQL", "expression": text}]}


def field(name, column=None, **kwargs):
    return {"name": name, "expression": expression(column or name), **kwargs}


def dataset(name, **kwargs):
    return {
        "name": name,
        "source": "fiction_" + name,
        "fields": [field("code")],
        "primary_key": ["code"],
        **kwargs,
    }


def ontology_map(datasets, metrics=(), concepts=(), **kwargs):
    return {
        "name": "sales_map",
        "semantic_model": {
            "name": "sales_semantics",
            "datasets": datasets,
            "metrics": list(metrics),
        },
        "concept_mappings": list(concepts),
        **kwargs,
    }


def run(data):
    result = OssieAdapter().import_document(
        json.dumps(data, ensure_ascii=False).encode(), CTX
    )
    validate_core_graph(result.model)
    ids = {e.id for c in COLLECTIONS for e in getattr(result.model, c)}
    source = SourceDocument.parse(json.dumps(data, ensure_ascii=False).encode())
    for issue in result.report.issues:
        assert set(issue.target_element_ids) <= ids
        pointer = issue.source_locator.get("json_pointer")
        if pointer is not None:
            assert source.get(pointer) == json.loads(issue.original)
    return result


def issues(result, rule, outcome=None):
    return [
        i
        for i in result.report.issues
        if i.rule_id == rule and (outcome is None or i.outcome == outcome)
    ]


def test_properties_unary_readings_names_and_whole_identifier():
    data = document(
        entity(
            "customer",
            identify_by=["code"],
            relationships=[rel("code", "String"), rel("is_vip")],
        )
    )
    result = run(data)
    code, vip = result.model.properties
    assert code.identifier and code.unique
    assert vip.value_kind == "boolean" and not vip.identifier
    assert issues(result, "RT-26", "converted") and issues(result, "RT-33", "converted")
    data["ontology"][0]["identify_by"] = ["code", "missing"]
    result = run(data)
    assert not any(p.identifier for p in result.model.properties)
    assert not result.model.properties[0].unique
    assert issues(result, "RT-30", "dropped")


def test_relationship_identifier_does_not_shrink_to_an_attribute():
    result = run(
        document(
            entity(
                "customer",
                relationships=[rel("code", "String"), rel("account", "account")],
                identify_by=["account", "code"],
            ),
            entity("account"),
        )
    )
    assert not result.model.properties[0].identifier
    assert len(result.model.link_types) == 1
    assert issues(result, "RT-32", "dropped")


def test_first_parent_is_file_order_and_child_does_not_change_parent_identity():
    result = run(
        document(
            entity(
                "person",
                relationships=[rel("person_no", "String")],
                identify_by=["person_no"],
            ),
            entity("alternate"),
            entity(
                "employee",
                extends=["person", "alternate"],
                relationships=[rel("employee_no", "String")],
                identify_by=["employee_no"],
            ),
        )
    )
    person, alternate, employee = result.model.object_types
    assert employee.extends == person.id and employee.extends != alternate.id
    local = next(p for p in result.model.properties if p.owner_type_id == employee.id)
    assert local.unique and not local.identifier
    assert DraftIndex(result.model).identifier(employee.id) == DraftIndex(
        result.model
    ).identifier(person.id)
    assert issues(result, "RT-34", "dropped") and issues(result, "RT-68", "dropped")


def test_incompatible_value_ancestors_are_not_guessed_as_string():
    result = run(
        document(
            {"concept": "mixed", "type": "ValueType", "extends": ["String", "Integer"]},
            entity(
                "customer",
                relationships=[rel("code", "mixed"), rel("label", "String")],
                identify_by=["code", "label"],
            ),
        )
    )
    assert [p.name for p in result.model.properties] == ["label"]
    assert not result.model.properties[0].identifier
    assert issues(result, "RT-35") and issues(result, "RT-30")


def test_entity_inheriting_value_is_invalid_and_does_not_block_other_entities():
    result = run(document(entity("invalid", extends=["String"]), entity("valid")))
    assert [o.name for o in result.model.object_types] == ["valid"]
    assert any(
        i.outcome == "error" and i.source_path == "/ontology/0"
        for i in result.report.issues
    )


def test_value_types_import_as_shared_types_and_fold_ancestor_constraints():
    data = document(
        {
            "concept": "Money",
            "type": "ValueType",
            "extends": ["Decimal"],
            "requires": ["Money >= 0"],
        },
        {
            "concept": "Positive",
            "type": "ValueType",
            "extends": ["Money"],
            "requires": ["Positive > 0"],
        },
        entity(
            "customer", relationships=[rel("amount", "Money"), rel("refund", "Positive")]
        ),
    )
    result = run(data)
    types = {v.name: v for v in result.model.value_types}
    assert set(types) == {"Money", "Positive"}
    assert {str(v.value_kind) for v in types.values()} == {"decimal"}
    props = {p.name: p for p in result.model.properties}
    assert props["amount"].value_type_id == types["Money"].id
    assert props["refund"].value_type_id == types["Positive"].id
    # Constraints live on the types, not copied to every property; the
    # ancestor's constraint folds into the descendant (no value type inheritance).
    owned = {(r.owner_id, r.expression) for r in result.model.rules}
    assert owned == {
        (types["Money"].id, "Money >= 0"),
        (types["Positive"].id, "Positive >= 0"),
        (types["Positive"].id, "Positive > 0"),
    }
    assert all(str(r.owner_kind) == "value_type" for r in result.model.rules)
    assert issues(result, "RT-24")


def test_nary_many_to_one_uses_all_determining_roles_and_direct_business_identifiers():
    data = document(
        entity(
            "warehouse",
            identify_by=["code"],
            relationships=[
                rel("code", "String"),
                {
                    "name": "route",
                    "roles": [
                        {"concept": "warehouse", "name": "destination"},
                        {"concept": "Integer", "name": "days"},
                    ],
                    "multiplicity": "ManyToOne",
                    "verbalizes": [
                        "{warehouse} 到 {warehouse:destination} 用 {Integer:days}"
                    ],
                },
            ],
        )
    )
    result = run(data)
    intermediate = next(o for o in result.model.object_types if o.name == "warehouse_route")
    props = [p for p in result.model.properties if p.owner_type_id == intermediate.id]
    assert len(props) == 3
    assert len([p for p in props if p.identifier]) == 2
    assert all(p.required for p in props)
    assert not next(p for p in props if p.name == "days").identifier
    links = [
        link for link in result.model.link_types if link.source_type_id == intermediate.id
    ]
    assert len(links) == 2 and all(link.data_join.kind == "direct" for link in links)
    assert links[0].data_join.source_property_ids != links[1].data_join.source_property_ids
    assert issues(result, "RT-27") and issues(result, "RT-28")
    data["ontology"][0]["relationships"][1]["multiplicity"] = "OneToOne"
    bad = run(data)
    assert len(bad.model.object_types) == 1
    assert any(
        i.outcome == "error" and i.completion_status == "not_needed"
        for i in bad.report.issues
    )


def test_last_role_without_identity_does_not_destroy_determining_tuple_key():
    data = document(
        entity(
            "doctor",
            relationships=[
                rel("code", "String"),
                {
                    "name": "shift",
                    "roles": [
                        {"concept": "Date", "name": "date"},
                        {"concept": "department"},
                    ],
                    "multiplicity": "ManyToOne",
                    "verbalizes": ["{doctor} {Date:date} {department}"],
                },
            ],
            identify_by=["code"],
        ),
        entity("department"),
    )
    result = run(data)
    obj = next(o for o in result.model.object_types if o.name == "doctor_shift")
    assert len(DraftIndex(result.model).identifier(obj.id)) == 2
    assert issues(result, "RT-28", "error")
    data["ontology"][0].pop("identify_by")
    result = run(data)
    obj = next(o for o in result.model.object_types if o.name == "doctor_shift")
    assert not DraftIndex(result.model).identifier(obj.id)


def test_membership_is_all_or_nothing_and_keeps_or_and_reverse_exists():
    data = document(
        entity(
            "customer",
            relationships=[
                rel("level", "String"),
                rel(
                    "contact",
                    "customer",
                    roles=[{"concept": "customer", "name": "related"}],
                    verbalizes=["{customer} contact {customer:related}"],
                ),
            ],
        ),
        entity(
            "vip",
            extends=["customer"],
            derived_by=["customer.level = 'VIP'", "EXISTS (customer.REVERSE(contact))"],
        ),
    )
    result = run(data)
    assert len(result.model.object_types[1].derived_by) == 2
    assert not result.model.rules
    assert issues(result, "RT-67", "converted")
    data["ontology"][1]["derived_by"].append("EXISTS (customer.unknown)")
    bad = run(data)
    assert bad.model.object_types[1].derived_by == []
    assert issues(bad, "RT-31", "error")


def test_legacy_extension_is_not_read_and_core_extension_restores_presentation_only():
    data = document(
        entity("customer", relationships=[rel("code", "String")]),
        ai_context={
            "ontofoundry": {"version": "3", "display_names": {"customer": "错误名称"}}
        },
    )
    assert run(data).model.object_types[0].name == "customer"
    data["ai_context"]["ontofoundry"] = {
        "version": "core-1",
        "display_names": {"customer": "客户"},
        "required": ["customer.code"],
        "title_properties": {"customer": "code"},
    }
    result = run(data)
    assert result.model.object_types[0].display_name == "客户"
    assert result.model.properties[0].required
    assert result.model.object_types[0].title_property_id == result.model.properties[0].id


def test_local_schema_error_does_not_drop_unrelated_valid_definition():
    result = run(
        document(
            entity(
                "customer",
                relationships=[
                    {"name": "broken", "roles": [{"concept": "String"}]},
                    rel("code", "String"),
                ],
            ),
            entity("supplier"),
        )
    )
    assert len(result.model.object_types) == 2
    assert [p.name for p in result.model.properties] == ["code"]
    assert result.report.counts["error"] >= 1


@pytest.mark.parametrize(
    "value",
    [
        {"version": "0.2.0.dev0", "semantic_model": {}},
        {"version": "1", "ontology": []},
        {"mapping_documents": []},
    ],
)
def test_unsupported_formats_are_file_errors(value):
    result = run(value)
    assert not result.model.object_types and result.report.issues[0].outcome == "error"


def test_dataset_names_are_scoped_not_merged_and_query_sources_are_not_table_names():
    raw = ontology_map([dataset("same")])
    second = copy.deepcopy(raw)
    second["name"] = "another"
    result = run(document(entity("customer"), ontology_mappings=[raw, second]))
    assert (
        len(result.model.datasets) == 2 and len({d.id for d in result.model.datasets}) == 2
    )
    assert len({d.name for d in result.model.datasets}) == 2
    second["semantic_model"]["datasets"][0]["source"] = "SELECT * FROM fiction_sales"
    result = run(document(entity("customer"), ontology_mappings=[raw, second]))
    # A query source becomes an expression dataset instead of a fake table name (DS-02).
    query = [d for d in result.model.datasets if d.source_kind == "query"]
    assert len(result.model.datasets) == 2 and len(query) == 1
    assert query[0].table_name is None and query[0].query_sql == "SELECT * FROM fiction_sales"


def mapped_concept(name, source, children=()):
    identity = {"expression": source}
    return {
        "concept": name,
        "object_mappings": [identity],
        "link_mappings": [{"object_mapping": identity, "children": list(children)}],
    }


def property_mapping(name, source):
    return {"relationship": name, "object_mapping": {"expression": source}}


def test_star_sources_require_unique_declared_connection_and_keep_main_identity():
    main = dataset("customers", fields=[field("code", "customer_code")])
    side = dataset(
        "details", fields=[field("code", "customer_ref"), field("name", "customer_name")]
    )
    cm = mapped_concept(
        "customer", "customers.code", [property_mapping("name", "details.name")]
    )
    mapping = ontology_map([main, side], concepts=[cm])
    mapping["semantic_model"]["relationships"] = [
        {
            "name": "details_customer",
            "from": "details",
            "to": "customers",
            "from_columns": ["code"],
            "to_columns": ["code"],
        }
    ]
    data = document(
        entity(
            "customer",
            identify_by=["code"],
            relationships=[rel("code", "String"), rel("name", "String")],
        ),
        ontology_mappings=[mapping],
    )
    result = run(data)
    bound = result.model.mappings[0]
    assert [s.key_columns for s in bound.sources] == [["customer_code"], ["customer_ref"]]
    assert bound.fields["name"].source_id == "side_1"
    mapping["semantic_model"]["relationships"] = []
    result = run(data)
    assert len(result.model.mappings[0].sources) == 1
    assert "name" not in result.model.mappings[0].fields
    assert issues(result, "RT-43", "dropped")


def test_child_mapping_does_not_override_bound_parent():
    data = document(
        entity("customer", identify_by=["code"], relationships=[rel("code", "String")]),
        entity("vip", extends=["customer"]),
        ontology_mappings=[
            ontology_map(
                [dataset("customers"), dataset("vips")],
                concepts=[
                    mapped_concept("customer", "customers.code"),
                    mapped_concept("vip", "vips.code"),
                ],
            )
        ],
    )
    result = run(data)
    assert len(result.model.datasets) == 2 and len(result.model.mappings) == 1
    assert issues(result, "RT-65", "dropped")


def metric_document(formulas, second=False):
    datasets = [
        dataset(
            "sales",
            fields=[
                field("amount", "raw_amount"),
                field("code", "raw_code"),
                field("status", "raw_status"),
            ],
        )
    ]
    if second:
        datasets.append(
            dataset("returns", fields=[field("amount", "raw_amount")], primary_key=[])
        )
    metrics = [
        {"name": name, "expression": expression(formula), "datatype": "Decimal"}
        for name, formula in formulas
    ]
    return document(
        entity("customer"), ontology_mappings=[ontology_map(datasets, metrics=metrics)]
    )


@pytest.mark.parametrize(
    "formula,aggregation,filtered",
    [
        ("SUM(sales.amount)", "sum", False),
        ("MEDIAN(sales.amount)", "median", False),
        ("COUNT(DISTINCT sales.code)", "count_distinct", False),
        ("SUM(CASE WHEN sales.status = 'done' THEN sales.amount END)", "sum", True),
        (
            "COUNT(DISTINCT CASE WHEN sales.status <> 'cancelled' THEN sales.code END)",
            "count_distinct",
            True,
        ),
        ("COUNT(CASE WHEN sales.code IS NULL THEN 1 ELSE 1 END)", "count", False),
        (
            "COUNT(CASE WHEN sales.status = 'done' THEN CASE WHEN sales.code IS NULL THEN 1 ELSE 1 END END)",
            "count",
            True,
        ),
    ],
)
def test_fixed_metric_shapes_keep_column_and_filter_semantics(
    formula, aggregation, filtered
):
    result = run(metric_document([("total", formula)]))
    assert len(result.model.metrics) == 1
    metric = result.model.metrics[0]
    assert isinstance(metric, SimpleMetric) and metric.aggregation == aggregation
    assert bool(metric.filters) == filtered
    if aggregation == "count":
        assert metric.measure is None
    else:
        assert metric.measure.column in {"raw_amount", "raw_code"}


@pytest.mark.parametrize(
    "formula",
    [
        "COUNT(sales.amount)",
        "COUNT(CASE WHEN sales.status='done' THEN sales.amount END)",
        "SUM(CASE WHEN sales.status='done' THEN sales.amount ELSE 0 END)",
        "COUNT(DISTINCT sales.status || '::' || sales.code)",
        "SUM(CASE WHEN sales.status='done' OR sales.status='new' THEN sales.amount END)",
    ],
)
def test_non_fixed_algorithms_remain_one_expression_metric(formula):
    result = run(metric_document([("total", formula)]))
    assert len(result.model.metrics) == 1 and isinstance(
        result.model.metrics[0], ExpressionMetric
    )
    assert "raw_" in result.model.metrics[0].expression
    if "::" in formula:
        assert "'::'" in result.model.metrics[0].expression


def test_nullable_count_result_is_one_while_row_counter_is_two():
    result = run(
        metric_document(
            [
                ("nonnull", "COUNT(sales.amount)"),
                ("rows", "COUNT(CASE WHEN sales.amount IS NULL THEN 1 ELSE 1 END)"),
            ]
        )
    )
    with sqlite3.connect(":memory:") as db:
        db.executescript(
            "CREATE TABLE fiction_sales(raw_amount REAL); INSERT INTO fiction_sales VALUES(NULL),(10);"
        )
        count = db.execute(
            "SELECT " + result.model.metrics[0].expression + " FROM fiction_sales AS sales"
        ).fetchone()[0]
        assert count == 1
    assert isinstance(result.model.metrics[1], SimpleMetric)
    assert result.model.metrics[1].aggregation == "count"


def test_ratio_reuses_only_declared_components_even_when_declared_after_ratio():
    data = metric_document(
        [
            (
                "fraction",
                "CAST(SUM(sales.amount) AS DOUBLE) / NULLIF(COUNT(DISTINCT sales.code), 0)",
            ),
            ("amount", "SUM(sales.amount)"),
            ("customers", "COUNT(DISTINCT sales.code)"),
        ]
    )
    result = run(data)
    ratio = result.model.metrics[0]
    assert isinstance(ratio, RatioMetric)
    assert (
        ratio.numerator_id == result.model.metrics[1].id
        and ratio.denominator_id == result.model.metrics[2].id
    )
    data["ontology_mappings"][0]["semantic_model"]["metrics"].pop()
    result = run(data)
    assert len(result.model.metrics) == 2 and isinstance(
        result.model.metrics[0], ExpressionMetric
    )


@pytest.mark.parametrize(
    "formula",
    [
        "SUM(sales.amount) + SUM(returns.amount)",
        "(SELECT SUM(sales.amount) FROM sales)",
        "SUM(sales.amount) OVER ()",
    ],
)
def test_cross_dataset_and_query_scope_metrics_do_not_enter_core(formula):
    result = run(
        metric_document(
            [("unsupported", formula), ("valid", "SUM(sales.amount)")], second=True
        )
    )
    assert [m.name for m in result.model.metrics] == ["valid"]
    issue = issues(result, "RT-69", "error")[0]
    assert issue.completion_status == "available" and not issue.target_element_ids
    assert formula in issue.original


def test_bare_count_requires_explicit_dataset_choice():
    result = run(metric_document([("rows", "COUNT(*)")]))
    assert result.model.metrics == []
    assert any(
        i.completion_status == "available" and "选择数据集" in i.message
        for i in result.report.issues
    )


@pytest.mark.parametrize("name", ["library-lending", "storybook-lending"])
def test_original_ab_fixtures_are_not_preprocessed_and_return_deterministic_valid_subgraphs(
    name,
):
    raw = (FIXTURES / "ossie_synthetic" / (name + ".ossie.json")).read_bytes()
    value = json.loads(raw)
    result = OssieAdapter().import_document(raw, CTX)
    validate_core_graph(result.model)
    assert result.model.object_types
    if name == "library-lending":
        assert result.model.datasets and result.model.metrics
    else:
        assert not result.model.datasets and not result.model.metrics
    assert len(result.model.object_types) >= sum(
        c["type"] == "EntityType" for c in value["ontology"]
    )
    assert len(result.model.datasets) == sum(
        len(m["semantic_model"]["datasets"]) for m in value.get("ontology_mappings", [])
    )
    assert result.report == OssieAdapter().import_document(raw, CTX).report
    if name == "library-lending":
        assert issues(result, "RT-56") and issues(result, "RT-43")
    else:
        assert issues(result, "RT-27") and issues(result, "RT-28", "error")
    assert result.report.counts["converted"] > 0 and result.report.counts["dropped"] > 0


def test_composite_direct_join_reorders_source_columns_to_target_key():
    customer = entity(
        "customer",
        identify_by=["tenant", "code"],
        relationships=[rel("tenant", "String"), rel("code", "String")],
    )
    order = entity(
        "order",
        identify_by=["code"],
        relationships=[
            rel("code", "String"),
            rel("tenant_ref", "String"),
            rel("customer_ref", "String"),
            rel("buyer", "customer", source="order", multiplicity="ManyToOne"),
        ],
    )
    customers = dataset(
        "customers", fields=[field("tenant"), field("code")], primary_key=["tenant", "code"]
    )
    orders = dataset(
        "orders", fields=[field("code"), field("tenant_ref"), field("customer_ref")]
    )
    customer_map = {
        "concept": "customer",
        "object_mappings": [
            {
                "referent_mappings": [
                    {"relationship": "tenant", "expression": "customers.tenant"},
                    {"relationship": "code", "expression": "customers.code"},
                ]
            }
        ],
    }
    buyer = {
        "relationship": "buyer",
        "object_mapping": {
            "concept": "customer",
            "referent_mappings": [
                {"relationship": "code", "expression": "orders.customer_ref"},
                {"relationship": "tenant", "expression": "orders.tenant_ref"},
            ],
        },
    }
    order_map = mapped_concept(
        "order",
        "orders.code",
        [
            property_mapping("tenant_ref", "orders.tenant_ref"),
            property_mapping("customer_ref", "orders.customer_ref"),
            buyer,
        ],
    )
    mapping = ontology_map([orders, customers], concepts=[order_map, customer_map])
    mapping["semantic_model"]["relationships"] = [
        {
            "name": "buyer_fk",
            "from": "orders",
            "to": "customers",
            "from_columns": ["customer_ref", "tenant_ref"],
            "to_columns": ["code", "tenant"],
        }
    ]
    result = run(document(order, customer, ontology_mappings=[mapping]))
    link = result.model.link_types[0]
    assert link.data_join is not None and link.data_join.kind == "direct"
    index = {p.id: p.name for p in result.model.properties}
    assert [index[i] for i in link.data_join.source_property_ids] == [
        "tenant_ref",
        "customer_ref",
    ]
    assert [index[i] for i in link.data_join.target_property_ids] == ["tenant", "code"]


def test_mapping_table_with_two_endpoint_keys_and_no_fake_uniqueness():
    customer = entity(
        "customer",
        identify_by=["code"],
        relationships=[rel("code", "String"), rel("products", "product")],
    )
    product = entity("product", identify_by=["code"], relationships=[rel("code", "String")])
    cm = mapped_concept("customer", "customers.code")
    cm["link_mappings"].append(
        {
            "object_mapping": {"expression": "purchases.customer_ref"},
            "children": [
                {
                    "relationship": "products",
                    "object_mapping": {
                        "concept": "product",
                        "expression": "purchases.product_ref",
                    },
                }
            ],
        }
    )
    mapping = ontology_map(
        [
            dataset("customers"),
            dataset("products"),
            dataset(
                "purchases",
                fields=[field("customer_ref"), field("product_ref")],
                primary_key=[],
            ),
        ],
        concepts=[cm, mapped_concept("product", "products.code")],
    )
    mapping["semantic_model"]["relationships"] = [
        {
            "name": "customer_fk",
            "from": "purchases",
            "to": "customers",
            "from_columns": ["customer_ref"],
            "to_columns": ["code"],
        },
        {
            "name": "product_fk",
            "from": "purchases",
            "to": "products",
            "from_columns": ["product_ref"],
            "to_columns": ["code"],
        },
    ]
    result = run(document(customer, product, ontology_mappings=[mapping]))
    join = result.model.link_types[0].data_join
    assert join is not None and join.kind == "mapping_table"
    assert join.source_columns == ["customer_ref"] and join.target_columns == [
        "product_ref"
    ]
    assert join.source_key.kind == "mapping_key" and join.target_key.kind == "mapping_key"
    assert len(result.model.object_types) == 2


def test_parallel_links_are_bound_by_exact_foreign_key_fields():
    customer = entity(
        "customer", identify_by=["code"], relationships=[rel("code", "String")]
    )
    order = entity(
        "order",
        identify_by=["code"],
        relationships=[
            rel("code", "String"),
            rel("billing_code", "String"),
            rel("shipping_code", "String"),
            rel("billing", "customer", source="order", multiplicity="ManyToOne"),
            rel("shipping", "customer", source="order", multiplicity="ManyToOne"),
        ],
    )
    children = [
        property_mapping("billing_code", "orders.billing_code"),
        property_mapping("shipping_code", "orders.shipping_code"),
        {
            "relationship": "billing",
            "object_mapping": {"concept": "customer", "expression": "orders.billing_code"},
        },
        {
            "relationship": "shipping",
            "object_mapping": {"concept": "customer", "expression": "orders.shipping_code"},
        },
    ]
    mapping = ontology_map(
        [
            dataset("customers"),
            dataset(
                "orders",
                fields=[field("code"), field("billing_code"), field("shipping_code")],
            ),
        ],
        concepts=[
            mapped_concept("customer", "customers.code"),
            mapped_concept("order", "orders.code", children),
        ],
    )
    mapping["semantic_model"]["relationships"] = [
        {
            "name": name,
            "from": "orders",
            "to": "customers",
            "from_columns": [name + "_code"],
            "to_columns": ["code"],
        }
        for name in ["billing", "shipping"]
    ]
    result = run(document(customer, order, ontology_mappings=[mapping]))
    bindings = [link.data_join for link in result.model.link_types]
    assert all(b and b.kind == "direct" for b in bindings)
    assert bindings[0].source_property_ids != bindings[1].source_property_ids


def test_deterministic_names_and_ids_use_original_source_scope():
    data = document(
        entity(
            "sales-order",
            relationships=[rel("order-code", "String")],
            identify_by=["order-code"],
        )
    )
    first = run(data)
    second = run(data)
    assert first.model == second.model and first.report == second.report
    assert first.model.object_types[0].name == "sales_order"
    assert first.model.properties[0].name == "order_code"
    assert issues(first, "RT-12", "converted")
    changed = copy.deepcopy(data)
    changed["description"] = "另一个输入身份"
    assert run(changed).report.content_sha256 != first.report.content_sha256
    assert run(changed).model.object_types[0].id == first.model.object_types[0].id


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "core1_ossie").glob("*.json")), ids=lambda p: p.stem
)
def test_directed_source_fixtures_for_examples_03_06_07(path):
    result = run(json.loads(path.read_text()))
    assert result.model.object_types and result.model.properties
    if path.stem.startswith("03"):
        assert len(result.model.object_types) == 3 and len(result.model.link_types) == 2
    elif path.stem.startswith("06"):
        assert len(result.model.object_types[1].derived_by) == 2
        assert result.model.object_types[1].derived_by[0].kind == "simple"
    else:
        assert result.model.material_objects == []
        assert result.model.properties[0].value_kind == "boolean"


def test_nary_rule_binds_each_role_to_generated_properties_without_touching_literals():
    data = document(
        entity(
            "supplier",
            identify_by=["code"],
            relationships=[
                rel("code", "String"),
                {
                    "name": "supply",
                    "roles": [
                        {"concept": "part"},
                        {"concept": "Integer", "name": "quantity"},
                    ],
                    "multiplicity": "ManyToOne",
                    "verbalizes": ["{supplier} supplies {part} {Integer:quantity}"],
                    "requires": ["quantity > 0 AND supplier.code <> 'supplier.code'"],
                },
            ],
        ),
        entity("part", identify_by=["code"], relationships=[rel("code", "String")]),
    )
    result = run(data)
    obj = next(o for o in result.model.object_types if o.name == "supplier_supply")
    rule = next(r for r in result.model.rules if r.owner_id == obj.id)
    assert "supplier_supply.quantity > 0" in rule.expression
    assert "'supplier.code'" in rule.expression
    assert "supplier_supply.supplier_code" in rule.expression


def test_duplicate_source_datasets_do_not_resolve_to_the_first_occurrence():
    first = dataset("sales", fields=[field("amount")], primary_key=[])
    second = copy.deepcopy(first)
    second["source"] = "another_sales"
    result = run(
        document(
            entity("customer"),
            ontology_mappings=[
                ontology_map(
                    [first, second],
                    metrics=[
                        {"name": "total", "expression": expression("SUM(sales.amount)")}
                    ],
                )
            ],
        )
    )
    assert not result.model.datasets and not result.model.metrics
    assert any("重复" in i.message for i in result.report.issues)


def test_ambiguous_self_role_is_invalid_without_dropping_unrelated_property():
    result = run(
        document(
            entity(
                "customer", relationships=[rel("code", "String"), rel("parent", "customer")]
            )
        )
    )
    assert not result.model.link_types
    assert len(result.model.properties) == 1
    assert any(
        "角色名有歧义" in i.message and i.outcome == "error" for i in result.report.issues
    )


def test_source_cannot_hide_a_second_statement():
    result = run(
        document(
            entity("customer"),
            ontology_mappings=[
                ontology_map(
                    [dataset("sales", source="fiction_sales; DROP TABLE fiction_sales")]
                )
            ],
        )
    )
    assert not result.model.datasets and issues(result, "RT-63", "error")


def test_boolean_case_is_not_mistaken_for_the_exact_integer_row_count_form():
    result = run(
        metric_document(
            [("rows", "COUNT(CASE WHEN sales.code IS NULL THEN TRUE ELSE TRUE END)")]
        )
    )
    assert len(result.model.metrics) == 1 and isinstance(
        result.model.metrics[0], ExpressionMetric
    )


def test_oversized_definition_is_local_error_with_valid_dependencies_retained():
    data = document(
        entity("too_long", description="x" * 8001),
        entity(
            "valid",
            relationships=[
                rel("code", "String"),
                rel("bad", "String", description="x" * 8001),
            ],
        ),
    )
    result = run(data)
    assert [o.name for o in result.model.object_types] == ["valid"]
    assert [p.name for p in result.model.properties] == ["code"]
    assert result.report.counts["error"] == 2


def test_official_format_validation_is_separate_from_mechanical_translation():
    value = document(entity("customer", relationships=[rel("code", "String")]))
    assert OssieAdapter().validate_document(json.dumps(value).encode()) == []
    value["ontology"][0]["extends"] = ["String"]
    assert any(
        "INHERITANCE_TYPE_MISMATCH" in issue.message
        for issue in OssieAdapter().validate_document(json.dumps(value).encode())
    )


def test_unique_non_primary_property_can_be_a_direct_join_target():
    customer = entity(
        "customer",
        identify_by=["code"],
        relationships=[
            rel("code", "String"),
            rel("email", "String", multiplicity="ManyToOne"),
        ],
    )
    order = entity(
        "order",
        identify_by=["code"],
        relationships=[
            rel("code", "String"),
            rel("buyer_email", "String"),
            rel("buyer", "customer", source="order", multiplicity="ManyToOne"),
        ],
    )
    customers = dataset(
        "customers", fields=[field("code"), field("email")], unique_keys=[["email"]]
    )
    orders = dataset("orders", fields=[field("code"), field("buyer_email")])
    om = mapped_concept(
        "order",
        "orders.code",
        [
            property_mapping("buyer_email", "orders.buyer_email"),
            {
                "relationship": "buyer",
                "object_mapping": {
                    "concept": "customer",
                    "expression": "orders.buyer_email",
                },
            },
        ],
    )
    cm = mapped_concept(
        "customer", "customers.code", [property_mapping("email", "customers.email")]
    )
    mapping = ontology_map([customers, orders], concepts=[cm, om])
    mapping["semantic_model"]["relationships"] = [
        {
            "name": "buyer_email_fk",
            "from": "orders",
            "to": "customers",
            "from_columns": ["buyer_email"],
            "to_columns": ["email"],
        }
    ]
    result = run(document(customer, order, ontology_mappings=[mapping]))
    email = next(p for p in result.model.properties if p.name == "email")
    assert email.unique and not email.identifier
    join = result.model.link_types[0].data_join
    assert join is not None and join.kind == "direct"
    assert join.target_property_ids == [email.id]
    customers["unique_keys"] = [["code", "email"]]
    result = run(document(customer, order, ontology_mappings=[mapping]))
    email = next(p for p in result.model.properties if p.name == "email")
    assert not email.unique
    assert result.model.link_types[0].data_join is None


@pytest.mark.parametrize("case", OSSIE_IMPORT_CASES, ids=lambda c: c.source)
def test_reviewed_source_baselines_and_required_translation_rules(case):
    result = OssieAdapter().import_document((FIXTURES / case.source).read_bytes(), CTX)
    assert {key: len(getattr(result.model, key)) for key in case.counts} == case.counts
    assert case.rules <= {issue.rule_id for issue in result.report.issues}
    assert not result.model.material_objects
    validate_core_graph(result.model)


def test_conflicting_bindings_for_one_business_link_are_not_resolved_by_file_order():
    customer = entity(
        "customer", identify_by=["code"], relationships=[rel("code", "String")]
    )
    order = entity(
        "order",
        identify_by=["code"],
        relationships=[
            rel("code", "String"),
            rel("billing_code", "String"),
            rel("shipping_code", "String"),
            rel("buyer", "customer", source="order", multiplicity="ManyToOne"),
        ],
    )
    children = [
        property_mapping(name + "_code", "orders." + name + "_code")
        for name in ["billing", "shipping"]
    ]
    children += [
        {
            "relationship": "buyer",
            "object_mapping": {
                "concept": "customer",
                "expression": "orders." + name + "_code",
            },
        }
        for name in ["billing", "shipping"]
    ]
    mapping = ontology_map(
        [
            dataset("customers"),
            dataset(
                "orders",
                fields=[field("code"), field("billing_code"), field("shipping_code")],
            ),
        ],
        concepts=[
            mapped_concept("customer", "customers.code"),
            mapped_concept("order", "orders.code", children),
        ],
    )
    mapping["semantic_model"]["relationships"] = [
        {
            "name": name,
            "from": "orders",
            "to": "customers",
            "from_columns": [name + "_code"],
            "to_columns": ["code"],
        }
        for name in ["billing", "shipping"]
    ]
    data = document(customer, order, ontology_mappings=[mapping])
    result = run(data)
    assert result.model.link_types[0].data_join is None
    assert len(issues(result, "RT-53", "dropped")) >= 2
    mapping["concept_mappings"][1]["link_mappings"][0]["children"].reverse()
    assert run(data).model.link_types[0].data_join is None


def test_conflicting_object_populations_across_maps_are_not_silently_unioned_or_selected():
    customer = entity(
        "customer", identify_by=["code"], relationships=[rel("code", "String")]
    )
    one = ontology_map(
        [dataset("customers")], concepts=[mapped_concept("customer", "customers.code")]
    )
    two = copy.deepcopy(one)
    two["name"] = "another_map"
    result = run(document(customer, ontology_mappings=[one, two]))
    assert len(result.model.datasets) == 2
    assert not result.model.mappings
    assert len(issues(result, "RT-43", "dropped")) == 2


def test_duplicate_metric_names_drop_both_definitions_and_keep_independent_metrics():
    result = run(
        metric_document(
            [
                ("total", "SUM(sales.amount)"),
                ("total", "COUNT(DISTINCT sales.code)"),
                ("valid", "MAX(sales.amount)"),
            ]
        )
    )
    assert [m.name for m in result.model.metrics] == ["valid"]
    assert (
        len(
            [
                i
                for i in result.report.issues
                if i.construct == "Metric" and i.outcome == "error"
            ]
        )
        == 2
    )
