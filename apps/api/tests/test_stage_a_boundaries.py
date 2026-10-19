"""Metadata drift retention and typed source keys are independent of compatibility models."""

import pytest
from fastapi import HTTPException

from ontofoundry_api.api import assets
from ontofoundry_api.api.assets import (
    merge_structure,
    previous_selection,
    retain_schema_changes,
)
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.instance_plan import key_values


def test_repeated_refresh_retains_unresolved_drift():
    change = {
        "table": "fictional_orders",
        "column": "amount",
        "kind": "changed",
        "before": "int",
        "after": "decimal",
    }
    assert retain_schema_changes([change], []) == [change]
    reverse = {**change, "before": "decimal", "after": "int"}
    assert retain_schema_changes([change], [reverse]) == []


def test_selected_refresh_replaces_only_named_tables():
    old_a = {"name": "a", "columns": [{"name": "id"}]}
    old_b = {"name": "b", "columns": [{"name": "id"}]}
    new_b = {"name": "b", "columns": [{"name": "id"}, {"name": "amount"}]}
    previous = {"tables": [old_a, old_b]}
    assert merge_structure(previous, {"tables": [new_b]}, ["b"]) == {
        "tables": [old_a, new_b]
    }
    assert previous_selection(previous, ["b"]) == {"tables": [old_b]}
    assert previous_selection(previous, None) is previous


def test_selected_refresh_bypasses_the_table_cap(monkeypatch):
    class Inspector:
        def get_table_names(self, schema=None):
            return [f"fictional_{i}" for i in range(250)]

        def get_view_names(self, schema=None):
            return []

        def get_pk_constraint(self, name, schema=None):
            return {"constrained_columns": []}

        def get_table_comment(self, name, schema=None):
            return {"text": None}

        def get_columns(self, name, schema=None):
            return [{"name": "id", "type": "int", "nullable": False, "comment": None}]

    monkeypatch.setattr(assets, "inspect", lambda connection: Inspector())
    with pytest.raises(HTTPException):
        assets.read_structure(object(), None)
    observed = assets.read_structure(object(), None, ["fictional_7"])
    assert [table["name"] for table in observed["tables"]] == ["fictional_7"]


def test_typed_keys_reject_null_and_malformed_parts():
    for value in [[{"type": "null", "value": None}], [{"type": "integer", "value": 1}]]:
        with pytest.raises(ServiceError):
            key_values(value)
