from pydantic import EmailStr, TypeAdapter

from app.utils.strings import normalize_email

EMAIL_ADAPTER = TypeAdapter(EmailStr)


def validate_email(
    value: str,
    *,
    max_length: int = 255,
) -> str:
    value = normalize_email(value)

    if not value:
        raise ValueError("Email cannot be blank.")

    if len(value) > max_length:
        raise ValueError(f"Email must not exceed {max_length} characters.")

    try:
        validated_email = EMAIL_ADAPTER.validate_python(value)
    except ValueError as exc:
        raise ValueError("Email must be a valid email address.") from exc

    return str(validated_email)
