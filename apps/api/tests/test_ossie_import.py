import pytest

from ontofoundry_api.domain.models import OntologyDraft
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


def test_foreign_file_reports_every_construct_it_cannot_represent():
    payload, report = import_ossie(
        foreign_document(), workspace_id=DEMO_WORKSPACE_ID, mode="replace"
    )
    model = OntologyDraft.model_validate(payload)
    by_key = {item.technical_name: item for item in model.object_types}
    reasons = {item["path"]: item["reason"] for item in report["skipped"]}

    # Inheritance is flattened, including the identifier it carries.
    customer = by_key["customer"]
    assert [a.technical_name for a in customer.attributes] == [
        "party_code",
        "credit_limit",
    ]
    assert customer.attributes[0].identifier is True
    assert customer.attributes[1].value_kind == "decimal"
    assert any("继承自 party" in note for note in report["notes"])

    # A ValueType chain collapses onto the built-in it extends, and says so.
    assert customer.attributes[0].value_kind == "string"
    assert any("party_code_value" in note for note in report["notes"])

    assert "role" in reasons["customer.sold_to"]
    assert "role" in reasons["order.cancelled"]
    assert "Any" in reasons["customer.anything"]
    assert "表达式" in reasons["ontology.requires"]
    assert "表达式" in reasons["customer.requires"]
    assert "表达式" in reasons["order.placed_by.derived_by"]
    assert "ontology_mappings" in reasons
    assert "标识" in reasons["order.identify_by[placed_by]"]
    assert [item.technical_name for item in model.link_types] == ["placed_by"]


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
    with pytest.raises(OssieImportError, match="Apache Ossie"):
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
