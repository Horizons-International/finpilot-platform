from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import DocumentCategory


class VerificationDocumentTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: DocumentCategory
    supported_countries: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Document name cannot be blank.")

        return value

    @field_validator("supported_countries")
    @classmethod
    def validate_supported_countries(
        cls,
        value: list[str],
    ) -> list[str]:
        normalized = []

        for country in value:
            country = country.strip().upper()

            if len(country) != 2 or not country.isalpha():
                raise ValueError("Country codes must be two-letter ISO-style codes.")

            normalized.append(country)

        return list(dict.fromkeys(normalized))


class VerificationDocumentTypeUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    category: DocumentCategory | None = None
    supported_countries: list[str] | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Document name cannot be blank.")

        return value

    @field_validator("supported_countries")
    @classmethod
    def validate_supported_countries(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None

        normalized = []

        for country in value:
            country = country.strip().upper()

            if len(country) != 2 or not country.isalpha():
                raise ValueError("Country codes must be two-letter ISO-style codes.")

            normalized.append(country)

        return list(dict.fromkeys(normalized))


class VerificationDocumentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: DocumentCategory
    supported_countries: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
