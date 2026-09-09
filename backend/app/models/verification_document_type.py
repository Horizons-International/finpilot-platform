from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import DocumentCategory


class VerificationDocumentType(Base):
    __tablename__ = "verification_document_types"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    category: Mapped[DocumentCategory] = mapped_column(
        SQLEnum(
            DocumentCategory,
            name="document_category",
            create_constraint=True,
        ),
        nullable=False,
        index=True,
    )

    supported_countries: Mapped[list[str]] = mapped_column(
        ARRAY(String(2)),
        nullable=False,
        default=list,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "name",
            name="uq_verification_document_types_name",
        ),
    )
