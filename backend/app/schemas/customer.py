from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationInfo,
    field_validator,
)

from app.utils.enums import CustomerStatus
from app.utils.strings import normalize_whitespace
from app.utils.validators import (
    validate_date_of_birth,
    validate_email,
    validate_name,
    validate_phone,
)


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

    email: EmailStr

    phone_number: str = Field(
        min_length=1,
        max_length=30,
    )

    status: CustomerStatus = CustomerStatus.NEW

    @field_validator("middle_name", mode="before")
    @classmethod
    def validate_middle_name(
        cls,
        value: str,
    ) -> str | None:
        if value is None:
            return None

        return validate_name(
            value,
            field_name="Middle name",
        )

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def validate_names(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field_name = info.field_name

        if field_name is None:
            field_name = "Name"

        field_name = field_name.replace("_", " ").title()

        return validate_name(
            value,
            field_name=field_name,
        )

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_address(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        return validate_phone(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is None:
            return None

        return validate_date_of_birth(value)

    @field_validator(
        "nationality",
        "country_of_residence",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
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

    @field_validator("middle_name")
    @classmethod
    def validate_middle_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return validate_name(
            value,
            field_name="Middle name",
        )

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def validate_names(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None

        field_name = info.field_name

        if field_name is None:
            field_name = "Name"

        field_name = field_name.replace("_", " ").title()

        return validate_name(
            value,
            field_name=field_name,
        )

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_address(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return validate_email(value)

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return validate_phone(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(
        cls,
        value: date | None,
    ) -> date | None:
        if value is None:
            return None

        return validate_date_of_birth(value)

    @field_validator(
        "nationality",
        "country_of_residence",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return normalize_whitespace(value)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date | None
    nationality: str | None
    country_of_residence: str | None
    email: EmailStr | None
    phone_number: str
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime


class CustomerStatusUpdate(BaseModel):
    status: CustomerStatus


class CustomerListResponse(BaseModel):
    customers: list[CustomerResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CustomerSortField(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    EMAIL = "email"
    DATE_OF_BIRTH = "date_of_birth"
