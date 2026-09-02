from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import AddressType
from app.utils.strings import normalize_whitespace


class CustomerAddressCreate(BaseModel):
    address_line_1: str = Field(
        min_length=1,
        max_length=255,
    )
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str = Field(
        min_length=1,
        max_length=100,
    )
    state: str | None = Field(default=None, max_length=100)
    country: str = Field(
        min_length=1,
        max_length=100,
    )
    postal_code: str | None = Field(default=None, max_length=30)
    address_type: AddressType
    is_primary: bool = False

    @field_validator(
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "country",
        "postal_code",
        mode="before",
    )
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_whitespace(value)


class CustomerAddressUpdate(BaseModel):
    address_line_1: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    address_line_2: str | None = Field(
        default=None,
        max_length=255,
    )
    city: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    state: str | None = Field(
        default=None,
        max_length=100,
    )
    country: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    postal_code: str | None = Field(
        default=None,
        max_length=30,
    )
    address_type: AddressType | None = None

    @field_validator(
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "country",
        "postal_code",
        mode="before",
    )
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_whitespace(value)


class CustomerAddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str | None
    country: str
    postal_code: str | None
    address_type: AddressType
    is_primary: bool
    created_at: datetime
    updated_at: datetime
