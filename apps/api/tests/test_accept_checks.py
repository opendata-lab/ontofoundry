"""Accept-time checks (docs/design/2026-11-15-accept-completeness.md)."""

from copy import deepcopy
from uuid import uuid4

import pytest
from core1_fixtures import example_draft_json
from test_instance_store import accept_all
from test_modeling import ROOT, create_session, save
from test_t4_proposal_decisions import create, decide, seed_batch, update

from ontofoundry_api.db_models import DocumentInstanceRecord
from ontofoundry_api.domain.accept_checks import Change, definition_issues
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services.workspaces import DEV_USER_ID

# --- definitions (AC-04, AC-10) ------------------------------------------------


def sales():
    """Example 01: customer and order, each fully bound to a synced table."""
    return example_draft_json("01-basic-sales")


def by_name(draft, collection, name):
    return next(e for e in draft[collection] if e["name"] == name)


def with_property(draft, owner, name, bind_to=None):
    prop = {"id": str(uuid4()), "owner_type_id": by_name(draft, "object_types", owner)["id"],
            "name": name, "value_kind": "string"}
    draft["properties"].append(prop)
    changes = [Change("property", prop["id"], prop)]
    if bind_to:
        mapping = next(m for m in draft["mappings"] if m["type_id"] == prop["owner_type_id"])
        mapping["fields"][name] = {"kind": "column", "source_id": "main", "column": bind_to}
        changes.append(Change("mapping", mapping["id"], mapping))
    return changes


def issues(draft, changes):
    return definition_issues(CoreDraft.model_validate(draft), changes)


def test_a_complete_example_has_no_issues():
    draft = sales()
    changes = [Change("object_type", o["id"], o) for o in draft["object_types"]]
    assert issues(draft, changes) == []


def test_a_property_of_a_bound_object_needs_a_binding():
    draft = sales()
    [problem] = issues(draft, with_property(draft, "customer", "vip_level"))
    assert problem.endswith("：属性 vip_level（vip_level）未绑定")


def test_the_binding_accepted_together_satisfies_the_property():
    draft = sales()
    assert issues(draft, with_property(draft, "customer", "vip_level", bind_to="region")) == []


def test_a_gap_elsewhere_does_not_block_an_unrelated_accept():
    draft = sales()
    with_property(draft, "customer", "vip_level")  # left unbound, not being accepted
    other = next(o for o in draft["object_types"] if o["name"] != "customer")
    assert issues(draft, [Change("object_type", other["id"], other)]) == []


def test_an_object_without_a_table_is_not_checked():
    draft = sales()
    clause = {"id": str(uuid4()), "name": "contract_clause"}
    draft["object_types"].append(clause)
    prop = {"id": str(uuid4()), "owner_type_id": clause["id"], "name": "wording", "value_kind": "string"}
    draft["properties"].append(prop)
    assert issues(draft, [Change("object_type", clause["id"], clause), Change("property", prop["id"], prop)]) == []


def test_a_missing_logical_key_blocks():
    draft = sales()
    mapping = draft["mappings"][0]
    mapping["sources"][0]["key_columns"] = []
    assert any(p.endswith("：来源逻辑键待补全") for p in issues(draft, [Change("mapping", mapping["id"], mapping)]))


def test_an_unsynced_table_blocks_until_synced():
    draft = sales()
    customers = by_name(draft, "datasets", "customers")
    customers["columns"] = None
    mapping = next(m for m in draft["mappings"] if m["sources"][0]["dataset_id"] == customers["id"])
    found = issues(draft, [Change("mapping", mapping["id"], mapping)])
    assert any(p.endswith("：请先同步数据集 customers 的表结构，列无法验证") for p in found)


def test_a_metric_on_an_unsynced_table_blocks():
    draft = sales()
    orders = by_name(draft, "datasets", "orders")
    orders["columns"] = None
    metric = {"id": str(uuid4()), "name": "total", "display_name": "销售额", "kind": "simple",
              "dataset_id": orders["id"], "aggregation": "sum",
              "measure": {"dataset_id": orders["id"], "column": "ammount"}}
    draft["metrics"].append(metric)
    assert "指标 销售额：请先同步数据集 orders 的表结构，列无法验证" in issues(draft, [Change("metric", metric["id"], metric)])


# --- instances through the API (AC-02, AC-08, AC-11) -----------------------------


def types(session):
    return {o["name"]: o["id"] for o in session["draft"]["object_types"]}


def test_a_required_value_may_be_missing_in_a_proposal_but_not_when_accepted(client):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    label = next(p for p in draft["properties"] if p["name"] == "label")
    label["required"] = True
    session = save(client, session, draft).json()
    customer = types(session)["customer"]

    batch = seed_batch(client, session, [create("c", "material_object", {"type_id": customer, "values": {}})])
    # The review panel shows the same reason before anyone clicks accept (AC-05).
    [shown] = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()["items"]
    assert len(shown["acceptance_issues"]) == 1 and shown["acceptance_issues"][0].endswith("（label）待补全")
    response = decide(client, session, [(batch["items"][0]["id"], "accept")])
    assert response.status_code >= 400 and shown["acceptance_issues"][0] in response.text

    session, done = accept_all(client, session, [create("c2", "material_object", {"type_id": customer, "values": {"label": "月湾客户"}})])
    [ok] = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{done['id']}").json()["items"]
    assert ok["acceptance_issues"] == []


