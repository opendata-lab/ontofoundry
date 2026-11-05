"""Registered MySQL column types classify, so bindings over them are ready."""

import pytest

from ontofoundry_api.domain.models import ValueKind
from ontofoundry_api.domain.validation import physical_value_kind


@pytest.mark.parametrize(
    "physical_type,kind",
    [
        ("enum('ODS','DWD','DWS')", ValueKind.STRING),
        ("set('read','write')", ValueKind.STRING),
        ("longtext", ValueKind.STRING),
        ("MEDIUMTEXT", ValueKind.STRING),
        ("tinytext", ValueKind.STRING),
        ("year", ValueKind.INTEGER),
        ("varchar(64)", ValueKind.STRING),
        ("blob", None),
    ],
)
def test_mysql_physical_types(physical_type, kind):
    assert physical_value_kind(physical_type) == kind
