import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import (
    ComplianceCasePriority,
    ComplianceCaseStatus,
    ComplianceCaseType,
)


class ComplianceCase(Base):
    __tablename__ = "compliance_cases"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    customer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "customers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    case_type: Mapped[ComplianceCaseType] = mapped_column(
        Enum(
            ComplianceCaseType,
            name="compliance_case_type",
        ),
        nullable=False,
        index=True,
    )

    priority: Mapped[ComplianceCasePriority] = mapped_column(
        Enum(
            ComplianceCasePriority,
            name="compliance_case_priority",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[ComplianceCaseStatus] = mapped_column(
        Enum(
            ComplianceCaseStatus,
            name="compliance_case_status",
        ),
        nullable=False,
        default=ComplianceCaseStatus.OPEN,
        index=True,
    )

    assigned_to: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    resolution_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    customer = relationship(
        "Customer",
        back_populates="compliance_cases",
    )

    assigned_user = relationship(
        "User",
        foreign_keys=[assigned_to],
        back_populates="assigned_compliance_cases",
    )

    workflow_history = relationship(
        "ComplianceCaseHistory",
        back_populates="compliance_case",
        cascade="all, delete-orphan",
        order_by="ComplianceCaseHistory.created_at",
    )
