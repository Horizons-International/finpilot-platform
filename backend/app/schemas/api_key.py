import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import APIKeyStatus

_SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*:(read|write|create|update|delete)$")


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    permissions: list[str] = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("API key name must not be blank.")
        return normalized

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str]) -> list[str]:
        normalized = [permission.strip().lower() for permission in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("API key permissions must not contain duplicates.")
        invalid = [
            permission
            for permission in normalized
            if not _SCOPE_PATTERN.fullmatch(permission)
        ]
        if invalid:
            raise ValueError(
                "Each permission must use the format '<resource>:<action>', "
                "for example 'customers:read'."
            )
        return normalized


class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    permissions: list[str]
    status: APIKeyStatus
    created_by: UUID | None
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class APIKeyCreatedResponse(APIKeyResponse):
    """The raw key is returned only in this create response."""

    api_key: str


class APIKeyUsageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_key_id: UUID
    method: str
    path: str
    status_code: int
    request_id: str | None
    created_at: datetime
