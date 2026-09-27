from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import InvestigationNoteType


class InvestigationNote(Base):
    __tablename__ = "investigation_notes"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "identity_verification_cases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    activity_type: Mapped[InvestigationNoteType] = mapped_column(
        Enum(
            InvestigationNoteType,
            name="investigation_note_type",
        ),
        nullable=False,
        index=True,
    )

    note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    attachment_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
