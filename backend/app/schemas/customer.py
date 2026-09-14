from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)

from app.schemas.mixins import (
    CustomerFreeTextFieldValidatorMixin,
    DateOfBirthFieldValidatorMixin,
    EmailFieldValidatorMixin,
    MiddleNameFieldValidatorMixin,
    NameFieldValidatorMixin,
    PhoneFieldValidatorMixin,
)
from app.utils.enums import CustomerStatus


class CustomerCreate(
    NameFieldValidatorMixin,
    MiddleNameFieldValidatorMixin,
    EmailFieldValidatorMixin,
    PhoneFieldValidatorMixin,
    DateOfBirthFieldValidatorMixin,
    CustomerFreeTextFieldValidatorMixin,
    BaseModel,
):
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


class CustomerUpdate(
    NameFieldValidatorMixin,
    MiddleNameFieldValidatorMixin,
    EmailFieldValidatorMixin,
    PhoneFieldValidatorMixin,
    DateOfBirthFieldValidatorMixin,
    CustomerFreeTextFieldValidatorMixin,
    BaseModel,
):
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
