from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.core.database import Base
from app.utils.enums import (
    KnowledgeDocumentStatus,
)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    file_reference: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[KnowledgeDocumentStatus] = mapped_column(
        SQLEnum(
            KnowledgeDocumentStatus,
            name="knowledge_document_status",
            native_enum=True,
        ),
        nullable=False,
        default=KnowledgeDocumentStatus.INACTIVE,
    )

    uploaded_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_knowledge_documents_active_name",
            "name",
            unique=True,
            postgresql_where="status = 'ACTIVE'",
        ),
        UniqueConstraint(
            "name",
            "version",
            name="uq_knowledge_documents_name_version",
        ),
    )

    uploader = relationship(
        "User",
    )
