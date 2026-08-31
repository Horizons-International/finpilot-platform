from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.customer import CustomerStatus
from app.utils.strings import normalize_email, normalize_whitespace


class CustomerCreate(BaseModel):
    first_name: str = Field(
        min_length=1,
        max_length=100,
    )

    middle_name: str | None = Field(
        default=None,
        max_length=100,
    )

    last_name: str = Field(
        min_length=1,
        max_length=100,
    )

    date_of_birth: date | None = None

    nationality: str | None = Field(
        default=None,
        max_length=100,
    )

    country_of_residence: str | None = Field(
        default=None,
        max_length=100,
    )

    email: EmailStr | None = None

    phone_number: str = Field(
        min_length=1,
        max_length=30,
    )

    @field_validator(
        "first_name",
        "middle_name",
        "last_name",
        "nationality",
        "country_of_residence",
        "phone_number",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_whitespace(value)

    @field_validator("email")
    @classmethod
    def normalize_customer_email(cls, value: EmailStr | None) -> EmailStr | None:
        if value is None:
            return None
        return normalize_whitespace(value)


class CustomerUpdate(BaseModel):
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    middle_name: str | None = Field(
        default=None,
        max_length=100,
    )

    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    date_of_birth: date | None = None

    nationality: str | None = Field(
        default=None,
        max_length=100,
    )

    country_of_residence: str | None = Field(
        default=None,
        max_length=100,
    )

    email: EmailStr | None = None

    phone_number: str | None = Field(
        default=None,
        max_length=30,
    )

    CustomerStatus: str | None = None

    @field_validator(
        "first_name",
        "middle_name",
        "last_name",
        "nationality",
        "country_of_residence",
        "phone_number",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_whitespace(value)

    @field_validator("email")
    @classmethod
    def normalize_customer_email(
        cls,
        value: EmailStr | None,
    ) -> EmailStr | None:
        if value is None:
            return None

        return normalize_email(value)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: str | None
    nationality: str | None
    country_of_residence: str | None
    email: EmailStr | None
    phone_number: str
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime
