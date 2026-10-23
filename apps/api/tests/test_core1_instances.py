"""Source population, inheritance, composite keys and independent snapshots."""

import pytest
from core1_query_fixtures import source_database

from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.instance_plan import query_instances
from ontofoundry_api.services.instance_query import db_ref, parse_ref


def query(draft, name):
    return next(o.id for o in draft.object_types if o.name == name)


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


@pytest.mark.parametrize("local_condition", [False, True])
def test_exists_membership_correlates_to_current_party(
    tmp_path, monkeypatch, local_condition
):
    from ontofoundry_api.domain.core import DerivedExpression

    draft, engine = source_database(tmp_path, monkeypatch, "06-inheritance")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO contracts (contract_id, amount, signer_id) VALUES ('K1', 100, 'P2')"
            )
        vip = next(o for o in draft.object_types if o.name == "vip_party")
        # A/P1 satisfies the local condition but has no contract. Only B/P2 has one.
        expression = "EXISTS (party.REVERSE(signer))"
        if local_condition:
            expression = "party.phone <> '3' AND " + expression
        vip.derived_by = [DerivedExpression(kind="expression", expression=expression)]
        result = query_instances(None, str(draft.workspace_id), draft, vip.id, None)
        assert [r["values"]["party_no"] for r in result["items"]] == ["P2"]
        assert result["items"][0]["__key"] == [{"type": "string", "value": "P2"}]
    finally:
        engine.dispose()


def test_reverse_virtual_parent_expands_concrete_local_bindings(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from ontofoundry_api.services.instance_neighborhood import database_neighborhood

    draft, engine = source_database(tmp_path, monkeypatch, "06-inheritance")
    try:
        # Both assets have the same local key, but distinct concrete identities.
        with engine.begin() as conn:
            conn.exec_driver_sql("UPDATE vehicles SET responsible_id = 'P1'")
        party = next(o for o in draft.object_types if o.name == "party")
        responsible = next(
            relation
            for relation in draft.link_types
            if relation.name == "responsible_party"
        )
        result = database_neighborhood(
            None,
            str(draft.workspace_id),
            draft,
            SimpleNamespace(
                type_id=party.id,
                key=[{"type": "string", "value": "P1"}],
                depth=1,
                snapshot_date=None,
            ),
            None,
        )
        assert not result["warnings"], result["warnings"]
        assets = [o for o in result["objects"] if o["type_id"] != str(party.id)]
        assert {o["type_id"] for o in assets} == {
            str(o.id) for o in draft.object_types if o.name in {"device", "vehicle"}
        }
        assert len(assets) == 2 and len({o["id"] for o in assets}) == 2
        assert all(o["key"] == [{"type": "string", "value": "1"}] for o in assets)
        edges = [e for e in result["links"] if e["type_id"] == str(responsible.id)]
        assert {(e["source_id"], e["target_id"]) for e in edges} == {
            (o["id"], result["center_id"]) for o in assets
        }
    finally:
        engine.dispose()


@pytest.mark.parametrize("dialect_name", ["postgresql", "mysql"])
@pytest.mark.parametrize("modulo", [False, True])
def test_expression_like_literals_use_driver_safe_parameters(dialect_name, modulo):
    from sqlalchemy import column, select, table
    from sqlalchemy.dialects import mysql, postgresql
    from sqlglot import parse_one

    from ontofoundry_api.services.instance_plan import ResolvedScalar

    party = table("party", column("phone"), column("party_no"))
    expression = "phone LIKE '1%'"
    if modulo:
        expression += " AND phone % 2 = 1"
    scalar = ResolvedScalar(parse_one(expression), {"phone": party.c.phone})
    statement = select(party.c.party_no).where(scalar, party.c.party_no == "P1")
    dialect = {"postgresql": postgresql.dialect, "mysql": mysql.dialect}[dialect_name]()
    compiled = statement.compile(dialect=dialect)
    sql = str(compiled)
    assert "'1%'" not in sql
    assert "1%" in compiled.params.values()
    assert "P1" in compiled.params.values()
    # Simulate only the driver's percent formatting, without a connection.
    parameters = (
        tuple(compiled.params[name] for name in compiled.positiontup)
        if compiled.positional
        else compiled.params
    )
    rendered = sql % parameters
    assert "1%" in rendered and "P1" in rendered
    if modulo:
        assert " % 2" in rendered
    inlined = str(
        statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    )
    assert "'1%%'" in inlined


@pytest.mark.parametrize("neighborhood", [False, True])
def test_virtual_parent_exact_key_requires_concrete_type(monkeypatch, neighborhood):
    from types import SimpleNamespace

    from core1_fixtures import example_draft

    from ontofoundry_api.services.instance_neighborhood import database_neighborhood

    draft = example_draft("06-inheritance")
    virtual_id = query(draft, "asset")
    key = [{"type": "string", "value": "missing-asset"}]

    def unexpected_source(*args, **kwargs):
        pytest.fail("Virtual parent exact lookup must fail before any source lookup")

    monkeypatch.setattr(
        "ontofoundry_api.services.instance_plan.resolve_dataset", unexpected_source
    )
    with pytest.raises(ServiceError) as error:
        if neighborhood:
            database_neighborhood(
                None,
                str(draft.workspace_id),
                draft,
                SimpleNamespace(type_id=virtual_id, key=key, depth=1, snapshot_date=None),
                None,
            )
        else:
            query_instances(None, str(draft.workspace_id), draft, virtual_id, None, key=key)
    assert error.value.status_code == 422
    assert error.value.code == "INVALID_OBJECT_REF"
    assert "具体类型" in error.value.message


def test_a_child_sharing_a_snapshot_parent_reads_only_the_snapshot_day(tmp_path, monkeypatch):
    # A child with member conditions and no mapping of its own, over a daily
    # snapshot table: it must read the chosen day, not every day's copy.
    from uuid import uuid4

    from ontofoundry_api.domain.core import DerivedSimple, ObjectType, PathCondition

    draft, engine = source_database(tmp_path, monkeypatch, "12-snapshot-and-trends")
    try:
        mapping = draft.mappings[0]
        parent = next(o for o in draft.object_types if o.id == mapping.type_id)
        identifier = next(p for p in draft.properties if p.owner_type_id == parent.id and p.identifier)
        whole = query_instances(None, str(draft.workspace_id), draft, parent.id, None)
        key = whole["items"][0]["values"][identifier.name]
        child = ObjectType(
            id=uuid4(), name="picked", synonyms=[], tags=[], extends=parent.id, evidence=[],
            derived_by=[DerivedSimple(kind="simple", conditions=[PathCondition(
                path={"links": [], "property_id": identifier.id}, operator="eq", values=[key])])],
        )
        draft.object_types.append(child)
        latest = query_instances(None, str(draft.workspace_id), draft, child.id, None)
        assert latest["snapshot_dates"] and latest["items"]
        assert {d["date"] for d in latest["snapshot_dates"]} == {d["date"] for d in whole["snapshot_dates"]}
        assert len(latest["items"]) == 1
        older = query_instances(None, str(draft.workspace_id), draft, child.id, None, snapshot_date="2026-12-29")
        assert {d["date"] for d in older["snapshot_dates"]} == {"2026-12-29"}
    finally:
        engine.dispose()
