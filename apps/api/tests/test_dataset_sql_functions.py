"""Read-only checks accept date differences and name unsupported reads correctly."""

import pytest

from ontofoundry_api.services.dataset_sources import DatasetSourceError
from ontofoundry_api.services.dataset_sql import parse_query


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("SELECT DATEDIFF(done_at, created_at) AS lead_days FROM fiction_story", "doris"),
        ("SELECT TIMESTAMPDIFF(DAY, created_at, done_at) AS lead_days FROM fiction_story", "mysql"),
        ("SELECT DATEDIFF(done_at, created_at) FROM fiction_story", "mysql"),
    ],
)
def test_date_differences_are_read_only(sql, dialect):
    parse_query(sql, dialect)


def test_unknown_read_function_is_unsupported_not_a_write():
    with pytest.raises(DatasetSourceError) as caught:
        parse_query("SELECT SOUNDEX(name) FROM fiction_supplier", "mysql")
    assert caught.value.code == "SQL_UNSUPPORTED"


def test_writes_are_still_refused():
    with pytest.raises(DatasetSourceError) as caught:
        parse_query("DELETE FROM fiction_supplier", "mysql")
    assert caught.value.code == "SQL_NOT_READ_ONLY"
