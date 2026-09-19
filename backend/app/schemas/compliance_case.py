from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    ComplianceCasePriority,
    ComplianceCaseStatus,
    ComplianceCaseType,
)


class ComplianceCaseCreate(BaseModel):
    customer_id: UUID
    case_type: ComplianceCaseType
    priority: ComplianceCasePriority
    description: str | None = Field(
        default=None,
        max_length=10000,
    )
    assigned_to: UUID | None = None


class ComplianceCaseUpdate(BaseModel):
    case_type: ComplianceCaseType | None = None
    priority: ComplianceCasePriority | None = None
    status: ComplianceCaseStatus | None = None
    assigned_to: UUID | None = None
    description: str | None = Field(
        default=None,
        max_length=10000,
    )


class ComplianceCaseResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    customer_id: UUID
    case_type: ComplianceCaseType
    priority: ComplianceCasePriority
    status: ComplianceCaseStatus
    assigned_to: UUID | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
