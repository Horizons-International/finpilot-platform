"""Synthetic sales-demo scenario records isolated to one sandbox account."""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SandboxDemoRecord(Base):
    """A scenario/demo artifact; contains synthetic data only, never production rows."""

    __tablename__ = "sandbox_demo_records"
    __table_args__ = (
        UniqueConstraint(
            "sandbox_account_id",
            "scenario_key",
            name="uq_sandbox_demo_records_account_scenario",
        ),
        CheckConstraint(
            "record_type IN ('COMPLIANCE_CASE', 'AML_ALERT', 'AI_RISK_RECOMMENDATION', "
            "'INVESTIGATION_SUMMARY', 'DASHBOARD', 'REPORT', 'WORKFLOW')",
            name="ck_sandbox_demo_records_type",
        ),
        Index(
            "ix_sandbox_demo_records_account_type_created",
            "sandbox_account_id",
            "record_type",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["customer_id", "sandbox_account_id"],
            ["sandbox_customers.id", "sandbox_customers.sandbox_account_id"],
            ondelete="CASCADE",
            name="fk_sandbox_demo_records_customer_account",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True, index=True
    )
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scenario_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
