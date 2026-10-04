from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    AuditEventType,
    SystemConfigurationCategory,
    SystemConfigurationStatus,
)


class SystemConfigurationCreate(BaseModel):
    key: str = Field(
        min_length=3,
        max_length=200,
    )

    value: dict[str, Any]

    category: SystemConfigurationCategory

    status: SystemConfigurationStatus = SystemConfigurationStatus.ACTIVE


class SystemConfigurationUpdate(BaseModel):
    value: dict[str, Any]


class SystemConfigurationStatusUpdate(BaseModel):
    status: SystemConfigurationStatus


class SystemConfigurationResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    key: str
    value: dict[str, Any]
    category: SystemConfigurationCategory
    status: SystemConfigurationStatus
    updated_by: UUID | None
    updated_at: datetime


class SystemConfigurationAuditResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    user_id: UUID | None
    email: str | None
    event_type: AuditEventType
    timestamp: datetime
    ip_address: str | None
    user_agent: str | None
    resource_type: str | None
    resource_id: UUID | None
