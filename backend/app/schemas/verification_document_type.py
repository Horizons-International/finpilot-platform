from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.mixins import (
    DocumentTypeNameFieldValidatorMixin,
    SupportedCountriesFieldValidatorMixin,
)
from app.utils.enums import DocumentCategory


class VerificationDocumentTypeCreate(
    DocumentTypeNameFieldValidatorMixin,
    SupportedCountriesFieldValidatorMixin,
    BaseModel,
):
    name: str = Field(min_length=1, max_length=100)
    category: DocumentCategory
    supported_countries: list[str] = Field(default_factory=list)
    is_active: bool = True


class VerificationDocumentTypeUpdate(
    DocumentTypeNameFieldValidatorMixin,
    SupportedCountriesFieldValidatorMixin,
    BaseModel,
):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    category: DocumentCategory | None = None
    supported_countries: list[str] | None = None
    is_active: bool | None = None


class VerificationDocumentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: DocumentCategory
    supported_countries: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
