from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CustomerAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    user_id: UUID
    action: str
    changed_field: str
    old_value: object | None
    new_value: object | None
    created_at: datetime


class CustomerAuditLogListResponse(BaseModel):
    audit_logs: list[CustomerAuditLogResponse]
