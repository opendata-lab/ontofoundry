"""A/B semantic differences have exact paths and checked transformations, not blanket RT tags."""

import json
from pathlib import Path
from uuid import UUID

import pytest
import sqlglot
from rt_cases import SYNTHETIC_ROUNDTRIPS
from sqlglot import exp
from test_core1_ossie_roundtrip import property_projection, roundtrip

from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.ossie.importer import OssieAdapter


def differences(left, right, path=""):
    if type(left) is not type(right):
        return {path}
    if isinstance(left, dict):
        return {path + "/" + key for key in left.keys() ^ right.keys()} | set().union(
            *(
                differences(left[key], right[key], path + "/" + key)
                for key in left.keys() & right.keys()
            )
        )
    if isinstance(left, list):
        if len(left) != len(right):
            return {path}
        return set().union(
            *(
                differences(a, b, path + "/" + str(i))
                for i, (a, b) in enumerate(zip(left, right, strict=True))
            )
        )
    return {path} if left != right else set()


@pytest.mark.parametrize("case", SYNTHETIC_ROUNDTRIPS, ids=lambda c: c.source)
def test_ab_roundtrip_checks_each_semantic_loss_and_exact_remaining_difference(case):
    raw = (Path(__file__).parent / "fixtures" / case.source).read_bytes()
    source = OssieAdapter().import_document(
        raw, ImportContext(UUID("44444444-4444-4444-8444-444444444444"))
    )
    exported, restored = roundtrip(source.model)
    repeated, _ = roundtrip(restored.model)
    left, right = json.loads(exported.document), json.loads(repeated.document)
    for document in (left, right):
        for scope in document.get("ontology_mappings", []):
            for dataset in scope["semantic_model"]["datasets"]:
                # RT-10 permits field order changes when the two aliases are renamed.
                dataset["fields"].sort(
                    key=lambda f: json.dumps(f["expression"], sort_keys=True)
                )
    assert differences(left, right) == set(case.allowed_reexport_differences)
    assert property_projection(source.model) == property_projection(restored.model)
    owners = {o.id: o.technical_name for o in source.model.object_types}
    lost = {owners[m.type_id] for m in source.model.mappings} - {
        o.technical_name
        for o in restored.model.object_types
        if any(m.type_id == o.id for m in restored.model.mappings)
    }
    assert lost == case.dropped_mapping_owners
    for name in lost:
        obj = next(o for o in source.model.object_types if o.technical_name == name)
        assert not any(
            p.identifier for p in source.model.properties if p.owner_type_id == obj.id
        )
        assert any(
            i.construct == "ObjectMapping"
            and i.rule_id == "RT-43"
            and i.target_element_ids == [obj.id]
            and i.outcome == "dropped"
            for i in exported.report.issues
        )
    # Resolve only the two reviewed aliases; all AST algorithms, constants,
    # NULL branches, fields, keys, source positions and other document data match.
    for scope in left.get("ontology_mappings", []):
        for dataset in scope["semantic_model"]["datasets"]:
            aliases = case.field_aliases.get(dataset["name"], {})
            for field in dataset["fields"]:
                if field["name"] in aliases:
                    assert (
                        field["expression"]["dialects"][0]["expression"]
                        == '"' + aliases[field["name"]] + '"'
                    )
                    field["name"] = aliases[field["name"]]
        for metric in scope["semantic_model"]["metrics"]:
            expression = metric["expression"]["dialects"][0]
            ast = sqlglot.parse_one(expression["expression"])
            for column in ast.find_all(exp.Column):
                replacement = case.field_aliases.get(column.table, {}).get(column.name)
                if replacement:
                    column.set("this", exp.to_identifier(replacement, quoted=True))
            expression["expression"] = ast.sql()
    # SQL formatting is RT-13; compare parsed canonical expressions on both sides.
    for document in (left, right):
        for scope in document.get("ontology_mappings", []):
            for metric in scope["semantic_model"]["metrics"]:
                variant = metric["expression"]["dialects"][0]
                variant["expression"] = sqlglot.parse_one(variant["expression"]).sql()
    assert left == right
