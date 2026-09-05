import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import VerificationStatus, VerificationType


class IdentityVerificationCase(Base):
    __tablename__ = "identity_verification_cases"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    customer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    verification_type: Mapped[VerificationType] = mapped_column(
        Enum(VerificationType),
        nullable=False,
    )

    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus),
        nullable=False,
        default=VerificationStatus.NOT_STARTED,
    )

    assigned_to: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
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
        back_populates="verification_cases",
    )

    assigned_reviewer = relationship(
        "User",
        foreign_keys=[assigned_to],
    )
