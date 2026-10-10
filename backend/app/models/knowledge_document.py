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
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
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
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
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
        PostgreSQLUUID(as_uuid=True),
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

    uploader = relationship(
        "User",
    )

    tenant = relationship("Tenant")

    __table_args__ = (
        Index(
            "uq_knowledge_documents_active_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        UniqueConstraint(
            "tenant_id",
            "name",
            "version",
            name="uq_knowledge_documents_tenant_name_version",
        ),
    )
