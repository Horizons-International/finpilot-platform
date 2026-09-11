from pydantic import BaseModel


class VerificationSummaryResponse(BaseModel):
    total_cases: int
    pending_cases: int
    approved_cases: int
    rejected_cases: int


class DocumentSummaryResponse(BaseModel):
    uploaded_documents: int
    accepted_documents: int
    rejected_documents: int
