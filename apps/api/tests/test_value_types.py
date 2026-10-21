"""Value types: shared base kind plus owned constraints (VT-01–VT-13)."""

from uuid import uuid4

import pytest
from test_core1_mcp import call
from test_core1_ossie_roundtrip import roundtrip
from test_modeling import create_session, publish, save

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import reference_index
from ontofoundry_api.domain.validation import validate_core_graph

WORKSPACE = uuid4()
MEMBER, LEVEL_TYPE, LEVEL, AMOUNT_TYPE, AMOUNT = (uuid4() for _ in range(5))


def draft(type_rules=(), property_rules=(), *, kind="string", type_kind="string", type_name="member_level"):
    return {
        "workspace_id": str(WORKSPACE),
        "object_types": [{"id": str(MEMBER), "name": "member", "display_name": "会员"}],
        "value_types": [
            {"id": str(LEVEL_TYPE), "name": type_name, "display_name": "会员等级", "value_kind": type_kind}
        ],
        "properties": [
            {"id": str(LEVEL), "owner_type_id": str(MEMBER), "name": "level", "display_name": "等级",
             "value_kind": kind, "value_type_id": str(LEVEL_TYPE)}
        ],
        "rules": [
            {"id": str(uuid4()), "name": f"type_rule_{i}", "owner_kind": "value_type", "owner_id": str(LEVEL_TYPE),
             "rule_kind": "constraint", "expression": text}
            for i, text in enumerate(type_rules)
        ]
        + [
            {"id": str(uuid4()), "name": f"own_rule_{i}", "owner_kind": "property", "owner_id": str(LEVEL),
             "rule_kind": "constraint", "expression": text}
            for i, text in enumerate(property_rules)
        ],
    }


def valid(raw):
    return validate_core_graph(CoreDraft.model_validate(raw))


@pytest.mark.parametrize(
    ("rules", "kind"),
    [
        (["member_level IN ('普通', '银卡', '金卡')"], "string"),
        (["REGEXP_LIKE(member_level, '^[0-9]{11}$')"], "string"),
        (["member_level >= 0", "member_level = ROUND(member_level, 2)"], "decimal"),
    ],
)
def test_supported_constraints_are_valid(rules, kind):
    assert valid(draft(rules, kind=kind, type_kind=kind))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (draft(kind="integer"), "基础类型须与值类型"),
        (draft(["member_level IS NOT NULL"]), "不判断空值"),
        (draft(["other_value > 1"]), "必须引用当前值"),
        (draft(["REGEXP_LIKE(member_level, '(a)\\\\1')"]), "反向引用"),
        (draft(type_name="String"), "内置类型名"),
        (draft(type_name="member"), "共享英文标识"),
    ],
)
def test_invalid_value_types_are_rejected(raw, message):
    with pytest.raises(ValueError, match=message):
        valid(raw)


def test_contradicting_constraints_are_not_guessed_at_save_time():
    # Conflicts surface in instance checks and human review, not a solver.
    enum = ["member_level IN ('普通', '银卡', '金卡')"]
    assert valid(draft(enum, ["member.level IN ('铂金')"]))


def test_deleting_a_used_value_type_is_blocked_and_usage_is_a_dependency():
    raw = draft(["member_level IN ('普通', '金卡')"])
    model = CoreDraft.model_validate(raw)
    targets = {r.target_id for r in reference_index(model).get(LEVEL, ())}
    assert LEVEL_TYPE in targets
    raw["value_types"] = []
    raw["rules"] = []
    with pytest.raises(ValueError, match="值类型不存在"):
        valid(raw)


def test_ossie_round_trip_keeps_shared_type_constraints_and_references():
    model = CoreDraft.model_validate(draft(["member_level IN ('普通', '金卡')"]))
    exported, restored = roundtrip(model)
    assert exported.document is not None
    types = restored.model.value_types
    assert [(v.name, v.display_name, str(v.value_kind)) for v in types] == [("member_level", "会员等级", "string")]
    assert restored.model.properties[0].value_type_id == types[0].id
    assert [(str(r.owner_kind), r.expression) for r in restored.model.rules] == [
        ("value_type", "member_level IN ('普通', '金卡')")
    ]


def test_mcp_finds_value_types_with_derived_constraints_and_usage(client):
    session = create_session(client)
    raw = session["draft"]
    extra = draft(["member_level IN ('普通', '金卡')"])
    extra["object_types"][0]["name"] = "fiction_member"
    extra["rules"][0]["expression"] = "member_level IN ('普通', '金卡')"
    for collection in ("object_types", "value_types", "properties", "rules"):
        raw[collection] = [*raw[collection], *extra[collection]]
    response = save(client, session, raw)
    assert response.status_code == 200, response.text
    assert publish(client, response.json()).status_code == 200
    found = call(client, "search_ontology", {"query": "会员等级", "kinds": ["value_type"]})["structuredContent"]
    assert [h["id"] for h in found["items"]] == [str(LEVEL_TYPE)]
    detail = call(client, "get_ontology", {"ids": [str(LEVEL_TYPE)]})["structuredContent"]["elements"][0]
    assert detail["kind"] == "value_type"
    assert detail["definition"]["constraints"] == ["member_level IN ('普通', '金卡')"]
    assert detail["definition"]["used_by_property_ids"] == [str(LEVEL)]


