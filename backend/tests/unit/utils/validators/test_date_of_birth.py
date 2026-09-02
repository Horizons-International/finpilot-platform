from datetime import date, timedelta

import pytest

from app.utils.validators.date_of_birth import validate_date_of_birth


def test_validate_date_of_birth_accepts_past_date() -> None:
    value = date(1990, 5, 15)

    assert validate_date_of_birth(value) == value


def test_validate_date_of_birth_accepts_today() -> None:
    value = date.today()

    assert validate_date_of_birth(value) == value


def test_validate_date_of_birth_rejects_future_date() -> None:
    value = date.today() + timedelta(days=1)

    with pytest.raises(
        ValueError,
        match="Date of birth cannot be in the future",
    ):
        validate_date_of_birth(value)
