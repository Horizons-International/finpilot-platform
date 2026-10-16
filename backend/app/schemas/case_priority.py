from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import ComplianceCasePriority


class CasePriorityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    case_id: UUID
    priority_level: ComplianceCasePriority
    priority_score: Decimal
    reason: str
    risk_snapshot: dict[str, Any]
    created_at: datetime


class CasePriorityListRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
