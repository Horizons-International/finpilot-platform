from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.utils.enums import OrganizationStatus


class OrganizationCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )

    legal_name: str | None = Field(
        default=None,
        max_length=200,
    )

    registration_number: str | None = Field(
        default=None,
        max_length=100,
    )

    tax_identification_number: str | None = Field(
        default=None,
        max_length=100,
    )

    industry: str | None = Field(
        default=None,
        max_length=100,
    )

    business_description: str | None = Field(
        default=None,
        max_length=5000,
    )

    contact_name: str | None = Field(
        default=None,
        max_length=200,
    )

    contact_email: EmailStr | None = None

    contact_phone: str | None = Field(
        default=None,
        max_length=30,
    )

    website: str | None = Field(
        default=None,
        max_length=500,
    )

    country: str = Field(
        min_length=2,
        max_length=2,
    )

    status: OrganizationStatus = OrganizationStatus.ACTIVE

    settings: dict = Field(
        default_factory=dict,
    )

    @field_validator(
        "name",
        "legal_name",
        "registration_number",
        "tax_identification_number",
        "industry",
        "business_description",
        "contact_name",
        "website",
    )
    @classmethod
    def strip_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("country")
    @classmethod
    def normalize_country(
        cls,
        value: str,
    ) -> str:
        value = value.strip().upper()

        if len(value) != 2 or not value.isalpha():
            raise ValueError(
                "Country must be a valid two-letter country code.",
            )

        return value


class OrganizationUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )

    legal_name: str | None = Field(
        default=None,
        max_length=200,
    )

    registration_number: str | None = Field(
        default=None,
        max_length=100,
    )

    tax_identification_number: str | None = Field(
        default=None,
        max_length=100,
    )

    industry: str | None = Field(
        default=None,
        max_length=100,
    )

    business_description: str | None = Field(
        default=None,
        max_length=5000,
    )

    contact_name: str | None = Field(
        default=None,
        max_length=200,
    )

    contact_email: EmailStr | None = None

    contact_phone: str | None = Field(
        default=None,
        max_length=30,
    )

    website: str | None = Field(
        default=None,
        max_length=500,
    )

    country: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )

    status: OrganizationStatus | None = None

    settings: dict | None = None

    @field_validator(
        "name",
        "legal_name",
        "registration_number",
        "tax_identification_number",
        "industry",
        "business_description",
        "contact_name",
        "website",
    )
    @classmethod
    def strip_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("country")
    @classmethod
    def normalize_country(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip().upper()

        if len(value) != 2 or not value.isalpha():
            raise ValueError(
                "Country must be a valid two-letter country code.",
            )

        return value


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    tenant_id: UUID
    name: str
    legal_name: str | None
    registration_number: str | None
    tax_identification_number: str | None
    industry: str | None
    business_description: str | None
    contact_name: str | None
    contact_email: EmailStr | None
    contact_phone: str | None
    website: str | None
    country: str
    status: OrganizationStatus
    settings: dict
    created_at: datetime
    updated_at: datetime
