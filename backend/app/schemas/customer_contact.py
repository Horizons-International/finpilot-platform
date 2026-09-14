from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.mixins import EmailFieldValidatorMixin, PhoneFieldValidatorMixin
from app.utils.enums import PreferredContactMethod


class CustomerContactCreate(
    PhoneFieldValidatorMixin,
    EmailFieldValidatorMixin,
    BaseModel,
):
    phone_number: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    preferred_contact_method: PreferredContactMethod | None = None
    phone_verified: bool = False
    email_verified: bool = False


class CustomerContactUpdate(
    PhoneFieldValidatorMixin,
    EmailFieldValidatorMixin,
    BaseModel,
):
    phone_number: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    preferred_contact_method: PreferredContactMethod | None = None
    phone_verified: bool | None = None
    email_verified: bool | None = None


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
