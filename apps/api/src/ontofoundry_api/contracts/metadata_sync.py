"""Full and selected-table sync requests share the same batch mechanism."""

from typing import Literal

from pydantic import Field, model_validator

from ontofoundry_api.domain.core import Strict


class SyncRequest(Strict):
    scope: Literal["all", "selected"]
    tables: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def selection(self):
        if self.scope == "selected" and (not self.tables or any(not t.strip() or len(t) > 240 for t in self.tables)):
            raise ValueError("指定表同步必须选择至少一张有效表")
        if self.scope == "all" and self.tables:
            raise ValueError("全量同步不能同时指定表")
        return self
