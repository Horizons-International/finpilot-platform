import re

from app.utils.strings import normalize_whitespace

NAME_PATTERN = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$", re.UNICODE)


def validate_name(
    value: str,
    *,
    field_name: str = "Name",
    max_length: int = 100,
) -> str:
    value = normalize_whitespace(value)

    if not value:
        raise ValueError(f"{field_name} cannot be blank.")

    if len(value) > max_length:
        raise ValueError(f"{field_name} must not exceed {max_length} characters.")

    if not NAME_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} contains invalid characters.")

    return value
