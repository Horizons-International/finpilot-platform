import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import ComplianceCaseStatus


class ComplianceCaseHistory(Base):
    __tablename__ = "compliance_case_history"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    compliance_case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "compliance_cases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    from_status: Mapped[ComplianceCaseStatus | None] = mapped_column(
        Enum(
            ComplianceCaseStatus,
            name="compliance_case_status",
        ),
        nullable=True,
    )

    to_status: Mapped[ComplianceCaseStatus] = mapped_column(
        Enum(
            ComplianceCaseStatus,
            name="compliance_case_status",
        ),
        nullable=False,
    )

    changed_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    compliance_case = relationship(
        "ComplianceCase",
        back_populates="workflow_history",
    )

    changed_by_user = relationship(
        "User",
        foreign_keys=[changed_by],
        back_populates="compliance_case_history",
    )
