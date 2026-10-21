"""Relationship read projections follow effective bindings and both endpoints."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from core1_fixtures import example_draft

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.ontology_query import resource_items


def relationship_draft(kind="direct"):
    a, b, pa, pb, da, db, bridge, rel = [str(uuid4()) for _ in range(8)]
    join = {"kind": "direct", "source_property_ids": [pa], "target_property_ids": [pb]}
    if kind == "mapping_table":
        join = {
            "kind": "mapping_table",
            "dataset_id": bridge,
            "source_columns": ["a_id"],
            "target_columns": ["b_id"],
            "source_key": {"kind": "mapping_key"},
            "target_key": {"kind": "properties", "property_ids": [pb]},
        }
    return validate_core_graph(
        CoreDraft.model_validate(
            {
                "workspace_id": str(uuid4()),
                "object_types": [
                    {"id": i, "display_name": n, "name": t}
                    for i, n, t in [
                        (a, "星港订单", "starport_order"),
                        (b, "星港客户", "starport_customer"),
                    ]
                ],
                "properties": [
                    {
                        "id": p,
                        "owner_type_id": o,
                        "display_name": "编号",
                        "name": "number",
                        "value_kind": "string",
                        "unique": True,
                    }
                    for p, o in [(pa, a), (pb, b)]
                ],
                "datasets": [
                    {
                        "id": da,
                        "name": "fictional_orders",
                        "table_name": "fictional_orders",
                        "columns": [{"name": "id", "physical_type": "text"}],
                    },
                    {
                        "id": db,
                        "name": "fictional_customers",
                        "table_name": "fictional_customers",
                        "columns": [{"name": "id", "physical_type": "text"}],
                    },
                    {
                        "id": bridge,
                        "name": "fictional_pairs",
                        "table_name": "fictional_pairs",
                        "columns": [
                            {"name": n, "physical_type": "text"} for n in ("a_id", "b_id")
                        ],
                    },
                ],
                "mappings": [
                    {
                        "id": str(uuid4()),
                        "type_id": o,
                        "binding_mode": "independent",
                        "sources": [{"id": "main", "dataset_id": d, "key_columns": ["id"]}],
                        "fields": {
                            "number": {
                                "kind": "column",
                                "source_id": "main",
                                "column": "id",
                            }
                        },
                    }
                    for o, d in [(a, da), (b, db)]
                ],
                "link_types": [
                    {
                        "id": rel,
                        "name": "belongs_to",
                        "source_type_id": a,
                        "target_type_id": b,
                        "multiplicity": "many_to_one",
                        "data_join": join,
                    }
                ],
            }
        )
    )


def link_statuses(draft, **kwargs):
    items = resource_items(draft.model_dump(mode="json"), **kwargs)
    return [
        d["binding_status"]
        for item in items
        for d in (
            [item["definition"]]
            if item["kind"] == "link_type"
            else item["definition"].get("links", [])
        )
    ]


@pytest.mark.parametrize("kind", ["direct", "mapping_table"])
@pytest.mark.parametrize("missing", [None, "mapping", "field", "column", "join", "bridge"])
def test_relationship_readiness_requires_endpoints_and_valid_join(kind, missing):
    draft = relationship_draft(kind)
    if missing == "mapping":
        draft.mappings.clear()
    elif missing == "field":
        draft.mappings[1].fields.clear()
    elif missing == "column":
        draft.mappings[0].fields["number"].column = "missing"
    elif missing == "join":
        draft.link_types[0].data_join = None
    elif missing == "bridge":
        draft.datasets[2].columns.clear()
    expected = (
        "bound"
        if missing is None or (missing == "bridge" and kind == "direct")
        else "unbound"
    )
    assert link_statuses(draft) == [expected] * 3
    assert link_statuses(draft, mappings=False) == ["forbidden"] * 3


@pytest.mark.parametrize("kind", ["direct", "mapping_table"])
@pytest.mark.parametrize("separate", ["none", "endpoint", "bridge", "unavailable"])
def test_relationship_server_connections(kind, separate, monkeypatch):
    from ontofoundry_api.services import dataset_sources
    from ontofoundry_api.services.errors import NotFoundError

    draft = relationship_draft(kind)
    other = draft.datasets[1 if separate == "endpoint" else 2].id

    def resolve(db, workspace_id, dataset):
        if separate == "unavailable":
            raise NotFoundError("来源不存在")
        identity = (
            "other"
            if separate in {"endpoint", "bridge"} and dataset.id == other
            else "same"
        )
        return SimpleNamespace(connection=SimpleNamespace(id=identity))

    monkeypatch.setattr(dataset_sources, "resolve_dataset", resolve)
    monkeypatch.setattr(
        dataset_sources,
        "authorized_dataset_projection",
        lambda db, wid, ds: ds.model_dump(mode="json"),
    )
    expected = "bound"
    if separate == "unavailable":
        expected = "unbound"
    elif separate == "endpoint" or (separate == "bridge" and kind == "mapping_table"):
        expected = "cross_connection"
    assert (
        link_statuses(draft, db=object(), workspace_id=str(draft.workspace_id))
        == [expected] * 3
    )


def test_inherited_relationship_uses_concrete_local_binding():
    draft = example_draft("06-inheritance").model_copy(deep=True)
    child = next(o for o in draft.object_types if o.name == "device")
    mapping = next(m for m in draft.mappings if m.type_id == child.id)
    link_id = next(iter(mapping.inherited_link_bindings))
    assert next(link for link in draft.link_types if link.id == link_id).data_join is None

    def view():
        items = resource_items(draft.model_dump(mode="json"))
        obj = next(i["definition"] for i in items if i["definition"]["id"] == str(child.id))
        return next(link for link in obj["links"] if link["id"] == str(link_id))

    assert view()["binding_status"] == "bound"
    assert view()["data_join"]["kind"] == "direct"
    mapping.inherited_link_bindings.clear()
    assert view()["binding_status"] == "unbound"
    assert view()["data_join"] is None


def test_self_relationship_projects_both_directions_with_same_id():
    draft = example_draft("05-self-and-parallel-links")
    link = next(
        link for link in draft.link_types if link.source_type_id == link.target_type_id
    )
    items = resource_items(draft.model_dump(mode="json"))
    obj = next(
        i["definition"] for i in items if i["definition"]["id"] == str(link.source_type_id)
    )
    views = [v for v in obj["links"] if v["id"] == str(link.id)]
    assert [v["direction"] for v in views] == ["forward", "reverse"]
    assert all(v["source_role_name"] == link.source_role_name for v in views)
    assert all(v["target_role_name"] == link.target_role_name for v in views)
    assert all(v["verbalizes"] == link.verbalizes for v in views)
    assert (
        sum(
            i["kind"] == "link_type" and i["definition"]["id"] == str(link.id)
            for i in items
        )
        == 1
    )
