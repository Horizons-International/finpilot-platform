"""One explicit feedback record per user and AI interaction."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIModelFeedback(Base):
    __tablename__ = "ai_model_feedback"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            "user_id",
            name="uq_ai_model_feedback_tenant_interaction_user",
        ),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_ai_model_feedback_rating_range",
        ),
        Index("ix_ai_model_feedback_tenant_created", "tenant_id", "created_at"),
    )

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
    interaction_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_interactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unspecified", server_default="unspecified"
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    is_accurate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    interaction = relationship("AIInteraction", foreign_keys=[interaction_id])
    user = relationship("User", foreign_keys=[user_id])
    tenant = relationship("Tenant")
