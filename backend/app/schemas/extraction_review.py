from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import ExtractionReviewStatus


class ExtractionReviewData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(
        default=None,
        max_length=100,
    )

    middle_name: str | None = Field(
        default=None,
        max_length=100,
    )

    last_name: str | None = Field(
        default=None,
        max_length=100,
    )

    date_of_birth: date | None = None

    nationality: str | None = Field(
        default=None,
        max_length=100,
    )

    document_number: str | None = Field(
        default=None,
        max_length=100,
    )

    expiry_date: date | None = None

    address: str | None = None


class ExtractionReviewUpdate(ExtractionReviewData):
    pass


class ExtractionReviewReject(BaseModel):
    reason: str = Field(
        min_length=1,
        max_length=1000,
    )


class ExtractionReviewResponse(ExtractionReviewData):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    ocr_result_id: UUID
    provider_name: str

    extraction_status: str = Field(validation_alias="status")
    review_status: ExtractionReviewStatus

    reviewed_by: UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None

    created_at: datetime
    updated_at: datetime
