"""Read-only proposal check and conversation notice contracts."""

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalCheckError(Strict):
    code: str
    message: str


class UnacceptableGroup(Strict):
    client_refs: list[str | None]
    item_count: int = Field(ge=1)
    reason: str
    code: str = "PROPOSAL_GROUP_UNACCEPTABLE"


class ProposalCheckResponse(Strict):
    passed: bool
    contract_errors: list[ProposalCheckError]
    unacceptable_groups: list[UnacceptableGroup]
    reviewable_count: int = Field(ge=0)
    unacceptable_count: int = Field(ge=0)


class ProposalRunNotice(Strict):
    run_token: str
    summary: str
    affected_count: int = Field(ge=0)
    reviewable_count: int = Field(ge=0)
