# mypy: ignore-errors
"""Create tenant-scoped entity-intelligence graph storage."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1a4e6f8d2b9"
down_revision: Union[str, Sequence[str], None] = "f3a91c7d5e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entity_intelligence_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_key", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("risk_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "risk_level", sa.String(length=16), server_default="LOW", nullable=False
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_entity_intelligence_nodes_risk_score_range",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_entity_intelligence_nodes_risk_level",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_entity_intelligence_nodes_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "entity_type",
            "entity_key",
            name="uq_entity_intelligence_nodes_tenant_type_key",
        ),
    )
    op.create_index(
        "ix_entity_intelligence_nodes_tenant_id",
        "entity_intelligence_nodes",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_intelligence_nodes_tenant_type",
        "entity_intelligence_nodes",
        ["tenant_id", "entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_entity_intelligence_nodes_tenant_source",
        "entity_intelligence_nodes",
        ["tenant_id", "source_type", "source_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_intelligence_nodes_tenant_risk",
        "entity_intelligence_nodes",
        ["tenant_id", "risk_score"],
        unique=False,
    )

    op.create_table(
        "entity_intelligence_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("risk_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "risk_level", sa.String(length=16), server_default="LOW", nullable=False
        ),
        sa.Column(
            "risk_indicators",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("observed_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_entity_intelligence_relationships_risk_score_range",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_entity_intelligence_relationships_confidence_range",
        ),
        sa.CheckConstraint(
            "source_entity_id <> target_entity_id",
            name="ck_entity_intelligence_relationships_no_self_edge",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_entity_intelligence_relationships_risk_level",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_entity_intelligence_relationships_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_entity_id"],
            ["entity_intelligence_nodes.id"],
            name="fk_entity_intelligence_relationships_source_entity_nodes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"],
            ["entity_intelligence_nodes.id"],
            name="fk_entity_intelligence_relationships_target_entity_nodes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_entity_intelligence_relationships_tenant_edge_type",
        ),
    )
    op.create_index(
        "ix_entity_intelligence_relationships_tenant_id",
        "entity_intelligence_relationships",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_intelligence_relationships_tenant_source",
        "entity_intelligence_relationships",
        ["tenant_id", "source_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_intelligence_relationships_tenant_target",
        "entity_intelligence_relationships",
        ["tenant_id", "target_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_intelligence_relationships_tenant_risk",
        "entity_intelligence_relationships",
        ["tenant_id", "risk_score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entity_intelligence_relationships_tenant_risk",
        table_name="entity_intelligence_relationships",
    )
    op.drop_index(
        "ix_entity_intelligence_relationships_tenant_target",
        table_name="entity_intelligence_relationships",
    )
    op.drop_index(
        "ix_entity_intelligence_relationships_tenant_source",
        table_name="entity_intelligence_relationships",
    )
    op.drop_index(
        "ix_entity_intelligence_relationships_tenant_id",
        table_name="entity_intelligence_relationships",
    )
    op.drop_table("entity_intelligence_relationships")
    op.drop_index(
        "ix_entity_intelligence_nodes_tenant_risk",
        table_name="entity_intelligence_nodes",
    )
    op.drop_index(
        "ix_entity_intelligence_nodes_tenant_source",
        table_name="entity_intelligence_nodes",
    )
    op.drop_index(
        "ix_entity_intelligence_nodes_tenant_type",
        table_name="entity_intelligence_nodes",
    )
    op.drop_index(
        "ix_entity_intelligence_nodes_tenant_id",
        table_name="entity_intelligence_nodes",
    )
    op.drop_table("entity_intelligence_nodes")
