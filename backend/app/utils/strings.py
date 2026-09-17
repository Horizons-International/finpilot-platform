import re


def normalize_whitespace(value: str) -> str:
    """Collapse consecutive whitespace and trim the string."""
    return re.sub(r"\s+", " ", value).strip()


def normalize_email(email: str) -> str:
    """Normalize an email address for consistent storage and comparison."""
    return email.strip().lower()


def is_blank(value: str | None) -> bool:
    """Return True when a string is empty or contains only whitespace."""
    return value is None or not value.strip()


def truncate_text(
    value: str | None,
    max_length: int,
) -> str | None:
    if value is None:
        return None

    if len(value) <= max_length:
        return value

    return value[:max_length] + "\n[TRUNCATED]"
