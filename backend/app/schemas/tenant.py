from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import TenantStatus


class TenantCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )

    code: str = Field(
        min_length=2,
        max_length=50,
        pattern=r"^[A-Z0-9][A-Z0-9_-]*$",
    )

    @field_validator("name")
    @classmethod
    def normalize_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Tenant name is required.")

        return value

    @field_validator("code")
    @classmethod
    def normalize_code(
        cls,
        value: str,
    ) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("Tenant code is required.")

        return value


class TenantResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    name: str
    code: str
    status: TenantStatus
    created_at: datetime
