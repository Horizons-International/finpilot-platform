from datetime import date


def validate_date_of_birth(
    value: date,
) -> date:
    if value > date.today():
        raise ValueError("Date of birth cannot be in the future.")

    return value
