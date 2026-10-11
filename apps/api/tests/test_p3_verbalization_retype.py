"""Retyping a role must keep untouched readings pointing at that role (real bottom-up run, 2026-10-11)."""
from ontofoundry_api.contracts.proposals import _carry_placeholders

OWNER = "2cfd13ac-fe00-549b-a7bb-2d5817c7e298"
NAMES = {OWNER: "customer", "v1": "customer_level_value"}


def prop(concept, verbalizes, role_name=None):
    return {"owner_ref": {"kind": "object_type", "ref": OWNER}, "owner_role_name": None,
            "roles": [{"id": "r1", "name": role_name, "concept": concept}], "verbalizes": verbalizes}


def test_builtin_retype_renames_placeholder():
    before = prop({"kind": "builtin", "ref": "String"}, ["{customer}客户编号{String}"])
    after = prop({"kind": "builtin", "ref": "Integer"}, ["{customer}客户编号{String}"])
    assert _carry_placeholders(before, after, NAMES) == ["{customer}客户编号{Integer}"]


def test_named_role_and_value_type_keep_qualifier():
    before = prop({"kind": "builtin", "ref": "String"}, ["{customer}的等级是{String:level}"], "level")
    after = prop({"kind": "value_type", "ref": "v1"}, ["{customer}的等级是{String:level}"], "level")
    assert _carry_placeholders(before, after, NAMES) == ["{customer}的等级是{customer_level_value:level}"]


def test_unchanged_concept_and_other_text_untouched():
    before = prop({"kind": "builtin", "ref": "String"}, ["{customer}有一个String编号{String}"])
    assert _carry_placeholders(before, before, NAMES) == ["{customer}有一个String编号{String}"]
    after = prop({"kind": "builtin", "ref": "Integer"}, ["{customer}有一个String编号{String}"])
    assert _carry_placeholders(before, after, NAMES) == ["{customer}有一个String编号{Integer}"]
