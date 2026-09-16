from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.models.ai_prompt import AIPrompt
from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import AIFunction


class AIPromptAssignment(Base):
    __tablename__ = "ai_prompt_assignments"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    ai_function: Mapped[AIFunction] = mapped_column(
        SQLEnum(
            AIFunction,
            name="ai_function",
            create_constraint=True,
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    prompt_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_prompts.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    prompt: Mapped["AIPrompt"] = relationship(
        "AIPrompt",
        foreign_keys=[prompt_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "ai_function",
            name="uq_ai_prompt_assignments_function",
        ),
    )
