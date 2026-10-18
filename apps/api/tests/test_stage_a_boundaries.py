"""Metadata drift retention and typed source keys are independent of compatibility models."""

import pytest

from ontofoundry_api.api.assets import retain_schema_changes
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


def test_typed_keys_reject_null_and_malformed_parts():
    for value in [[{"type": "null", "value": None}], [{"type": "integer", "value": 1}]]:
        with pytest.raises(ServiceError):
            key_values(value)
