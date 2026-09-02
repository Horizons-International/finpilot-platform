from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.customer_contact import PreferredContactMethod
from app.utils.strings import normalize_email, normalize_whitespace


class CustomerContactCreate(BaseModel):
    phone_number: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    preferred_contact_method: PreferredContactMethod | None = None
    phone_verified: bool = False
    email_verified: bool = False

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_whitespace(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_address(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_email(value)


class CustomerContactUpdate(BaseModel):
    phone_number: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    preferred_contact_method: PreferredContactMethod | None = None
    phone_verified: bool | None = None
    email_verified: bool | None = None

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_whitespace(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_address(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_email(value)


class CustomerContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    phone_number: str | None
    email: EmailStr | None
    phone_verified: bool
    email_verified: bool
    preferred_contact_method: PreferredContactMethod | None
    created_at: datetime
