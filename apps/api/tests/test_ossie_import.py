import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ontofoundry_api.domain.models import (
    AttributeDefinition,
    LinkTypeDefinition,
    Multiplicity,
    ObjectTypeDefinition,
    OntologyDraft,
    ValueKind,
)
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.importer import OssieImportError, import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID, build_demo_draft

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"


def demo_document():
    return compile_ossie(
        build_demo_draft(),
        ontology_name="manufacturing_supply_chain",
        ontology_description="制造供应链",
    )


def foreign_document():
    """A file written outside OntoFoundry: inheritance, n-ary roles, expressions."""
    return {
        "version": "0.2.0.dev0",
        "name": "crm",
        "description": "Customer model",
        "requires": ["EXISTS (customer)"],
        "ontology": [
            {
                "concept": "party",
                "type": "EntityType",
                "description": "A party",
                "identify_by": ["party_code"],
                "relationships": [
                    {
                        "name": "party_code",
                        "roles": [{"concept": "party_code_value"}],
                        "verbalizes": ["{party} code {party_code_value}"],
                        "multiplicity": "OneToOne",
                    }
                ],
            },
            {
                "concept": "customer",
                "type": "EntityType",
                "extends": ["party"],
                "description": "买方",
                "requires": ["customer.status = 'active'"],
                "relationships": [
                    {
                        "name": "credit_limit",
                        "roles": [{"concept": "Decimal"}],
                        "verbalizes": ["{customer} limit {Decimal}"],
                        "multiplicity": "ManyToOne",
                    },
                    {
                        "name": "sold_to",
                        "roles": [
                            {"concept": "order"},
                            {"concept": "party", "name": "broker"},
                        ],
                        "verbalizes": ["{customer} sold {order} via {party:broker}"],
                    },
                    {
                        "name": "anything",
                        "roles": [{"concept": "Any"}],
                        "verbalizes": ["{customer} touches {Any}"],
                    },
                ],
            },
            {
                "concept": "order",
                "type": "EntityType",
                "description": "订单",
                "identify_by": ["placed_by"],
                "relationships": [
                    {
                        "name": "placed_by",
                        "roles": [{"concept": "customer"}],
                        "verbalizes": ["{order} placed by {customer}"],
                        "multiplicity": "ManyToOne",
                        "derived_by": ["SELECT 1"],
                    },
                    {
                        "name": "cancelled",
                        "roles": [],
                        "verbalizes": ["{order} is cancelled"],
                    },
                ],
            },
            {
                "concept": "party_code_value",
                "type": "ValueType",
                "extends": ["strict_code"],
            },
            {"concept": "strict_code", "type": "ValueType", "extends": ["String"]},
        ],
        "ontology_mappings": [
            {
                "semantic_model": {
                    "name": "crm_logical",
                    "datasets": [{"name": "customers", "source": "public.customers"}],
                },
                "concept_mappings": [{"concept": "customer"}],
            }
        ],
    }


def test_export_then_import_restores_the_same_model():
    draft = build_demo_draft()
    payload, report = import_ossie(
        demo_document(), workspace_id=str(draft.workspace_id), mode="replace"
    )
    imported = OntologyDraft.model_validate(payload)

    def object_shape(model):
        return {
            item.technical_name: (
                item.name,
                item.description,
                sorted(item.tags),
                {
                    a.technical_name: (a.name, a.value_kind, a.required, a.identifier)
                    for a in item.attributes
                },
            )
            for item in model.object_types
        }

    def link_shape(model):
        names = {item.id: item.technical_name for item in model.object_types}
        return {
            item.technical_name: (
                item.name,
                item.multiplicity,
                names[item.source_type_id],
                names[item.target_type_id],
                sorted(item.tags),
            )
            for item in model.link_types
        }

    assert object_shape(imported) == object_shape(draft)
    assert link_shape(imported) == link_shape(draft)
    assert report["skipped"] == []
    # Importing the same file twice gives the same identifiers.
    again, _ = import_ossie(
        demo_document(), workspace_id=str(draft.workspace_id), mode="replace"
    )
    assert again == payload


def test_imported_model_still_compiles_and_validates():
    draft = build_demo_draft()
    payload, _ = import_ossie(
        demo_document(), workspace_id=str(draft.workspace_id), mode="replace"
    )
    report = validate_ossie(
        compile_ossie(
            OntologyDraft.model_validate(payload),
            ontology_name="manufacturing_supply_chain",
            ontology_description="制造供应链",
        )
    )
    assert report["publishable"] is True


