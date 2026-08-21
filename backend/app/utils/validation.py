import re

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    """Return True when the supplied value has a valid email format."""
    return bool(EMAIL_PATTERN.match(email.strip()))


def is_valid_uuid(value: str) -> bool:
    """Return True when the supplied value is a valid UUID string."""
    from uuid import UUID

    try:
        UUID(value)
        return True
    except ValueError:
        return False
