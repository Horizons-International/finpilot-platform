import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import CommunicationChannel, CommunicationStatus


class CommunicationLog(Base):
    __tablename__ = "communication_logs"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    recipient: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    channel: Mapped[CommunicationChannel] = mapped_column(
        Enum(
            CommunicationChannel,
            name="communication_channel",
        ),
        nullable=False,
        index=True,
    )

    template_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    status: Mapped[CommunicationStatus] = mapped_column(
        Enum(
            CommunicationStatus,
            name="communication_status",
        ),
        nullable=False,
        default=CommunicationStatus.PENDING,
        server_default=CommunicationStatus.PENDING.value,
        index=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
