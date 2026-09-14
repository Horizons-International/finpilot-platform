from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    ExtractionReviewStatus,
    ExtractionStatus,
)


class DocumentExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    ocr_result_id: UUID

    provider_name: str

    extraction_status: ExtractionStatus = Field(validation_alias="status")
    review_status: ExtractionReviewStatus

    first_name: str | None
    middle_name: str | None
    last_name: str | None

    date_of_birth: date | None
    nationality: str | None
    document_number: str | None
    expiry_date: date | None
    address: str | None

    error_message: str | None

    reviewed_by: UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None

    created_at: datetime
    updated_at: datetime
