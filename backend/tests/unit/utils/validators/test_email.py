import pytest

from app.utils.validators.email import validate_email


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("john@example.com", "john@example.com"),
        ("JOHN@EXAMPLE.COM", "john@example.com"),
        ("  john@example.com  ", "john@example.com"),
        ("john.smith@example.com", "john.smith@example.com"),
        ("john+test@example.com", "john+test@example.com"),
    ],
)
def test_validate_email_accepts_valid_emails(
    value: str,
    expected: str,
) -> None:
    assert validate_email(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "not-an-email",
        "john",
        "john@",
        "@example.com",
        "john@example",
        "john.example.com",
    ],
)
def test_validate_email_rejects_invalid_emails(value: str) -> None:
    with pytest.raises(ValueError):
        validate_email(value)


def test_validate_email_rejects_email_exceeding_max_length() -> None:
    value = f"{'a' * 250}@example.com"

    with pytest.raises(ValueError, match="must not exceed 255 characters"):
        validate_email(value)


def test_validate_email_supports_custom_max_length() -> None:
    value = "john@example.com"

    with pytest.raises(ValueError, match="must not exceed 10 characters"):
        validate_email(value, max_length=10)