def test_foreign_file_keeps_inheritance_identifiers_and_expressions():
    payload, report = import_ossie(
        foreign_document(), workspace_id=DEMO_WORKSPACE_ID, mode="replace"
    )
    model = OntologyDraft.model_validate(payload)
    by_key = {item.technical_name: item for item in model.object_types}
    customer, order, party = by_key["customer"], by_key["order"], by_key["party"]

    # extends is kept as inheritance, not copied into the child.
    assert customer.extends == [party.id]
    assert [a.technical_name for a in customer.attributes] == ["credit_limit"]
    assert [a.technical_name for a in model.effective_attributes(customer.id)] == [
        "credit_limit",
        "party_code",
    ]
    assert party.attributes[0].identifier is True
    assert party.attributes[0].value_kind == "string"

    # Expressions land on the concept and the relationship that carry them.
    assert model.requires == ["EXISTS (customer)"]
    assert customer.requires == ["customer.status = 'active'"]
    placed_by = next(i for i in model.link_types if i.technical_name == "placed_by")
    assert placed_by.derived_by == ["SELECT 1"]
    # An entity relationship can identify its concept, as Ossie allows.
    assert placed_by.identifier is True
    assert placed_by.verbalizes == ["{order} placed by {customer}"]
    assert order.attributes == []

    # A collapsed value concept is only reported when something is lost.
    assert any("party_code_value" in note for note in report["notes"])


def test_foreign_file_reports_only_what_it_cannot_represent():
    payload, report = import_ossie(
        foreign_document(), workspace_id=DEMO_WORKSPACE_ID, mode="replace"
    )
    model = OntologyDraft.model_validate(payload)
    reasons = {item["path"]: item["reason"] for item in report["skipped"]}

    assert "role" in reasons["customer.sold_to"]
    assert "role" in reasons["order.cancelled"]
    assert "Any" in reasons["customer.anything"]
    assert "dataset" in reasons["ontology_mappings[0].customer"]
    # Expressions and identifying relations are supported now, so they are gone
    # from the report.
    assert not [path for path in reasons if path.endswith("requires")]
    assert not [path for path in reasons if path.endswith("derived_by")]
    assert "order.identify_by[placed_by]" not in reasons
    assert [item.technical_name for item in model.link_types] == ["placed_by"]


def rich_draft():
    """A model that uses every Ossie construct the internal model now carries."""
    space = UUID(str(DEMO_WORKSPACE_ID))
    party = ObjectTypeDefinition(
        id=uuid4(),
        name="往来单位",
        technical_name="party",
        description="企业往来的单位",
        attributes=[
            AttributeDefinition(
                id=uuid4(),
                name="单位编号",
                technical_name="party_code",
                value_kind=ValueKind.STRING,
                identifier=True,
                required=True,
                requires=["party.party_code IS NOT NULL"],
            )
        ],
    )
    customer = ObjectTypeDefinition(
        id=uuid4(),
        name="客户",
        technical_name="customer",
        description="买方",
        extends=[party.id],
        requires=["EXISTS (customer.orders)"],
        tags=["销售"],
        attributes=[
            AttributeDefinition(
                id=uuid4(),
                name="信用额度",
                technical_name="credit_limit",
                value_kind=ValueKind.DECIMAL,
                verbalizes=["{customer}的信用额度上限是{Decimal}"],
            )
        ],
    )
    order = ObjectTypeDefinition(
        id=uuid4(),
        name="订单",
        technical_name="sales_order",
        attributes=[
            AttributeDefinition(
                id=uuid4(),
                name="行号",
                technical_name="line_no",
                value_kind=ValueKind.INTEGER,
                identifier=True,
            )
        ],
    )
    placed_by = LinkTypeDefinition(
        id=uuid4(),
        name="下单客户",
        technical_name="placed_by",
        source_type_id=order.id,
        target_type_id=customer.id,
        multiplicity=Multiplicity.MANY_TO_ONE,
        identifier=True,
        derived_by=["SELECT 1"],
        verbalizes=["{sales_order}由{customer}下单"],
    )
    # Same relationship name under a different concept: legal in Ossie, and now
    # legal here too because the name only has to be unique inside its concept.
    referred_by = LinkTypeDefinition(
        id=uuid4(),
        name="推荐人",
        technical_name="placed_by",
        source_type_id=customer.id,
        target_type_id=party.id,
        multiplicity=Multiplicity.MANY_TO_ONE,
    )
    return OntologyDraft(
        workspace_id=space,
        requires=["EXISTS (party)"],
        object_types=[party, customer, order],
        link_types=[placed_by, referred_by],
    )


