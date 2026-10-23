"""Validation and response schemas for enterprise partner onboarding."""

from datetime import datetime
from ipaddress import ip_network
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

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
    def strip_strings(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if info.field_name in {"organization_name", "contact_name"} and not value:
            field_label = info.field_name.replace("_", " ").capitalize()
            raise ValueError(f"{field_label} is required.")
        return value or None

    @field_validator("contact_email")
    @classmethod
    def normalize_contact_email(cls, value: EmailStr) -> EmailStr:
        return cast(EmailStr, str(value).strip().lower())

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

    @field_validator("contact_email")
    @classmethod
    def normalize_contact_email(cls, value: EmailStr | None) -> EmailStr | None:
        if value is None:
            return None
        return cast(EmailStr, str(value).strip().lower())

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


class PartnerOnboardingPortalCreatedResponse(PartnerOnboardingResponse):
    """Portal token is shown only at creation and is never stored in plaintext."""

    portal_token: str
    portal_token_expires_at: datetime


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


class PartnerOnboardingAdministratorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    department: str | None = Field(default=None, max_length=100)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_required_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Administrator first and last names are required.")
        return normalized

    @field_validator("department")
    @classmethod
    def strip_department(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return cast(EmailStr, str(value).strip().lower())


class PartnerOnboardingAdministratorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    onboarding_id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    role: str
    department: str | None
    status: str
    invited_at: datetime | None
    created_at: datetime


class PartnerOnboardingAdministratorCreatedResponse(
    PartnerOnboardingAdministratorResponse
):
    """Invitation token is returned once and is never stored in plaintext."""

    invitation_token: str


class PartnerOnboardingDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    onboarding_id: UUID
    document_type: str
    original_filename: str
    content_type: str
    file_size: int
    sha256: str
    review_status: str
    review_notes: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class PartnerOnboardingDocumentReview(BaseModel):
    review_status: Literal["APPROVED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_rejection_reason(self) -> "PartnerOnboardingDocumentReview":
        if self.review_status == "REJECTED" and not self.notes:
            raise ValueError("Review notes are required when rejecting a document.")
        return self


class PartnerTechnicalSetupUpdate(BaseModel):
    target_environment: Literal["sandbox", "production"]
    callback_url: AnyHttpUrl
    allowed_ip_ranges: list[str] = Field(default_factory=list, max_length=100)
    integration_contact_email: EmailStr

    @field_validator("callback_url")
    @classmethod
    def require_https_callback(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        host = value.host

        if host is None:
            raise ValueError("Callback URL must include a host.")
        host = host.lower().strip("[]")
        if value.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Callback URL must use HTTPS.")
        return value

    @field_validator("allowed_ip_ranges")
    @classmethod
    def validate_ip_ranges(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            try:
                normalized.append(str(ip_network(value, strict=False)))
            except ValueError as exc:
                raise ValueError(f"Invalid IP address or network: {value}") from exc
        if len(normalized) != len(set(normalized)):
            raise ValueError("IP allow-list must not contain duplicates.")
        return normalized

    @field_validator("integration_contact_email")
    @classmethod
    def normalize_integration_email(cls, value: EmailStr) -> EmailStr:
        return cast(EmailStr, str(value).strip().lower())


class PartnerOnboardingProgressStep(BaseModel):
    key: str
    label: str
    complete: bool
    detail: str


class PartnerOnboardingProgressResponse(BaseModel):
    onboarding_id: UUID
    status: PartnerOnboardingStatus
    progress_percent: int
    steps: list[PartnerOnboardingProgressStep]
    documents: list[PartnerOnboardingDocumentResponse]
    administrators: list[PartnerOnboardingAdministratorResponse]
    technical_setup: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class PartnerOnboardingActivationResponse(PartnerOnboardingResponse):
    """Raw API key is returned only once when portal-backed onboarding activates."""

    api_key: str | None = None


class PartnerOnboardingPortalSubmitResponse(BaseModel):
    onboarding_id: UUID
    status: PartnerOnboardingStatus
    submitted: bool
    progress_percent: int