def test_definition_acceptance_issues_remain_separate(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales", published=True)
    mapping = session["draft"]["mappings"][0]
    sources = deepcopy(mapping["sources"])
    sources[0]["key_columns"] = []
    batch = seed_batch(client, session, [update("mapping", mapping, sources=sources, fields={}, inherited_link_bindings=[])])
    [item] = batch["items"]
    candidate = deepcopy(session["draft"])
    candidate["mappings"] = [item["after"] if m["id"] == mapping["id"] else m for m in candidate["mappings"]]
    expected = issues(candidate, [Change("mapping", mapping["id"], item["after"], mapping)])
    assert len(expected) >= 2
    assert item["acceptance_issues"] == expected
    rejected = decide(client, session, [(item["id"], "accept")])
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["issues"] == expected


def test_instance_acceptance_issues_remain_separate(client):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    customer = types(session)["customer"]
    next(p for p in draft["properties"] if p["name"] == "label")["required"] = True
    draft["properties"].append({
        "id": str(uuid4()), "owner_type_id": customer, "name": "fiction_grade",
        "value_kind": "string", "required": True,
    })
    session = save(client, session, draft).json()
    batch = seed_batch(client, session, [create("fiction-customer", "material_object", {"type_id": customer, "values": {}})])
    [item] = batch["items"]
    assert len(item["acceptance_issues"]) == 2
    assert any("（label）" in issue for issue in item["acceptance_issues"])
    assert any("（fiction_grade）" in issue for issue in item["acceptance_issues"])
    rejected = decide(client, session, [(item["id"], "accept")])
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["issues"] == item["acceptance_issues"]


def test_a_many_to_one_relation_accepts_only_one_target(client):
    session = create_session(client)
    t = types(session)
    buyer = session["draft"]["link_types"][0]
    source, target = (("order", "customer") if buyer["source_type_id"] == t["order"] else ("customer", "order"))
    values = {"order": {"order_no": "O-028"}, "customer": {"label": "月湾客户"}}

    def fact(ref, kind, title):
        return create(ref, "material_object", {"type_id": t[kind], "values": {**values[kind], **title}})

    key = "order_no" if target == "order" else "label"
    session, batch = accept_all(client, session, [
        fact("s", source, {}),
        fact("t1", target, {key: "第一"}),
        fact("t2", target, {key: "第二"}),
        create("l1", "material_link", {"type_id": buyer["id"], "source_id": {"client_ref": "s"},
                                       "target_id": {"client_ref": "t1"}}),
    ])
    ids = {i["client_ref"]: i["target_id"] for i in batch["items"]}
    second = seed_batch(client, session, [create("l2", "material_link", {
        "type_id": buyer["id"], "source_id": ids["s"], "target_id": ids["t2"]})])
    [shown] = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{second['id']}").json()["items"]
    response = decide(client, session, [(second["items"][0]["id"], "accept")])
    assert response.status_code >= 400 and shown["acceptance_issues"][0] in response.text
    assert f"关系 {buyer.get('display_name') or buyer['name']} 只能连一个" in response.text
    assert "第一" in response.text


def test_accepting_only_definitions_does_not_recheck_stored_instances(client):
    session = create_session(client)
    t = types(session)
    draft = deepcopy(session["draft"])
    draft["properties"].append({"id": str(uuid4()), "owner_type_id": t["customer"], "name": "visits",
                                "value_kind": "integer"})
    session = save(client, session, draft).json()
    with client.app.state.session_factory() as db:  # stored before numbers had to be numbers
        db.add(DocumentInstanceRecord(
            id=str(uuid4()), workspace_id=session["workspace_id"], state="active", revision=1,
            created_by=DEV_USER_ID, updated_by=DEV_USER_ID, type_id=t["customer"],
            values={"label": "旧客户", "visits": "42"}))
        db.commit()
    accept_all(client, session, [create("p", "property", {"owner_type_id": t["order"], "name": "channel"})])


# --- conditions (AC-09) -----------------------------------------------------------


@pytest.mark.parametrize(("kind", "expression", "valid"), [
    ("constraint", "{o}.amount + 1", False),
    ("constraint", "LENGTH({o}.status)", False),
    ("constraint", "{o}.amount >= 0", True),
    ("constraint", "{o}.amount < 100000 OR {o}.status IS NOT NULL", True),
    ("constraint", "CASE WHEN {o}.amount > 0 THEN TRUE ELSE FALSE END", True),
    ("derivation", "{o}.amount * 0.9", True),
])
def test_constraints_must_be_conditions(kind, expression, valid):
    draft = sales()
    order = next(o for o in draft["object_types"] if o["name"] != "customer")
    draft["rules"].append({"id": str(uuid4()), "name": "r1", "owner_kind": "object_type",
                           "owner_id": order["id"], "rule_kind": kind,
                           "expression": expression.format(o=order["name"])})
    if valid:
        OntologyDraft.model_validate(draft)
    else:
        with pytest.raises(ValueError, match="规则 r1：必须是条件（结果为真或假）"):
            OntologyDraft.model_validate(draft)


# --- review fixes (Codex review of PR #77) -----------------------------------------


def test_a_ratio_reads_the_datasets_of_its_parts():
    draft = sales()
    orders = by_name(draft, "datasets", "orders")
    orders["columns"] = None
    part = {"id": str(uuid4()), "name": "order_total", "kind": "simple", "dataset_id": orders["id"],
            "aggregation": "sum", "measure": {"dataset_id": orders["id"], "column": "amount"}}
    ratio = {"id": str(uuid4()), "name": "share", "display_name": "占比", "kind": "ratio",
             "numerator_id": part["id"], "denominator_id": part["id"]}
    draft["metrics"] += [part, ratio]
    assert "指标 占比：请先同步数据集 orders 的表结构，列无法验证" in issues(draft, [Change("metric", ratio["id"], ratio)])


def test_a_used_column_without_a_known_type_blocks():
    draft = sales()
    customers = by_name(draft, "datasets", "customers")
    next(c for c in customers["columns"] if c["name"] == "region")["physical_type"] = None
    mapping = next(m for m in draft["mappings"] if m["sources"][0]["dataset_id"] == customers["id"])
    found = issues(draft, [Change("mapping", mapping["id"], mapping)])
    assert any(p.endswith("：请先同步数据集 customers 的表结构，列无法验证") for p in found)


def test_nullif_may_be_a_condition():
    draft = sales()
    order = next(o for o in draft["object_types"] if o["name"] != "customer")
    draft["properties"].append({"id": str(uuid4()), "owner_type_id": order["id"], "name": "is_active",
                                "value_kind": "boolean"})
    draft["rules"].append({"id": str(uuid4()), "name": "r1", "owner_kind": "object_type", "owner_id": order["id"],
                           "rule_kind": "constraint", "expression": f"NULLIF({order['name']}.is_active, FALSE)"})
    OntologyDraft.model_validate(draft)


def test_a_property_is_accepted_with_the_mapping_update_that_binds_it(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales")
    draft = session["draft"]
    customer = by_name(draft, "object_types", "customer")
    mapping = next(m for m in draft["mappings"] if m["type_id"] == customer["id"])
    prop = create("vip", "property", {"owner_type_id": customer["id"], "name": "vip_region"})
    rebound = {
        "operation": "update", "target_kind": "mapping", "target_id": mapping["id"],
        "after": {**{k: v for k, v in mapping.items() if k != "id"},
                  "inherited_link_bindings": [],
                  "fields": {**mapping["fields"], "vip_region": {"kind": "column", "source_id": "main", "column": "region"}}},
    }
    batch = seed_batch(client, session, [prop, rebound])
    shown = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()["items"]
    assert all(i["acceptance_issues"] == [] for i in shown)
    the_property = next(i for i in shown if i["target_kind"] == "property")
    response = decide(client, session, [(the_property["id"], "accept")])
    assert response.status_code == 200, response.text
    assert {r["status"] for r in response.json()["results"]} == {"accepted"}
    assert len(response.json()["results"]) == 2


def test_deleting_the_old_target_frees_a_many_to_one_relation(client):
    from test_instance_store import baseline, instance_update

    session = create_session(client)
    t = types(session)
    buyer = session["draft"]["link_types"][0]
    source, target = (("order", "customer") if buyer["source_type_id"] == t["order"] else ("customer", "order"))
    values = {"order": {"order_no": "O-1"}, "customer": {"label": "旧"}}
    session, batch = accept_all(client, session, [
        create("s", "material_object", {"type_id": t[source], "values": values[source]}),
        create("t1", "material_object", {"type_id": t[target], "values": values[target]}),
        create("t2", "material_object", {"type_id": t[target], "values": values[target]}),
        create("l1", "material_link", {"type_id": buyer["id"], "source_id": {"client_ref": "s"},
                                       "target_id": {"client_ref": "t1"}}),
    ])
    ids = {i["client_ref"]: i["target_id"] for i in batch["items"]}
    old = next(e for e in baseline(client, session)["items"] if e["target_id"] == ids["t1"])
    change = seed_batch(client, session, [
        {**instance_update(old), "operation": "delete", "after": None},
        create("l2", "material_link", {"type_id": buyer["id"], "source_id": ids["s"], "target_id": ids["t2"]}),
    ])
    shown = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{change['id']}").json()["items"]
    # The new relation alone still conflicts. Accepting the independent target
    # deletion together frees its slot, which the combined decision verifies.
    assert next(i for i in shown if i["operation"] == "delete")["acceptance_issues"] == []
    assert next(i for i in shown if i["operation"] == "create")["acceptance_issues"]
    response = decide(client, session, [(i["id"], "accept") for i in change["items"]])
    assert response.status_code == 200, response.text
