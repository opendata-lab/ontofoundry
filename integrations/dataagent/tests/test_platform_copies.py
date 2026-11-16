"""Platform facts the standalone skill scripts must copy stay equal to the platform's.

The scripts run in DataAgent without the platform package, so a few small facts
are copied; these tests fail when the platform changes and the copy does not.
"""

import importlib

import pytest
import test_workflow  # noqa: F401 - puts the skill scripts on sys.path

pytest.importorskip("ontofoundry_api")
from ontofoundry_api.domain import expressions, validation

expand_tables = importlib.import_module("expand_tables")
show_element = importlib.import_module("show_element")


def test_physical_type_classification_matches_the_platform():
    names = {name for group, _ in expand_tables.KINDS for name in group}
    samples = names | {"VARCHAR(32)", "decimal(10, 2)", "TIMESTAMP WITH TIME ZONE", "text", "uuid", "json", "geometry", ""}
    for physical in sorted(samples):
        platform = validation.physical_value_kind(physical)
        # Types the platform cannot classify read as text in the expander.
        assert expand_tables.value_kind(physical) == (platform.value if platform else "string"), physical


def test_expression_tokenizer_matches_the_platform():
    assert show_element.TOKEN.pattern == expressions._TOKEN.pattern
