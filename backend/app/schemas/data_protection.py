from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetentionPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retention_days: int = Field(ge=1, le=36500)
    enabled: bool = True
    legal_basis: str | None = Field(default=None, max_length=255)

    @field_validator("legal_basis")
    @classmethod
    def validate_legal_basis(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("legal_basis cannot be blank")
        return value.strip() if value is not None else None


class DataProtectionPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    resource_type: str
    retention_days: int
    enabled: bool
    legal_basis: str | None
    created_at: datetime
    updated_at: datetime


class LegalHoldCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: UUID
    reason: str = Field(min_length=3, max_length=4000)


class LegalHoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    resource_type: str
    resource_id: UUID
    reason: str
    active: bool
    created_by: UUID
    released_by: UUID | None
    released_at: datetime | None
    created_at: datetime


class DeletionRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: UUID
    reason: str = Field(min_length=3, max_length=4000)


class DeletionRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    resource_type: str
    resource_id: UUID
    status: str
    requested_by: UUID | None
    approved_by: UUID | None
    reason: str
    failure_reason: str | None
    requested_at: datetime
    approved_at: datetime | None
    completed_at: datetime | None
