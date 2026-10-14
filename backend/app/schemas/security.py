"""Request and response schemas for enterprise security controls."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MFAEnrollRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class MFACodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8, pattern=r"^\d{6}$")


class MFADisableRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MFAEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str
    message: str


class SecuritySessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None
    is_current: bool = False


class SecurityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None
    user_id: UUID | None
    email: str | None
    event_type: str
    ip_address: str | None
    user_agent: str | None
    request_path: str | None
    details: dict[str, Any]
    timestamp: datetime
