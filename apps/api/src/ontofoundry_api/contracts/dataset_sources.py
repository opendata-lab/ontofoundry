"""Dataset source validation requests and linked registered tables."""

from pydantic import Field

from ontofoundry_api.domain.core import Dataset, Strict


class DatasetCheck(Strict):
    dataset: Dataset
    expected_session_revision: int | None = None
    session_id: str | None = None


class LinkedTable(Strict):
    """A registered table a modeling session works from (not a dataset yet)."""

    connection_id: str = Field(min_length=1, max_length=36)
    schema_name: str = Field(default="", max_length=240)
    table_name: str = Field(min_length=1, max_length=240)
