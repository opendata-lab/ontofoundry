"""Run-scoped proposal submission: checked and stored in one transaction."""

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalSubmitIssue(Strict):
    code: str
    message: str


class ProposalSubmitResponse(Strict):
    passed: bool
    errors: list[ProposalSubmitIssue]
    warnings: list[ProposalSubmitIssue] = Field(default_factory=list)
    reviewable_count: int = Field(ge=0)
    batch_id: str | None = None
    repair_used: int = Field(default=0, ge=0)
    repair_limit: int = Field(default=2, ge=0)
