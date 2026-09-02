import pytest

from app.utils.validators.name import validate_name


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("John", "John"),
        ("John Smith", "John Smith"),
        ("Mary-Jane", "Mary-Jane"),
        ("O'Connor", "O'Connor"),
        ("Jean Pierre", "Jean Pierre"),
        ("José", "José"),
        ("  John   Smith  ", "John Smith"),
    ],
)
def test_validate_name_accepts_valid_names(
    value: str,
    expected: str,
) -> None:
    assert validate_name(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "John123",
        "John@",
        "John_",
        "John!",
        "12345",
    ],
)
def test_validate_name_rejects_invalid_names(value: str) -> None:
    with pytest.raises(ValueError):
        validate_name(value)


def test_validate_name_rejects_name_exceeding_max_length() -> None:
    value = "A" * 101

    with pytest.raises(ValueError, match="must not exceed 100 characters"):
        validate_name(value)


def test_validate_name_supports_custom_field_name() -> None:
    with pytest.raises(ValueError, match="First name cannot be blank"):
        validate_name("   ", field_name="First name")


def test_validate_name_supports_custom_max_length() -> None:
    with pytest.raises(ValueError, match="must not exceed 10 characters"):
        validate_name("A" * 11, max_length=10)
