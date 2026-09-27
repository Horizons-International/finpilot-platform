from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import InvestigationNoteType


class InvestigationNoteCreate(BaseModel):
    activity_type: InvestigationNoteType = InvestigationNoteType.NOTE

    note: str = Field(
        min_length=1,
        max_length=10000,
    )

    attachment_reference: str | None = Field(
        default=None,
        max_length=500,
    )


class InvestigationNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    user_id: UUID
    activity_type: InvestigationNoteType
    note: str
    attachment_reference: str | None
    created_at: datetime
