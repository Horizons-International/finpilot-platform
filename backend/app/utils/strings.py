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
