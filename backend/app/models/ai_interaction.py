from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import (
    AIFunction,
    AIInteractionStatus,
    AIResourceType,
)


class AIInteraction(Base):
    __tablename__ = "ai_interactions"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    ai_function: Mapped[AIFunction] = mapped_column(
        SQLEnum(
            AIFunction,
            name="ai_function",
            create_constraint=False,
        ),
        nullable=False,
        index=True,
    )

    prompt_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_prompts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    resource_type: Mapped[AIResourceType] = mapped_column(
        SQLEnum(
            AIResourceType,
            name="ai_resource_type",
            create_constraint=True,
        ),
        nullable=False,
    )

    resource_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    response_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    response_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provider_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    provider_request_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[AIInteractionStatus] = mapped_column(
        SQLEnum(
            AIInteractionStatus,
            name="ai_interaction_status",
            create_constraint=True,
        ),
        nullable=False,
        default=AIInteractionStatus.PENDING,
        server_default=AIInteractionStatus.PENDING.value,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
    )

    prompt = relationship(
        "AIPrompt",
        foreign_keys=[prompt_id],
    )
