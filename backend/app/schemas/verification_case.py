from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.utils.enums import VerificationStatus, VerificationType


class VerificationCaseCreate(BaseModel):
    verification_type: VerificationType


class VerificationCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    verification_type: VerificationType
    status: VerificationStatus
    assigned_to: UUID | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
