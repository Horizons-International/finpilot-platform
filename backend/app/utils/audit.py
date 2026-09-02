from datetime import date, datetime
from enum import Enum
from uuid import UUID


def serialize_audit_value(
    value: object | None,
) -> object | None:
    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Enum):
        return str(value.value)

    return value
