from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import ReviewDecision


class VerificationReview(Base):
    __tablename__ = "verification_reviews"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    verification_case_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "identity_verification_cases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    reviewer_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    decision: Mapped[ReviewDecision] = mapped_column(
        SQLEnum(
            ReviewDecision,
            name="review_decision",
            native_enum=True,
        ),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    verification_case = relationship(
        "IdentityVerificationCase",
        back_populates="reviews",
    )

    reviewer = relationship(
        "User",
        back_populates="verification_reviews",
    )
