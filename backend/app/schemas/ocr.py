from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.utils.enums import OCRProcessingStatus


class OCRResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    provider_name: str
    request_id: UUID | None
    extracted_text: str | None
    status: OCRProcessingStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime
