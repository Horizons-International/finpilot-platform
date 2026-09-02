import pytest

from app.utils.validators.phone import validate_phone


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+249912345678", "+249912345678"),
        ("+447911123456", "+447911123456"),
        ("+12025550123", "+12025550123"),
        (" +249912345678 ", "+249912345678"),
        ("+249 912 345 678", "+249912345678"),
        ("+249-912-345-678", "+249912345678"),
    ],
)
def test_validate_phone_accepts_valid_numbers(
    value: str,
    expected: str,
) -> None:
    assert validate_phone(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "0912345678",
        "912345678",
        "249912345678",
        "+0123456789",
        "+249123",
        "+249912345678abc",
        "phone-number",
        "++249912345678",
    ],
)
def test_validate_phone_rejects_invalid_numbers(value: str) -> None:
    with pytest.raises(ValueError):
        validate_phone(value)


def test_validate_phone_rejects_missing_country_code() -> None:
    with pytest.raises(
        ValueError,
        match="international format with a valid country code",
    ):
        validate_phone("912345678")


def test_validate_phone_rejects_zero_country_code() -> None:
    with pytest.raises(
        ValueError,
        match="international format with a valid country code",
    ):
        validate_phone("+0123456789")


def test_validate_phone_supports_custom_field_name() -> None:
    with pytest.raises(
        ValueError,
        match="Mobile number must be in international format",
    ):
        validate_phone(
            "0912345678",
            field_name="Mobile number",
        )


def test_validate_phone_rejects_invalid_number() -> None:
    with pytest.raises(
        ValueError,
        match="international format with a valid country code",
    ):
        validate_phone("+249123")