def test_rich_model_survives_a_full_round_trip_and_stays_publishable():
    draft = rich_draft()
    document = compile_ossie(draft, ontology_name="crm", ontology_description="客户模型")
    assert validate_ossie(document)["publishable"] is True

    components = {item["concept"]: item for item in document["ontology"]}
    assert components["customer"]["extends"] == ["party"]
    assert components["sales_order"]["identify_by"] == ["line_no", "placed_by"]
    assert components["customer"]["requires"] == ["EXISTS (customer.orders)"]
    assert document["requires"] == ["EXISTS (party)"]

    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )
    imported = OntologyDraft.model_validate(payload)
    by_key = {item.technical_name: item for item in imported.object_types}

    assert report["skipped"] == []
    assert by_key["customer"].extends == [by_key["party"].id]
    assert by_key["customer"].requires == ["EXISTS (customer.orders)"]
    assert by_key["customer"].attributes[0].verbalizes == [
        "{customer}的信用额度上限是{Decimal}"
    ]
    assert imported.requires == ["EXISTS (party)"]
    order_link = next(
        item
        for item in imported.link_types
        if item.source_type_id == by_key["sales_order"].id
    )
    assert order_link.identifier is True
    assert order_link.derived_by == ["SELECT 1"]
    assert order_link.verbalizes == ["{sales_order}由{customer}下单"]
    # Both relationships keep the same technical name under different concepts.
    assert sorted(item.technical_name for item in imported.link_types) == [
        "placed_by",
        "placed_by",
    ]
    assert (
        validate_ossie(
            compile_ossie(imported, ontology_name="crm", ontology_description="客户模型")
        )["publishable"]
        is True
    )


def test_model_rejects_what_ossie_would_reject():
    draft = rich_draft()
    cycle = draft.model_dump(mode="json")
    cycle["object_types"][0]["extends"] = [cycle["object_types"][1]["id"]]
    with pytest.raises(ValidationError, match="循环"):
        OntologyDraft.model_validate(cycle)

    clash = draft.model_dump(mode="json")
    clash["object_types"][1]["attributes"][0]["technical_name"] = "party_code"
    with pytest.raises(ValidationError, match="技术名冲突"):
        OntologyDraft.model_validate(clash)

    loose = draft.model_dump(mode="json")
    loose["link_types"][0]["multiplicity"] = "many_to_many"
    with pytest.raises(ValidationError, match="标识"):
        OntologyDraft.model_validate(loose)


def test_readings_and_their_value_concepts_survive_verbatim():
    """No placeholder rewriting: the concepts a reading names are kept as well."""
    payload, _ = import_ossie(
        foreign_document(), workspace_id=DEMO_WORKSPACE_ID, mode="replace"
    )
    model = OntologyDraft.model_validate(payload)
    party = next(i for i in model.object_types if i.technical_name == "party")
    code = party.attributes[0]

    assert code.value_concept == "party_code_value"
    assert code.verbalizes == ["{party} code {party_code_value}"]

    document = compile_ossie(model, ontology_name="crm", ontology_description="")
    concepts = {item["concept"]: item for item in document["ontology"]}
    relationship = concepts["party"]["relationships"][0]

    # The value concept is written back under its own name, so the reading the
    # file shipped still points at a real role of this relationship.
    assert relationship["roles"] == [{"concept": "party_code_value"}]
    assert relationship["verbalizes"] == ["{party} code {party_code_value}"]
    assert concepts["party_code_value"]["extends"] == ["String"]
    assert validate_ossie(document)["publishable"] is True


