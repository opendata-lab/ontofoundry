"""Core direct and mapping-table adjacency, including reverse/self links."""

from types import SimpleNamespace

import pytest
from core1_query_fixtures import source_database

from ontofoundry_api.services.instance_neighborhood import database_neighborhood
from ontofoundry_api.services.instance_plan import query_instances


@pytest.mark.parametrize(
    "example,center_type,expected",
    [
        (
            "01-basic-sales",
            "customer",
            {
                ("sales_order", ("O1",), "customer", "customer", ("C1",)),
                ("sales_order", ("O2",), "customer", "customer", ("C1",)),
            },
        ),
        (
            "02-many-to-many",
            "student",
            {
                ("student", ("S1",), "courses", "course", ("C1",)),
                ("student", ("S1",), "courses", "course", ("C2",)),
                ("enrollment", ("S1", "C1"), "student", "student", ("S1",)),
                ("enrollment", ("S1", "C2"), "student", "student", ("S1",)),
                ("enrollment", ("S1", "C1"), "course", "course", ("C1",)),
                ("enrollment", ("S1", "C2"), "course", "course", ("C2",)),
            },
        ),
        (
            "04-composite-key",
            "sales_order",
            {
                *(
                    ("order_line", ("O1", str(i)), "parent_order", "sales_order", ("O1",))
                    for i in range(1, 4)
                ),
                *(
                    ("order_line", ("O1", str(i)), "product", "product", (f"K{i}",))
                    for i in range(1, 4)
                ),
                *(
                    ("shipment", (f"H{i}",), "order_line", "order_line", ("O1", str(i)))
                    for i in range(1, 4)
                ),
            },
        ),
        (
            "05-self-and-parallel-links",
            "employee",
            {
                ("employee", ("E2",), "manager", "employee", ("E1",)),
                ("employee", ("E1",), "desk", "desk", ("D1",)),
            },
        ),
        (
            "05-self-and-parallel-links",
            "company",
            {
                ("trade", ("T1",), "buyer", "company", ("A",)),
                ("trade", ("T1",), "seller", "company", ("B",)),
                ("trade", ("T2",), "buyer", "company", ("B",)),
                ("trade", ("T2",), "seller", "company", ("A",)),
            },
        ),
        (
            "11-multi-source-and-unique-link",
            "account",
            {
                ("account", ("A1",), "customer", "customer", ("U1",)),
            },
        ),
    ],
)
def test_neighborhood_uses_declared_join_columns(
    tmp_path, monkeypatch, example, center_type, expected
):
    draft, engine = source_database(tmp_path, monkeypatch, example)
    try:
        obj = next(o for o in draft.object_types if o.technical_name == center_type)
        rows = query_instances(None, str(draft.workspace_id), draft, obj.id, None)["items"]
        assert rows, (
            "The fictional center must exist; empty query results cannot pass adjacency tests"
        )
        result = database_neighborhood(
            None,
            str(draft.workspace_id),
            draft,
            SimpleNamespace(
                type_id=obj.id, key=rows[0]["__key"], depth=2, snapshot_date=None
            ),
            None,
        )
        assert not result["warnings"], result["warnings"]
        assert not result["truncated"]
        names = {str(o.id): o.technical_name for o in draft.object_types}
        links = {str(relation.id): relation.technical_name for relation in draft.link_types}
        nodes = {
            o["id"]: (names[o["type_id"]], tuple(str(p["value"]) for p in o["key"]))
            for o in result["objects"]
        }
        assert {
            (*nodes[e["source_id"]], links[e["type_id"]], *nodes[e["target_id"]])
            for e in result["links"]
        } == expected
        assert len(result["objects"]) <= 100 and len(result["links"]) <= 300
    finally:
        engine.dispose()
