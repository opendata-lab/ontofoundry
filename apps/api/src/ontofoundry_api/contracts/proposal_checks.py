"""Read-only proposal check and conversation notice contracts."""

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalCheckError(Strict):
    code: str
    message: str


class ProposalCheckResponse(Strict):
    passed: bool
    contract_errors: list[ProposalCheckError]
    reviewable_count: int = Field(ge=0)

