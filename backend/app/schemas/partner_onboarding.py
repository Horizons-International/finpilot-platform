"""Validation and response schemas for enterprise partner onboarding."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.enums import PartnerOnboardingStatus


class PartnerOnboardingCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    registration_number: str | None = Field(default=None, max_length=100)
    tax_identification_number: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    business_description: str | None = Field(default=None, max_length=5000)
    contact_name: str = Field(min_length=2, max_length=200)
    contact_email: EmailStr
    contact_phone: str | None = Field(default=None, max_length=30)
    website: str | None = Field(default=None, max_length=500)
    country: str = Field(min_length=2, max_length=2)

    @field_validator(
        "organization_name",
        "legal_name",
        "registration_number",
        "tax_identification_number",
        "industry",
        "business_description",
        "contact_name",
        "contact_phone",
        "website",
    )
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("Country must be a two-letter country code.")
        return value


class PartnerBusinessInformationUpdate(BaseModel):
    organization_name: str | None = Field(default=None, min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    registration_number: str | None = Field(default=None, max_length=100)
    tax_identification_number: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    business_description: str | None = Field(default=None, max_length=5000)
    contact_name: str | None = Field(default=None, min_length=2, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=30)
    website: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator(
        "organization_name",
        "legal_name",
        "registration_number",
        "tax_identification_number",
        "industry",
        "business_description",
        "contact_name",
        "contact_phone",
        "website",
    )
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("Country must be a two-letter country code.")
        return value


class PartnerOnboardingAssignment(BaseModel):
    assigned_to: UUID


class PartnerOnboardingAction(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class PartnerOnboardingReject(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A rejection reason is required.")
        return value


class PartnerOnboardingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_name: str
    legal_name: str | None
    registration_number: str | None
    tax_identification_number: str | None
    industry: str | None
    business_description: str | None
    contact_name: str
    contact_email: EmailStr
    contact_phone: str | None
    website: str | None
    country: str
    status: PartnerOnboardingStatus
    assigned_to: UUID | None
    activated_tenant_id: UUID | None
    rejection_reason: str | None
    internal_notes: str | None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    activated_at: datetime | None


class PartnerOnboardingHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    onboarding_id: UUID
    action: str
    previous_status: PartnerOnboardingStatus | None
    status: PartnerOnboardingStatus
    changed_by: UUID | None
    notes: str | None
    created_at: datetime
