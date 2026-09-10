from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.utils.enums import ReviewDecision


class VerificationReviewCreate(BaseModel):
    decision: ReviewDecision
    notes: str | None = None


class VerificationReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    verification_case_id: UUID
    reviewer_id: UUID
    decision: ReviewDecision
    notes: str | None
    created_at: datetime
