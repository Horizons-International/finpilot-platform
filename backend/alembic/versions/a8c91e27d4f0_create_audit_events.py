# mypy: ignore-errors

"""Create append-only, tenant-aware audit event records.

Revision ID: a8c91e27d4f0
Revises: 9f3c7a1e5b42
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a8c91e27d4f0"
down_revision: Union[str, Sequence[str], None] = "9f3c7a1e5b42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index(
        "ix_audit_events_tenant_timestamp",
        "audit_events",
        ["tenant_id", "timestamp"],
    )
    op.create_index(
        "ix_audit_events_tenant_action_timestamp",
        "audit_events",
        ["tenant_id", "action", "timestamp"],
    )
    op.create_index(
        "ix_audit_events_tenant_entity",
        "audit_events",
        ["tenant_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_audit_events_tenant_user_timestamp",
        "audit_events",
        ["tenant_id", "user_id", "timestamp"],
    )

    # PostgreSQL-level enforcement also blocks bulk UPDATE/DELETE operations that
    # bypass SQLAlchemy ORM events. The separate TRUNCATE trigger closes the
    # common table-wide deletion path. Database owners/superusers can still alter
    # DDL; production runtime credentials should not own this table/schema.
    op.execute("""
        CREATE FUNCTION finpilot_reject_audit_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only; % is prohibited', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER trg_audit_events_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION finpilot_reject_audit_event_mutation();
        """)
    op.execute("""
        CREATE TRIGGER trg_audit_events_no_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION finpilot_reject_audit_event_mutation();
        """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_truncate ON audit_events")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_audit_events_no_update_delete ON audit_events"
    )
    op.execute("DROP FUNCTION IF EXISTS finpilot_reject_audit_event_mutation()")
    op.drop_table("audit_events")