def test_one_value_concept_shared_by_several_attributes_stays_one_concept():
    document = {
        "version": "0.2.0.dev0",
        "name": "codes",
        "ontology": [
            {"concept": "sku", "type": "ValueType", "extends": ["String"]},
            {
                "concept": "product",
                "type": "EntityType",
                "relationships": [
                    {
                        "name": "code",
                        "roles": [{"concept": "sku"}],
                        "verbalizes": ["{product} has {sku}"],
                        "multiplicity": "ManyToOne",
                    }
                ],
            },
            {
                "concept": "listing",
                "type": "EntityType",
                "relationships": [
                    {
                        "name": "code",
                        "roles": [{"concept": "sku"}],
                        "verbalizes": ["{listing} lists {sku}"],
                        "multiplicity": "ManyToOne",
                    }
                ],
            },
        ],
    }
    payload, report = import_ossie(document, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    model = OntologyDraft.model_validate(payload)

    assert [item.attributes[0].value_concept for item in model.object_types] == [
        "sku",
        "sku",
    ]
    assert report["skipped"] == []

    rewritten = compile_ossie(model, ontology_name="codes", ontology_description="")
    values = [item for item in rewritten["ontology"] if item["type"] == "ValueType"]
    assert [item["concept"] for item in values] == ["sku"]
    assert validate_ossie(rewritten)["publishable"] is True


def mapped_draft():
    """The demo model with two tables mapped and one relation joined."""
    draft = build_demo_draft()
    payload = draft.model_dump(mode="json")
    supplier = next(
        item for item in payload["object_types"] if item["technical_name"] == "supplier"
    )
    material = next(
        item for item in payload["object_types"] if item["technical_name"] == "material"
    )
    payload["mappings"] = [
        {
            "id": str(uuid4()),
            "type_id": supplier["id"],
            "connection_alias": "erp",
            "table_name": "suppliers",
            "schema_name": "public",
            "key_column": "code",
            "fields": {"supplier_code": "code", "supplier_name": "name"},
        },
        {
            "id": str(uuid4()),
            "type_id": material["id"],
            "connection_alias": "erp",
            "table_name": "materials",
            "schema_name": None,
            "key_column": "code",
            "fields": {"material_code": "code"},
        },
    ]
    for link in payload["link_types"]:
        if link["technical_name"] == "supplies":
            link["data_join"] = {
                "source_column": "code",
                "target_column": "supplier_code",
            }
    return OntologyDraft.model_validate(payload)


def test_data_mappings_travel_as_ontology_mappings_without_connections():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    assert validate_ossie(document)["publishable"] is True

    maps = document["ontology_mappings"]
    assert [item["name"] for item in maps] == ["erp"]
    datasets = {item["name"]: item for item in maps[0]["semantic_model"]["datasets"]}
    assert datasets["supplier"]["source"] == "public.suppliers"
    assert datasets["supplier"]["primary_key"] == ["code"]
    assert maps[0]["semantic_model"]["relationships"][0]["from_columns"] == ["code"]
    supplier_mapping = next(
        item for item in maps[0]["concept_mappings"] if item["concept"] == "supplier"
    )
    root = supplier_mapping["link_mappings"][0]
    assert "relationship" not in root
    assert root["object_mapping"]["expression"] == "supplier.code"
    assert {item["relationship"] for item in root["children"]} == {
        "supplier_code",
        "supplier_name",
        "supplies",
    }
    # No credentials, host or connection id anywhere in the published document.
    assert "connection" not in json.dumps(document).lower()

    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )
    imported = OntologyDraft.model_validate(payload)
    names = {item.id: item.technical_name for item in imported.object_types}
    shape = {
        names[item.type_id]: (
            item.connection_alias,
            item.schema_name,
            item.table_name,
            item.key_column,
            item.fields,
        )
        for item in imported.mappings
    }
    source_names = {item.id: item.technical_name for item in draft.object_types}
    original = {
        source_names[item.type_id]: (
            item.connection_alias,
            item.schema_name,
            item.table_name,
            item.key_column,
            item.fields,
        )
        for item in draft.mappings
    }

    assert shape == original
    assert report["skipped"] == []
    joins = {
        item.technical_name: item.data_join
        for item in imported.link_types
        if item.data_join
    }
    assert joins["supplies"].source_column == "code"
    assert joins["supplies"].target_column == "supplier_code"


def test_computed_mapping_expressions_are_reported_not_guessed():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    mapping = document["ontology_mappings"][0]["concept_mappings"][0]
    child = mapping["link_mappings"][0]["children"][0]
    child["object_mapping"]["expression"] = "UPPER(code)"
    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )
    imported = OntologyDraft.model_validate(payload)
    dropped = child["relationship"]

    assert any("单列表达式" in item["reason"] for item in report["skipped"])
    assert all(
        dropped not in item.fields
        for item in imported.mappings
        if item.type_id
        == next(
            entry.id
            for entry in imported.object_types
            if entry.technical_name == mapping["concept"]
        )
    )


def test_declared_computed_field_is_not_guessed_as_a_physical_column():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    group = document["ontology_mappings"][0]
    mapping = group["concept_mappings"][0]
    dataset = next(
        item
        for item in group["semantic_model"]["datasets"]
        if item["name"] == mapping["concept"]
    )
    dataset["fields"].append(
        {
            "name": "calculated",
            "expression": {
                "dialects": [{"dialect": "ANSI_SQL", "expression": "UPPER(code)"}]
            },
        }
    )
    child = mapping["link_mappings"][0]["children"][0]
    child["object_mapping"]["expression"] = f"{mapping['concept']}.calculated"

    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )
    imported = OntologyDraft.model_validate(payload)
    object_type = next(
        item for item in imported.object_types if item.technical_name == mapping["concept"]
    )
    data_mapping = next(
        item for item in imported.mappings if item.type_id == object_type.id
    )
    assert child["relationship"] not in data_mapping.fields
    assert any(
        item["path"].endswith(child["relationship"]) and "单列表达式" in item["reason"]
        for item in report["skipped"]
    )


