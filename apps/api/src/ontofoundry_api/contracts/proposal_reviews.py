from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# superseded: replaced by a merged batch (AI-08); kept for history, never decided again.
ProposalStatus = Literal["pending", "accepted", "rejected", "superseded"]


class ProposalBatchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["available"]
    created_at: datetime
    source_session_revision: int
    base_version_id: str | None
    counts: dict[ProposalStatus, int]
    error: dict | None
    producer: dict | None
    read_only: bool