def test_renaming_a_type_named_like_a_function_keeps_the_function():
    from ontofoundry_api.domain.expressions import (
        render_references,
        resolve_rule_expression,
    )

    raw = draft(["round = ROUND(round, 2)"], kind="decimal", type_kind="decimal", type_name="round")
    model = CoreDraft.model_validate(raw)
    resolved = resolve_rule_expression(model, model.rules[0])
    raw["value_types"][0]["name"] = "amount"
    assert render_references(resolved, CoreDraft.model_validate(raw)) == "amount = ROUND(amount, 2)"


def test_changing_a_used_types_base_kind_revises_its_properties_in_one_save(client):
    from test_element_save import submit
    from test_modeling import ONTOLOGY, ROOT

    session = create_session(client)
    raw = session["draft"]
    extra = draft(kind="integer", type_kind="integer")
    extra["object_types"][0]["name"] = "fiction_member"
    for collection in ("object_types", "value_types", "properties"):
        raw[collection] = [*raw[collection], *extra[collection]]
    assert publish(client, save(client, session, raw).json()).status_code == 200
    latest = client.get(ROOT + "/published-snapshot").json()
    latest["value_types"][0]["value_kind"] = "decimal"
    next(p for p in latest["properties"] if p["id"] == str(LEVEL))["value_kind"] = "decimal"
    preview = client.post(
        ROOT + "/element-saves/preview",
        json={"target_kind": "value_type", "target_id": str(LEVEL_TYPE),
              "expected_current_version_id": client.get(ONTOLOGY + "/version").json()["version_id"], "draft": latest},
    )
    assert preview.status_code == 200, preview.text
    saved = submit(client, latest, kind="value_type", target_id=str(LEVEL_TYPE))
    assert saved.status_code == 200, saved.text
    level = next(p for p in saved.json()["draft"]["properties"] if p["id"] == str(LEVEL))
    assert level["value_kind"] == "decimal"
    # Anything else on the property stays outside a value type save.
    latest = client.get(ROOT + "/published-snapshot").json()
    next(p for p in latest["properties"] if p["id"] == str(LEVEL))["description"] = "顺带修改"
    sneaky = submit(client, latest, kind="value_type", target_id=str(LEVEL_TYPE))
    assert sneaky.status_code == 422 and sneaky.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"


def test_import_reuses_an_existing_value_type_with_the_same_name():
    from ontofoundry_api.services.import_matching import build_candidate_graph

    base = CoreDraft.model_validate(draft(["member_level IN ('普通', '金卡')"]))
    incoming_raw = draft(["member_level IN ('普通', '金卡')"])
    incoming_raw["value_types"][0]["id"] = str(uuid4())
    incoming_raw["rules"][0]["owner_id"] = incoming_raw["value_types"][0]["id"]
    incoming_raw["properties"][0]["value_type_id"] = incoming_raw["value_types"][0]["id"]
    candidate = build_candidate_graph(base, CoreDraft.model_validate(incoming_raw), native=False)
    assert candidate.id_map[incoming_raw["value_types"][0]["id"]] == str(LEVEL_TYPE)
    assert not candidate.blocked


def test_identifier_helper_types_do_not_come_back_as_value_types():
    from test_core1_ossie_roundtrip import read_ossie

    from ontofoundry_api.adapters.base import ImportContext
    from ontofoundry_api.adapters.ossie.importer import OssieAdapter

    raw = draft()
    raw["value_types"], raw["properties"][0]["value_type_id"] = [], None
    raw["properties"][0].update(identifier=True, required=True, unique=True)
    model = CoreDraft.model_validate(raw)
    exported, restored = roundtrip(model)
    assert restored.model.value_types == [] and restored.model.properties[0].value_type_id is None
    # Without the extension file the helper's shape still identifies it.
    pure = read_ossie(exported.document)[0]
    alone = OssieAdapter().import_document(pure.encode() if isinstance(pure, str) else pure, ImportContext(WORKSPACE))
    assert alone.model.value_types == []


def test_full_package_requires_materials_cited_only_by_value_types():
    from ontofoundry_api.adapters.base import ExportContext
    from ontofoundry_api.adapters.native.package import NativePackageAdapter

    raw = draft()
    raw["value_types"][0]["evidence"] = [
        {"id": str(uuid4()), "kind": "material", "material_id": str(uuid4()), "material_sha256": "a" * 64,
         "locator": {"line_start": 1, "line_end": 1}, "quote": "会员等级只有普通、银卡、金卡"}
    ]
    result = NativePackageAdapter().export_document(
        CoreDraft.model_validate(raw), ExportContext(workspace_name="虚构空间", workspace_slug="fiction", workspace_description="", materials=())
    )
    assert result.document is None
    assert any(i.outcome == "error" for i in result.report.issues)