def test_plain_logical_field_resolves_to_its_physical_column():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    group = document["ontology_mappings"][0]
    mapping = group["concept_mappings"][0]
    dataset = next(
        item
        for item in group["semantic_model"]["datasets"]
        if item["name"] == mapping["concept"]
    )
    child = mapping["link_mappings"][0]["children"][0]
    physical = child["object_mapping"]["expression"].split(".", 1)[1]
    dataset["fields"].append(
        {
            "name": "logical_field",
            "expression": {
                "dialects": [
                    {
                        "dialect": "ANSI_SQL",
                        "expression": f"{mapping['concept']}.{physical}",
                    }
                ]
            },
        }
    )
    child["object_mapping"]["expression"] = f"{mapping['concept']}.logical_field"

    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )
    imported = OntologyDraft.model_validate(payload)
    object_type = next(
        item for item in imported.object_types if item.technical_name == mapping["concept"]
    )
    data_mapping = next(
        item for item in imported.mappings if item.type_id == object_type.id
    )
    assert data_mapping.fields[child["relationship"]] == physical
    assert report["skipped"] == []


def test_merge_keeps_existing_model_instances_and_mappings():
    draft = build_demo_draft()
    document = foreign_document()
    payload, report = import_ossie(
        document,
        workspace_id=str(draft.workspace_id),
        base=draft.model_dump(mode="json"),
        mode="merge",
    )
    merged = OntologyDraft.model_validate(payload)
    keys = {item.technical_name for item in merged.object_types}

    assert {"supplier", "material", "customer", "order"} <= keys
    assert len(merged.objects) == len(draft.objects)
    assert len(merged.mappings) == len(draft.mappings)
    assert report["counts"]["objects_added"] == 3
    assert report["counts"]["objects_updated"] == 0


def test_merge_updates_matching_types_without_renaming_them():
    draft = build_demo_draft()
    document = demo_document()
    for component in document["ontology"]:
        if component["concept"] == "material":
            component["description"] = "导入后的新说明"
            component["relationships"].append(
                {
                    "name": "shelf_life_days",
                    "description": "保质期天数",
                    "roles": [{"concept": "Integer"}],
                    "verbalizes": ["{material}的保质期是{Integer}"],
                    "multiplicity": "ManyToOne",
                }
            )
    document["ai_context"]["ontofoundry"]["display_names"]["material"] = "改名的物料"

    payload, report = import_ossie(
        document,
        workspace_id=str(draft.workspace_id),
        base=draft.model_dump(mode="json"),
        mode="merge",
    )
    merged = OntologyDraft.model_validate(payload)
    material = next(i for i in merged.object_types if i.technical_name == "material")
    original = next(i for i in draft.object_types if i.technical_name == "material")

    assert material.id == original.id
    assert material.name == "物料"  # local business name wins on update
    assert material.description == "导入后的新说明"
    assert [a.technical_name for a in material.attributes][-1] == "shelf_life_days"
    assert report["counts"]["objects_updated"] == 5
    assert report["counts"]["attributes_added"] == 1


def test_import_refuses_documents_that_are_not_valid_ossie():
    with pytest.raises(OssieImportError, match="OSSIE_VERSION_UNSUPPORTED"):
        import_ossie({"version": "9", "ontology": []}, workspace_id=DEMO_WORKSPACE_ID)
    with pytest.raises(OssieImportError):
        import_ossie(
            {"version": "0.2.0.dev0", "name": "x", "ontology": []},
            workspace_id=DEMO_WORKSPACE_ID,
        )
    with pytest.raises(OssieImportError, match="EntityType"):
        import_ossie(
            {
                "version": "0.2.0.dev0",
                "name": "only_values",
                "ontology": [
                    {"concept": "code", "type": "ValueType", "extends": ["String"]}
                ],
            },
            workspace_id=DEMO_WORKSPACE_ID,
        )


def v1_export(draft):
    """The layout extension v1 exported: attribute columns flat, no object root."""
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    document["ai_context"]["ontofoundry"]["version"] = "1"
    for entry in document["ontology_mappings"]:
        for mapping in entry["concept_mappings"]:
            if mapping.get("link_mappings"):
                mapping["link_mappings"] = mapping["link_mappings"][0]["children"]
    return document


