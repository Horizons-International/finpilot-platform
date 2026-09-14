from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import ReviewDecision
from app.utils.strings import normalize_whitespace


class VerificationReviewCreate(BaseModel):
    decision: ReviewDecision
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = normalize_whitespace(value)

        return value or None


class VerificationReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    verification_case_id: UUID
    reviewer_id: UUID
    decision: ReviewDecision
    notes: str | None
    created_at: datetime
