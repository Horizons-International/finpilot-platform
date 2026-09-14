from datetime import date

from pydantic import ValidationInfo, field_validator

from app.utils.strings import normalize_whitespace
from app.utils.validators import (
    validate_date_of_birth,
    validate_email,
    validate_name,
    validate_phone,
)


class NameFieldValidatorMixin:
    """Validates `first_name` / `last_name`-style fields."""

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def validate_names(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None

        field_name = (info.field_name or "Name").replace("_", " ").title()

        return validate_name(value, field_name=field_name)


class MiddleNameFieldValidatorMixin:
    """Validates an optional `middle_name` field."""

    @field_validator("middle_name", mode="before")
    @classmethod
    def validate_middle_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return validate_name(value, field_name="Middle name")


class EmailFieldValidatorMixin:
    """Validates and normalizes an `email` field."""

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_address(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return validate_email(value)


class PhoneFieldValidatorMixin:
    """Validates and normalizes a `phone_number` field."""

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return validate_phone(value)


class DateOfBirthFieldValidatorMixin:
    """Validates a `date_of_birth` field."""

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is None:
            return None

        return validate_date_of_birth(value)


class CustomerFreeTextFieldValidatorMixin:
    """Normalizes whitespace on `nationality` / `country_of_residence`."""

    @field_validator("nationality", "country_of_residence", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_whitespace(value)


class AddressFieldValidatorMixin:
    """Normalizes whitespace on free-text address fields."""

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


class DocumentTypeNameFieldValidatorMixin:
    """Validates the `name` field on verification document types."""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Document name cannot be blank.")

        return value


class SupportedCountriesFieldValidatorMixin:
    """Validates/normalizes ISO-style country codes on `supported_countries`."""

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
