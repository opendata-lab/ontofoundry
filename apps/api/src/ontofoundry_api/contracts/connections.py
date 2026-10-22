"""Connection deletion diagnostics, derived from current references."""

from typing import Literal

from ontofoundry_api.domain.core import Strict


class ConnectionReference(Strict):
    type: Literal["dataset", "dataset_proposal", "linked_table"]
    name: str
    location: str


class ConnectionInUse(Strict):
    code: Literal["CONNECTION_IN_USE"] = "CONNECTION_IN_USE"
    message: str
    references: list[ConnectionReference]


class ConnectionInUseResponse(Strict):
    error: ConnectionInUse
