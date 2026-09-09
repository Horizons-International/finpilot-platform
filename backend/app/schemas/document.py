from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.utils.enums import DocumentStatus


class CustomerDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    verification_case_id: UUID
    document_type_id: UUID
    file_reference: str
    file_name: str
    file_type: str
    file_size: int
    status: DocumentStatus
    uploaded_by: UUID
    created_at: datetime


class CustomerDocumentListResponse(BaseModel):
    documents: list[CustomerDocumentResponse]
    total: int
