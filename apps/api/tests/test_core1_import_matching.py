"""Import identity matching never depends on file order or fact business values."""

from copy import deepcopy
from uuid import UUID, uuid4

from core1_fixtures import example_draft_json

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.import_matching import (
    build_candidate_graph,
    match_import,
    rewrite_import_ids,
)
from ontofoundry_api.services.import_proposals import build_import_batch

WS = UUID("22222222-2222-4222-8222-222222222222")


def object_type(name, ident=None):
    return {"id": str(ident or uuid4()), "display_name": name, "name": name}


def graph(*objects):
    return CoreDraft.model_validate({**empty_snapshot(WS), "object_types": list(objects)})


def test_uuid_locks_all_targets_before_natural_names_are_considered():
    alpha, beta = object_type("alpha"), object_type("beta")
    base = graph(alpha, beta)
    renamed_beta = {**beta, "name": "gamma", "display_name": "gamma"}
    new_beta = object_type("beta")
    source = graph(new_beta, renamed_beta)
    ids = match_import(base, source, native=True)
    assert ids[beta["id"]] == beta["id"]
    assert ids[new_beta["id"]] == new_beta["id"]
    assert match_import(base, graph(renamed_beta, new_beta), native=True) == ids


def test_natural_child_mapping_uses_remapped_owner_and_preserves_unmatched_uuid():
    old = object_type("order")
    new = object_type("order")
    prop_id, old_prop = str(uuid4()), str(uuid4())
    base = graph(old).model_dump(mode="json")
    base["properties"] = [
        {
            "id": old_prop,
            "owner_type_id": old["id"],
            "display_name": "编号",
            "name": "code",
            "value_kind": "string",
        }
    ]
    source = graph(new).model_dump(mode="json")
    source["properties"] = [
        {**base["properties"][0], "id": prop_id, "owner_type_id": new["id"]}
    ]
    result = build_candidate_graph(
        CoreDraft.model_validate(base), CoreDraft.model_validate(source), native=True
    )
    assert result.id_map[new["id"]] == old["id"]
    assert result.id_map[prop_id] == old_prop
    assert not result.changes and result.unchanged == 2


def test_native_name_swap_is_atomic_and_rewrites_external_rule_literal_safely():
    alpha, beta = object_type("alpha"), object_type("beta")
    base = graph(alpha, beta).model_dump(mode="json")
    property_id = str(uuid4())
    base["properties"] = [
        {
            "id": property_id,
            "display_name": "标签",
            "name": "label",
            "owner_type_id": alpha["id"],
            "value_kind": "string",
        }
    ]
    base["rules"] = [
        {
            "id": str(uuid4()),
            "display_name": "标签规则",
            "name": "label_rule",
            "owner_kind": "object_type",
            "owner_id": alpha["id"],
            "rule_kind": "constraint",
            "expression": "alpha.label <> 'alpha.label'",
        }
    ]
    source = graph(
        {**alpha, "display_name": "beta", "name": "beta"},
        {**beta, "display_name": "alpha", "name": "alpha"},
    )
    result = build_candidate_graph(CoreDraft.model_validate(base), source, native=True)
    assert not result.blocked
    assert result.model.rules[0].expression == "beta.label <> 'alpha.label'"
    batch = build_import_batch(
        base, result.changes, batch_id=str(uuid4()), lookup=lambda _: None
    )
    changed = {i.target_id: i for i in batch.items}
    assert changed[alpha["id"]].atomic_group_id == changed[beta["id"]].atomic_group_id
    assert changed[alpha["id"]].atomic_group_id


def test_kind_conflict_blocks_reverse_closure_but_keeps_independent_import():
    old = object_type("old")
    unrelated = object_type("independent")
    source = graph(object_type("new", old["id"]), unrelated).model_dump(mode="json")
    source["properties"] = [
        {
            "id": str(uuid4()),
            "display_name": "编号",
            "name": "code",
            "owner_type_id": old["id"],
            "value_kind": "string",
        }
    ]
    result = build_candidate_graph(
        graph(),
        CoreDraft.model_validate(source),
        native=True,
        registered={old["id"]: "dataset"},
    )
    assert {c["target_id"] for c in result.changes} == {unrelated["id"]}
    assert len(result.blocked) == 2


def test_duplicate_display_names_do_not_block_distinct_identifiers():
    old = object_type("orders")
    source = graph({**object_type("other"), "display_name": "orders"}, object_type("independent"))
    result = build_candidate_graph(graph(old), source, native=True)
    assert not result.blocked
    assert {c["after"]["name"] for c in result.changes} == {"other", "independent"}
    assert old["id"] in {str(o.id) for o in result.model.object_types}


def test_empty_and_repeat_import_never_propose_delete():
    base = CoreDraft.model_validate(example_draft_json("07-instances-and-evidence"))
    empty = build_candidate_graph(base, graph(), native=True)
    same = build_candidate_graph(base, base, native=True)
    assert not empty.changes and not same.changes
    assert empty.model == base and same.model == base


