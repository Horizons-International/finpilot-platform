from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VerificationCaseAssignmentRequest(BaseModel):
    assigned_to: UUID


class VerificationCaseAssignmentResponse(BaseModel):
    verification_case_id: UUID
    assigned_to: UUID
    assigned_at: datetime
    assigned_by: UUID
    previous_reviewer: UUID | None


class VerificationCaseAssignmentHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    verification_case_id: UUID
    assigned_to: UUID
    previous_reviewer: UUID | None
    assigned_by: UUID
    assigned_at: datetime


class AssignedVerificationCaseResponse(BaseModel):
    verification_case_id: UUID
    customer_id: UUID
    verification_type: str
    status: str
    assigned_to: UUID
    assigned_at: datetime | None
    assigned_by: UUID | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AssignedVerificationCasesResponse(BaseModel):
    total: int
    cases: list[AssignedVerificationCaseResponse]
