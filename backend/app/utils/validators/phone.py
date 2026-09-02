import re

import phonenumbers
from phonenumbers import NumberParseException

from app.utils.strings import normalize_whitespace

PHONE_FORMAT_PATTERN = re.compile(r"^\+[0-9][0-9\s().-]*$")


def validate_phone(
    value: str,
    *,
    field_name: str = "Phone number",
) -> str:
    value = normalize_whitespace(value)

    if not value:
        raise ValueError(f"{field_name} cannot be blank.")

    if not PHONE_FORMAT_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field_name} must be in international format with a valid country code."
        )

    try:
        phone_number = phonenumbers.parse(value, None)
    except NumberParseException:
        raise ValueError(
            f"{field_name} must be in international format with a valid country code."
        ) from None

    if not phonenumbers.is_valid_number(phone_number):
        raise ValueError(
            f"{field_name} must be in international format with a valid country code."
        )

    return phonenumbers.format_number(
        phone_number,
        phonenumbers.PhoneNumberFormat.E164,
    )