def mapping_view(mappings):
    return sorted(
        (m["table_name"], m["key_column"], sorted(m["fields"].items()))
        for m in mappings
    )


def test_extension_v1_files_with_flat_mappings_still_import():
    draft = mapped_draft()
    payload, report = import_ossie(
        v1_export(draft), workspace_id=str(draft.workspace_id), mode="replace"
    )

    expected = draft.model_dump(mode="json")["mappings"]
    assert mapping_view(payload["mappings"]) == mapping_view(expected)
    assert report["skipped"] == []
    # Re-exporting the imported model writes the current tree layout.
    again = compile_ossie(
        OntologyDraft.model_validate(payload), ontology_name="mfg", ontology_description="制造"
    )
    assert again["ai_context"]["ontofoundry"]["version"] == "2"
    assert all(
        "relationship" not in root
        for entry in again["ontology_mappings"]
        for mapping in entry["concept_mappings"]
        for root in mapping.get("link_mappings") or []
    )


def test_ambiguous_mapping_trees_are_reported_not_rejected():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    mapping = document["ontology_mappings"][0]["concept_mappings"][0]
    root = mapping["link_mappings"][0]
    mapping["link_mappings"].append(json.loads(json.dumps(root)))
    root["children"].append(json.loads(json.dumps(root["children"][0])))
    root["children"].append({"object_mapping": {"expression": "x.y"}})

    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )

    expected = draft.model_dump(mode="json")["mappings"]
    assert mapping_view(payload["mappings"]) == mapping_view(expected)
    reasons = " ".join(item["reason"] for item in report["skipped"])
    assert "只导入第一个" in reasons
    assert "只保留第一个" in reasons
    assert "缺少 relationship" in reasons


def test_import_rejects_unknown_extension_versions():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    document["ai_context"]["ontofoundry"]["version"] = "9"

    with pytest.raises(OssieImportError, match="ONTOFOUNDRY_EXTENSION_VERSION_UNSUPPORTED"):
        import_ossie(document, workspace_id=str(draft.workspace_id), mode="replace")


def test_standard_tree_without_ontofoundry_extension_can_be_imported():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    del document["ai_context"]["ontofoundry"]

    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )
    assert len(payload["mappings"]) == len(draft.mappings)
    assert report["skipped"] == []


