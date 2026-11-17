"""Platform facts the standalone skill scripts must copy stay equal to the platform's.

The scripts run in DataAgent without the platform package, so a few small facts
are copied; these tests fail when the platform changes and the copy does not.
"""

import importlib

import conftest  # noqa: F401 - puts the skill scripts on sys.path
import pytest

pytest.importorskip("ontofoundry_api")
from ontofoundry_api.domain import expressions

show_element = importlib.import_module("show_element")


def test_expression_tokenizer_matches_the_platform():
    assert show_element.TOKEN.pattern == expressions._TOKEN.pattern
