"""Source population, inheritance, composite keys and independent snapshots."""

import pytest
from core1_query_fixtures import source_database

from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.instance_plan import query_instances
from ontofoundry_api.services.instance_query import db_ref, parse_ref


def query(draft, name):
    return next(o.id for o in draft.object_types if o.technical_name == name)


@pytest.mark.parametrize(
    "name",
    [
        "01-basic-sales",
        "02-many-to-many",
        "03-n-ary-reified",
        "04-composite-key",
        "05-self-and-parallel-links",
        "06-inheritance",
        "10-partial",
        "11-multi-source-and-unique-link",
        "12-snapshot-and-trends",
    ],
)
def test_each_bound_population_can_be_read(tmp_path, monkeypatch, name):
    draft, engine = source_database(tmp_path, monkeypatch, name)
    try:
        independent = [m for m in draft.mappings if m.binding_mode == "independent"]
        for mapping in independent:
            data = query_instances(
                None, str(draft.workspace_id), draft, mapping.type_id, None
            )
            assert data["source"] == "database"
            for row in data["items"]:
                source, tid, key = parse_ref(row["__ref"])
                assert (
                    source == "database" and key == row["__key"] and tid == row["__type_id"]
                )
    finally:
        engine.dispose()


def test_main_population_left_join_keeps_missing_and_excludes_orphan(tmp_path, monkeypatch):
    draft, engine = source_database(
        tmp_path, monkeypatch, "11-multi-source-and-unique-link"
    )
    try:
        data = query_instances(
            None, str(draft.workspace_id), draft, query(draft, "account"), None
        )
        assert len(data["items"]) == 2
        values = {i["values"]["account_no"]: i["values"] for i in data["items"]}
        assert set(values) == {"A1", "A2"}
        assert float(values["A1"]["available_amount"]) == 100
        assert values["A2"]["available_amount"] is None
    finally:
        engine.dispose()


def test_composite_keys_are_typed_ordered_and_injection_safe(tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "04-composite-key")
    try:
        mapping = next(
            m
            for m in draft.mappings
            if len(next(s for s in m.sources if s.id == "main").key_columns) > 1
        )
        data = query_instances(None, str(draft.workspace_id), draft, mapping.type_id, None)
        row = data["items"][0]
        exact = query_instances(
            None, str(draft.workspace_id), draft, mapping.type_id, None, key=row["__key"]
        )
        assert exact["items"] == [row]
        attack = [dict(part) for part in row["__key"]]
        attack[0] = {"type": "string", "value": "' OR 1=1 --"}
        assert (
            query_instances(
                None, str(draft.workspace_id), draft, mapping.type_id, None, key=attack
            )["items"]
            == []
        )
    finally:
        engine.dispose()


def test_independent_snapshot_dates_and_exact_date(tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "12-snapshot-and-trends")
    try:
        mapping = draft.mappings[0]
        result = query_instances(
            None, str(draft.workspace_id), draft, mapping.type_id, None
        )
        dates = {d["dataset_id"]: d["date"] for d in result["snapshot_dates"]}
        assert dates == {
            str(source.dataset_id): "2026-12-31" if source.id == "main" else "2026-12-30"
            for source in mapping.sources
        }
        assert len(result["items"]) == 1
        assert result["items"][0]["values"]["quantity"] == 10
        assert result["items"][0]["values"]["status"] == "可用"
        exact = query_instances(
            None,
            str(draft.workspace_id),
            draft,
            mapping.type_id,
            None,
            snapshot_date="2026-12-29",
        )
        assert len(exact["items"]) == 1
        assert exact["items"][0]["values"]["quantity"] == 16
        assert exact["items"][0]["values"]["status"] is None
        assert {d["date"] for d in exact["snapshot_dates"]} == {"2026-12-29"}
        assert (
            query_instances(
                None,
                str(draft.workspace_id),
                draft,
                mapping.type_id,
                None,
                snapshot_date="2026-12-30",
            )["items"]
            == []
        )
    finally:
        engine.dispose()


def test_ref_distinguishes_types_and_scalar_kinds():
    from uuid import uuid4

    a, b = uuid4(), uuid4()
    assert db_ref(a, [{"type": "string", "value": "1"}]) != db_ref(
        a, [{"type": "integer", "value": "1"}]
    )
    assert db_ref(a, [{"type": "integer", "value": "1"}]) != db_ref(
        b, [{"type": "integer", "value": "1"}]
    )
    with pytest.raises(ServiceError):
        parse_ref("db.WyIxIiwiMSJd")


def test_shared_parent_membership_and_virtual_identity(tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "06-inheritance")
    try:
        parent = query_instances(
            None, str(draft.workspace_id), draft, query(draft, "party"), None
        )
        person = query_instances(
            None, str(draft.workspace_id), draft, query(draft, "person"), None
        )
        vip = query_instances(
            None, str(draft.workspace_id), draft, query(draft, "vip_party"), None
        )
        virtual = query_instances(
            None, str(draft.workspace_id), draft, query(draft, "asset"), None
        )
        assert len(parent["items"]) == 3
        assert len(person["items"]) == 1
        assert len(vip["items"]) == 1
        assert len(virtual["items"]) == 2
        assert len({i["__ref"] for i in virtual["items"]}) == 2
    finally:
        engine.dispose()


def test_runtime_main_order_and_many_sources(tmp_path, monkeypatch):
    draft, engine = source_database(
        tmp_path, monkeypatch, "11-multi-source-and-unique-link"
    )
    try:
        mapping = draft.mappings[0]
        auxiliary = next(s for s in mapping.sources if s.id != "main")
        mapping.sources.extend(
            auxiliary.model_copy(update={"id": f"extra_{n}"}) for n in range(21)
        )
        mapping.sources.reverse()
        data = query_instances(None, str(draft.workspace_id), draft, mapping.type_id, None)
        assert len(data["items"]) == 2
    finally:
        engine.dispose()
