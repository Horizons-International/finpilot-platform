from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import (
    AMLRuleSeverity,
    AMLRuleStatus,
    AMLRuleType,
)


class AMLRule(Base):
    __tablename__ = "aml_rules"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    rule_type: Mapped[AMLRuleType] = mapped_column(
        Enum(
            AMLRuleType,
            name="aml_rule_type",
        ),
        nullable=False,
        index=True,
    )

    condition: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    severity: Mapped[AMLRuleSeverity] = mapped_column(
        Enum(
            AMLRuleSeverity,
            name="aml_rule_severity",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[AMLRuleStatus] = mapped_column(
        Enum(
            AMLRuleStatus,
            name="aml_rule_status",
        ),
        nullable=False,
        default=AMLRuleStatus.ACTIVE,
        server_default="ACTIVE",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
