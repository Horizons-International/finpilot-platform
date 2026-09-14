from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.customer import CustomerResponse
from app.schemas.extraction_review import ExtractionReviewResponse


class ReviewDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    verification_case_id: UUID
    document_type_id: UUID

    file_name: str
    file_reference: str
    file_type: str
    file_size: int

    created_at: datetime


class ReviewOCRResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID

    provider_name: str
    extracted_text: str | None
    status: str

    created_at: datetime


class DocumentReviewResponse(BaseModel):
    document: ReviewDocumentResponse
    ocr_result: ReviewOCRResponse
    extraction: ExtractionReviewResponse
    customer: CustomerResponse