def test_import_endpoint_creates_a_reviewable_session_without_publishing(client):
    before = client.get(f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}/version")
    response = client.post(
        ROOT + "/imports/ossie",
        json={"document": foreign_document(), "mode": "merge"},
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["title"] == "导入 crm"
    assert body["import_report"]["counts"]["objects_added"] == 3
    assert body["validation"]["publishable"] is True
    assert {item["technical_name"] for item in body["draft"]["object_types"]} >= {
        "supplier",
        "customer",
    }
    # Nothing is published until the user publishes the session.
    after = client.get(f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}/version")
    assert after.json()["version"] == before.json()["version"]
    assert client.get(ROOT + "/sessions/" + body["id"]).json()["draft"] == body["draft"]


def test_import_endpoint_rejects_invalid_files(client):
    response = client.post(
        ROOT + "/imports/ossie",
        json={"document": {"version": "0.2.0.dev0", "name": "x"}, "mode": "merge"},
    )
    assert response.status_code == 422
    assert "导入失败" in response.json()["detail"]


def test_import_endpoint_accepts_v1_and_reports_unknown_extension_versions(client):
    draft = mapped_draft()
    response = client.post(
        ROOT + "/imports/ossie",
        json={"document": v1_export(draft), "mode": "replace"},
    )
    assert response.status_code == 201, response.text

    unknown = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    unknown["ai_context"]["ontofoundry"]["version"] = "9"
    response = client.post(
        ROOT + "/imports/ossie",
        json={"document": unknown, "mode": "replace"},
    )
    assert response.status_code == 422
    assert "ONTOFOUNDRY_EXTENSION_VERSION_UNSUPPORTED" in response.json()["detail"]


def test_relation_join_is_skipped_when_an_endpoint_has_no_data_mapping():
    """A real agent result where one concept ended up without a dataset.

    Joins used to be attached before mappings were read, so a relation whose
    endpoint had no table still got one — producing a draft that `OntologyDraft`
    itself rejects. Because the only producer of these documents is an agent,
    that rejection discarded a whole modeling run over one unmapped concept.
    The rest of the model is worth keeping; the missing join is worth saying.
    """
    document = json.loads(
        (
            Path(__file__).parent / "fixtures" / "agent_result_partial_mappings.json"
        ).read_text(encoding="utf-8")
    )["ontology"]

    draft, report = import_ossie(document, workspace_id=DEMO_WORKSPACE_ID, mode="replace")

    # The draft is valid — which is the whole point, since this document used to
    # raise out of the model layer.
    OntologyDraft.model_validate(draft)

    assert len(draft["object_types"]) == 4
    assert len(draft["mappings"]) == 3
    joined = [link for link in draft["link_types"] if link.get("data_join")]
    assert len(joined) == 1

    reasons = [item["reason"] for item in report["skipped"]]
    assert sum("order_item 没有数据映射" in reason for reason in reasons) == 2


def named_value_roles_document():
    return {
        "version": "0.2.0.dev0",
        "name": "governance",
        "description": "治理",
        "ontology": [
            {
                "concept": "arch_issue",
                "type": "EntityType",
                "identify_by": ["issue_key"],
                "relationships": [
                    {
                        "name": "issue_key",
                        "roles": [{"concept": "String", "name": "key_role"}],
                        "multiplicity": "ManyToOne",
                        "verbalizes": ["{arch_issue} 的编号是 {String:key_role}"],
                    },
                    {
                        "name": "issue_args",
                        "roles": [{"concept": "String", "name": "args_role"}],
                        "multiplicity": "ManyToOne",
                        "verbalizes": ["{arch_issue} 的参数是 {String:args_role}"],
                    },
                ],
            }
        ],
    }


def test_named_value_roles_and_stated_multiplicity_survive_round_trip():
    document = named_value_roles_document()
    payload, report = import_ossie(document, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    model = OntologyDraft.model_validate(payload)
    by_name = {item.technical_name: item for item in model.object_types[0].attributes}

    assert report["skipped"] == []
    assert by_name["issue_key"].value_concept == "String"
    assert by_name["issue_key"].multiplicity == Multiplicity.MANY_TO_ONE
    assert by_name["issue_key"].target_role_name == "key_role"
    assert by_name["issue_args"].target_role_name == "args_role"
    assert all(item.description == "" for item in by_name.values())

    rewritten = compile_ossie(
        model, ontology_name="governance", ontology_description="治理"
    )
    assert validate_ossie(rewritten)["publishable"] is True
    relationships = {
        item["name"]: item for item in rewritten["ontology"][0]["relationships"]
    }
    assert relationships == {
        item["name"]: item for item in document["ontology"][0]["relationships"]
    }
    assert "description" not in rewritten["ontology"][0]

    # Removing an imported reading regenerates one with the named placeholder.
    by_name["issue_args"].verbalizes = []
    generated = compile_ossie(
        model, ontology_name="governance", ontology_description="治理"
    )
    assert validate_ossie(generated)["publishable"] is True
    args = next(
        item
        for item in generated["ontology"][0]["relationships"]
        if item["name"] == "issue_args"
    )
    assert "{String:args_role}" in args["verbalizes"][0]


def test_imported_role_and_multiplicity_survive_publish_and_export(client):
    response = client.post(
        ROOT + "/imports/ossie",
        json={"document": named_value_roles_document(), "mode": "replace"},
    )
    assert response.status_code == 201, response.text
    session = response.json()
    published = client.post(
        ROOT + "/sessions/" + session["id"] + "/publish",
        json={"revision": session["revision"], "message": "值角色往返"},
    )
    assert published.status_code == 200, published.text
    version_id = published.json()["version"]["version_id"]

    snapshot = client.get(ROOT + "/published-snapshot").json()
    issue = next(
        item for item in snapshot["object_types"] if item["technical_name"] == "arch_issue"
    )
    key = next(
        item for item in issue["attributes"] if item["technical_name"] == "issue_key"
    )
    assert key["target_role_name"] == "key_role"
    assert key["multiplicity"] == "many_to_one"

    exported = client.get(
        f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}/versions/{version_id}/export"
    )
    assert exported.status_code == 200
    component = next(
        item for item in exported.json()["ontology"] if item["concept"] == "arch_issue"
    )
    key_relationship = next(
        item for item in component["relationships"] if item["name"] == "issue_key"
    )
    assert key_relationship["roles"] == [{"concept": "String", "name": "key_role"}]
    assert key_relationship["multiplicity"] == "ManyToOne"


def test_description_is_not_invented_or_removed_when_it_equals_a_name():
    document = named_value_roles_document()
    document["ontology"][0]["description"] = "arch_issue"
    document["ontology"][0]["relationships"][1]["description"] = "issue_args"
    payload, _ = import_ossie(document, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    rewritten = compile_ossie(
        OntologyDraft.model_validate(payload),
        ontology_name="governance",
        ontology_description="治理",
    )

    component = rewritten["ontology"][0]
    assert component["description"] == "arch_issue"
    args = next(item for item in component["relationships"] if item["name"] == "issue_args")
    assert args["description"] == "issue_args"
    assert "description" not in next(
        item for item in component["relationships"] if item["name"] == "issue_key"
    )


def test_editor_created_attribute_still_infers_identifier_multiplicity():
    payload, _ = import_ossie(
        named_value_roles_document(), workspace_id=DEMO_WORKSPACE_ID, mode="replace"
    )
    model = OntologyDraft.model_validate(payload)
    model.object_types[0].attributes[0].multiplicity = None
    rewritten = compile_ossie(
        model, ontology_name="governance", ontology_description="治理"
    )
    key = next(
        item
        for item in rewritten["ontology"][0]["relationships"]
        if item["name"] == "issue_key"
    )
    assert key["multiplicity"] == "OneToOne"


def test_attribute_rejects_cardinality_that_ossie_cannot_export():
    payload, _ = import_ossie(
        named_value_roles_document(), workspace_id=DEMO_WORKSPACE_ID, mode="replace"
    )
    payload["object_types"][0]["attributes"][0]["multiplicity"] = "many_to_many"
    with pytest.raises(ValidationError, match="属性的基数"):
        OntologyDraft.model_validate(payload)


def test_internal_draft_rejects_unknown_schema_version():
    payload = build_demo_draft().model_dump(mode="json")
    payload["schema_version"] = "2"
    with pytest.raises(ValidationError, match="schema_version"):
        OntologyDraft.model_validate(payload)


def test_value_concept_description_that_differs_is_reported():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    value = next(c for c in document["ontology"] if c.get("type") == "ValueType")
    value["description"] = "值概念自己的说明"

    _, report = import_ossie(document, workspace_id=str(draft.workspace_id), mode="replace")

    assert any(value["concept"] in note and "描述" in note for note in report["notes"])


V1_EXPORT = json.loads(
    (Path(__file__).parent / "fixtures" / "ossie_extension_v1_export.json").read_text(encoding="utf-8")
)


def test_frozen_extension_v1_export_imports_and_reexports_as_v2():
    """A file exported by the extension-v1 compiler (commit e3dc4a9), frozen."""
    expected = V1_EXPORT["draft"]
    payload, report = import_ossie(
        V1_EXPORT["ossie"], workspace_id=V1_EXPORT["workspace_id"], mode="replace"
    )

    assert mapping_view(payload["mappings"]) == mapping_view(expected["mappings"])
    assert {t["technical_name"] for t in payload["object_types"]} == {
        t["technical_name"] for t in expected["object_types"]
    }
    joins = {
        link["technical_name"]: link.get("data_join")
        for link in payload["link_types"]
        if link.get("data_join")
    }
    assert joins == {
        link["technical_name"]: link["data_join"]
        for link in expected["link_types"]
        if link.get("data_join")
    }
    assert report["skipped"] == []

    again = compile_ossie(
        OntologyDraft.model_validate(payload), ontology_name="mfg", ontology_description="制造"
    )
    assert again["ai_context"]["ontofoundry"]["version"] == "2"
    assert validate_ossie(again)["publishable"] is True


def test_second_mapping_root_is_skipped_not_merged():
    draft = mapped_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    mapping = document["ontology_mappings"][0]["concept_mappings"][0]
    first = mapping["link_mappings"][0]
    dataset = first["object_mapping"]["expression"].split(".")[0]
    mapping["link_mappings"].append(
        {
            "object_mapping": {"expression": f"{dataset}.other_key"},
            "children": [
                {
                    "relationship": first["children"][0]["relationship"],
                    "object_mapping": {"expression": f"{dataset}.other_column"},
                }
            ],
        }
    )

    payload, report = import_ossie(
        document, workspace_id=str(draft.workspace_id), mode="replace"
    )

    columns = {c for m in payload["mappings"] for c in [m["key_column"], *m["fields"].values()]}
    assert "other_key" not in columns and "other_column" not in columns
    assert any("只导入第一个" in item["reason"] for item in report["skipped"])


def test_current_extension_version_is_always_readable():
    from ontofoundry_api.ossie.compiler import EXTENSION_VERSION
    from ontofoundry_api.ossie.importer import READABLE_EXTENSION_VERSIONS

    assert EXTENSION_VERSION in READABLE_EXTENSION_VERSIONS
    assert "1" in READABLE_EXTENSION_VERSIONS
