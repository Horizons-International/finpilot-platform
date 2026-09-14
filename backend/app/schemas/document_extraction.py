from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.utils.enums import ExtractionStatus


class DocumentExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    ocr_result_id: UUID
    provider_name: str
    status: ExtractionStatus
    full_name: str | None
    date_of_birth: date | None
    nationality: str | None
    document_number: str | None
    expiry_date: date | None
    address: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
