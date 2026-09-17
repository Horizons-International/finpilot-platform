from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.models.user import User
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import AIPromptStatus


class AIPrompt(Base):
    __tablename__ = "ai_prompts"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    purpose: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    prompt_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[AIPromptStatus] = mapped_column(
        SQLEnum(
            AIPromptStatus,
            name="ai_prompt_status",
            create_constraint=True,
        ),
        nullable=False,
        default=AIPromptStatus.INACTIVE,
        server_default=AIPromptStatus.INACTIVE.value,
        index=True,
    )

    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    __table_args__ = (
        Index(
            "uq_ai_prompts_active_name",
            "name",
            unique=True,
            postgresql_where="status = 'ACTIVE'",
        ),
        UniqueConstraint(
            "name",
            "version",
            name="uq_ai_prompts_name_version",
        ),
    )

    # Relationships

    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by],
    )
