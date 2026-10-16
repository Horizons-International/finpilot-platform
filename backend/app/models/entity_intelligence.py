"""Tenant-scoped graph entities and directed relationships for investigations."""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EntityIntelligenceNode(Base):
    """A normalized graph node such as a customer, transaction, recipient or country."""

    __tablename__ = "entity_intelligence_nodes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "entity_type",
            "entity_key",
            name="uq_entity_intelligence_nodes_tenant_type_key",
        ),
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_entity_intelligence_nodes_risk_score_range",
        ),
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_entity_intelligence_nodes_risk_level",
        ),
        Index(
            "ix_entity_intelligence_nodes_tenant_type",
            "tenant_id",
            "entity_type",
        ),
        Index(
            "ix_entity_intelligence_nodes_tenant_source",
            "tenant_id",
            "source_type",
            "source_id",
        ),
        Index(
            "ix_entity_intelligence_nodes_tenant_risk",
            "tenant_id",
            "risk_score",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_entity_intelligence_nodes_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    risk_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LOW", server_default="LOW"
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant = relationship("Tenant")


class EntityIntelligenceRelationship(Base):
    """A directed, tenant-local edge between two graph nodes."""

    __tablename__ = "entity_intelligence_relationships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_entity_intelligence_relationships_tenant_edge_type",
        ),
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_entity_intelligence_relationships_risk_score_range",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_entity_intelligence_relationships_confidence_range",
        ),
        CheckConstraint(
            "source_entity_id <> target_entity_id",
            name="ck_entity_intelligence_relationships_no_self_edge",
        ),
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_entity_intelligence_relationships_risk_level",
        ),
        Index(
            "ix_entity_intelligence_relationships_tenant_source",
            "tenant_id",
            "source_entity_id",
        ),
        Index(
            "ix_entity_intelligence_relationships_tenant_target",
            "tenant_id",
            "target_entity_id",
        ),
        Index(
            "ix_entity_intelligence_relationships_tenant_risk",
            "tenant_id",
            "risk_score",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_entity_intelligence_relationships_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    source_entity_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "entity_intelligence_nodes.id",
            name="fk_entity_intelligence_relationships_source_entity_nodes",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    target_entity_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "entity_intelligence_nodes.id",
            name="fk_entity_intelligence_relationships_target_entity_nodes",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0"
    )
    risk_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LOW", server_default="LOW"
    )
    risk_indicators: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    observed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant = relationship("Tenant")