def test_same_business_values_and_quote_never_merge_facts_or_evidence():
    data = example_draft_json("07-instances-and-evidence")
    base = CoreDraft.model_validate(data)
    source = deepcopy(data)
    fact = source["material_objects"][0]
    previous_id = fact["id"]
    fact["id"] = str(uuid4())
    fact["evidence"] = [{**e, "id": str(uuid4())} for e in fact["evidence"]]
    for edge in source["material_links"]:
        for key in ("source_id", "target_id"):
            if edge[key] == previous_id:
                edge[key] = fact["id"]
    result = build_candidate_graph(base, CoreDraft.model_validate(source), native=True)
    assert len(result.model.material_objects) == len(base.material_objects) + 1
    assert result.id_map[fact["id"]] == fact["id"]


def test_mapping_uuid_lock_cannot_be_replaced_by_type_key():
    base = CoreDraft.model_validate(example_draft_json("01-basic-sales"))
    source = base.model_copy(deep=True)
    assert len(base.mappings) >= 2
    source.mappings[0].type_id, source.mappings[1].type_id = (
        source.mappings[1].type_id,
        source.mappings[0].type_id,
    )
    ids = match_import(base, source, native=True)
    assert all(ids[str(m.id)] == str(m.id) for m in source.mappings)


def test_all_typed_ids_rewrite_and_expressions_keep_string_literals():
    base = CoreDraft.model_validate(example_draft_json("13-dataset-metrics"))
    ids = {
        str(e.id): str(uuid4())
        for c in (
            "object_types",
            "properties",
            "link_types",
            "rules",
            "metrics",
            "datasets",
            "mappings",
            "material_objects",
            "material_links",
        )
        for e in getattr(base, c)
    }
    result = rewrite_import_ids(base, ids)
    validate_core_graph(result)
    assert {str(d.id) for d in result.datasets} == {ids[str(d.id)] for d in base.datasets}
    for m in result.metrics:
        if m.kind != "ratio":
            assert str(m.dataset_id) in ids.values()


def test_imported_expression_is_resolved_in_its_own_namespace_even_if_text_unchanged():
    alpha, beta = object_type("alpha"), object_type("beta")
    base = graph(alpha, beta).model_dump(mode="json")
    pa, pb = str(uuid4()), str(uuid4())
    base["properties"] = [
        {
            "id": pa,
            "display_name": "甲编号",
            "name": "code",
            "owner_type_id": alpha["id"],
            "value_kind": "string",
        },
        {
            "id": pb,
            "display_name": "乙编号",
            "name": "code",
            "owner_type_id": beta["id"],
            "value_kind": "string",
        },
    ]
    base["rules"] = [
        {
            "id": str(uuid4()),
            "display_name": "编号规则",
            "name": "code_rule",
            "owner_kind": "object_type",
            "owner_id": alpha["id"],
            "rule_kind": "constraint",
            "expression": "alpha.code <> 'alpha.code'",
        }
    ]
    source = deepcopy(base)
    source["object_types"] = [
        {**alpha, "display_name": "beta", "name": "beta"},
        {**beta, "display_name": "alpha", "name": "alpha"},
    ]
    source["rules"][0]["owner_id"] = beta["id"]
    validate_core_graph(CoreDraft.model_validate(source))
    result = build_candidate_graph(
        CoreDraft.model_validate(base), CoreDraft.model_validate(source), native=True
    )
    assert not result.blocked
    assert result.model.rules[0].expression == "alpha.code <> 'alpha.code'"
    batch = build_import_batch(
        base, result.changes, batch_id=str(uuid4()), lookup=lambda _: None
    )
    assert (
        next(i.after for i in batch.items if i.target_kind == "rule")["expression"]
        == "alpha.code <> 'alpha.code'"
    )


def test_duplicate_display_names_do_not_split_a_valid_identifier_exchange():
    alpha = object_type("alpha", UUID("00000000-0000-4000-8000-0000000000f1"))
    beta = object_type("beta", UUID("00000000-0000-4000-8000-0000000000f2"))
    retained1, retained2 = object_type("retained_one"), object_type("retained_two")
    source = graph(
        {**alpha, "display_name": "beta", "name": "beta"},
        {**beta, "display_name": "alpha", "name": "alpha"},
        {
            **object_type("new_one", UUID("00000000-0000-4000-8000-000000000001")),
            "display_name": "retained_one",
        },
        {
            **object_type("new_two", UUID("00000000-0000-4000-8000-000000000002")),
            "display_name": "retained_two",
        },
    )
    result = build_candidate_graph(
        graph(alpha, beta, retained1, retained2), source, native=True
    )
    assert not result.blocked
    assert len(result.changes) == 4
    assert {alpha["id"], beta["id"]} <= {c["target_id"] for c in result.changes}
