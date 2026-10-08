# mypy: ignore-errors

"""add multi tenant foundation

Revision ID: 3648976d844a
Revises: 5967cb3a1269
Create Date: 2026-10-07 20:14:29.471001

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3648976d844a"
down_revision: Union[str, Sequence[str], None] = "5967cb3a1269"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    tenant_status = postgresql.ENUM(
        "ACTIVE",
        "SUSPENDED",
        "INACTIVE",
        name="tenant_status",
        create_type=False,
    )

    tenant_status.create(
        op.get_bind(),
        checkfirst=True,
    )

    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "code",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "status",
            tenant_status,
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "code",
            name="uq_tenants_code",
        ),
    )

    op.create_index(
        "ix_tenants_code",
        "tenants",
        ["code"],
        unique=False,
    )

    op.create_index(
        "ix_tenants_status",
        "tenants",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_tenants_created_at",
        "tenants",
        ["created_at"],
        unique=False,
    )

    op.execute(
        sa.text("""
            INSERT INTO tenants (
                id,
                name,
                code,
                status
            )
            VALUES (
                CAST(:tenant_id AS UUID),
                :name,
                :code,
                'ACTIVE'
            )
            """).bindparams(
            sa.bindparam(
                "tenant_id",
                DEFAULT_TENANT_ID,
                type_=postgresql.UUID(as_uuid=True),
            ),
            sa.bindparam(
                "name",
                "Default Tenant",
            ),
            sa.bindparam(
                "code",
                "DEFAULT",
            ),
        )
    )

    # ---------------------------------------------------------
    # Users
    # ---------------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.execute(
        sa.text("""
            UPDATE users
            SET tenant_id = CAST(:tenant_id AS UUID)
            WHERE tenant_id IS NULL
            """).bindparams(
            tenant_id=DEFAULT_TENANT_ID,
        )
    )

    # Explicitly set the configured admin if the environment-based
    # admin already exists in the database.
    op.alter_column(
        "users",
        "tenant_id",
        nullable=False,
    )

    op.create_foreign_key(
        "fk_users_tenant_id",
        "users",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_users_tenant_id",
        "users",
        ["tenant_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # Customers
    # ---------------------------------------------------------

    op.add_column(
        "customers",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.execute(
        sa.text("""
            UPDATE customers
            SET tenant_id = CAST(:tenant_id AS UUID)
            WHERE tenant_id IS NULL
            """).bindparams(
            tenant_id=DEFAULT_TENANT_ID,
        )
    )

    op.alter_column(
        "customers",
        "tenant_id",
        nullable=False,
    )

    op.create_foreign_key(
        "fk_customers_tenant_id",
        "customers",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_customers_tenant_id",
        "customers",
        ["tenant_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # Workflows
    # ---------------------------------------------------------

    op.add_column(
        "workflows",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.execute(
        sa.text("""
            UPDATE workflows
            SET tenant_id = CAST(:tenant_id AS UUID)
            WHERE tenant_id IS NULL
            """).bindparams(
            tenant_id=DEFAULT_TENANT_ID,
        )
    )

    op.alter_column(
        "workflows",
        "tenant_id",
        nullable=False,
    )

    op.drop_constraint(
        "uq_workflows_name",
        "workflows",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_workflows_tenant_name",
        "workflows",
        ["tenant_id", "name"],
    )

    op.create_foreign_key(
        "fk_workflows_tenant_id",
        "workflows",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_workflows_tenant_id",
        "workflows",
        ["tenant_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # System configurations
    # ---------------------------------------------------------

    op.add_column(
        "system_configurations",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.execute(
        sa.text("""
            UPDATE system_configurations
            SET tenant_id = CAST(:tenant_id AS UUID)
            WHERE tenant_id IS NULL
            """).bindparams(
            tenant_id=DEFAULT_TENANT_ID,
        )
    )

    op.alter_column(
        "system_configurations",
        "tenant_id",
        nullable=False,
    )

    op.drop_constraint(
        "uq_system_configurations_key",
        "system_configurations",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_system_configurations_tenant_key",
        "system_configurations",
        ["tenant_id", "key"],
    )

    op.create_foreign_key(
        "fk_system_configurations_tenant_id",
        "system_configurations",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_system_configurations_tenant_id",
        "system_configurations",
        ["tenant_id"],
        unique=False,
    )

    op.drop_index(
        "ix_system_configurations_key",
        table_name="system_configurations",
    )

    # ---------------------------------------------------------
    # Report exports
    # ---------------------------------------------------------

    op.add_column(
        "report_exports",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.execute(
        sa.text(  # fmt: skip
            """  
            UPDATE report_exports re
            SET tenant_id = u.tenant_id
            FROM users u
            WHERE re.requested_by = u.id
            """
        )
    )

    op.execute(
        sa.text("""
            UPDATE report_exports
            SET tenant_id = CAST(:tenant_id AS UUID)
            WHERE tenant_id IS NULL
            """).bindparams(
            tenant_id=DEFAULT_TENANT_ID,
        )
    )

    op.alter_column(
        "report_exports",
        "tenant_id",
        nullable=False,
    )

    op.create_foreign_key(
        "fk_report_exports_tenant_id",
        "report_exports",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_report_exports_tenant_id",
        "report_exports",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_exports_tenant_id",
        table_name="report_exports",
    )

    op.drop_constraint(
        "fk_report_exports_tenant_id",
        "report_exports",
        type_="foreignkey",
    )

    op.drop_column(
        "report_exports",
        "tenant_id",
    )

    op.drop_index(
        "ix_system_configurations_tenant_id",
        table_name="system_configurations",
    )

    op.drop_constraint(
        "fk_system_configurations_tenant_id",
        "system_configurations",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_system_configurations_tenant_key",
        "system_configurations",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_system_configurations_key",
        "system_configurations",
        ["key"],
    )

    op.drop_column(
        "system_configurations",
        "tenant_id",
    )

    op.drop_index(
        "ix_workflows_tenant_id",
        table_name="workflows",
    )

    op.drop_constraint(
        "fk_workflows_tenant_id",
        "workflows",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_workflows_tenant_name",
        "workflows",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_workflows_name",
        "workflows",
        ["name"],
    )

    op.drop_column(
        "workflows",
        "tenant_id",
    )

    op.drop_index(
        "ix_customers_tenant_id",
        table_name="customers",
    )

    op.drop_constraint(
        "fk_customers_tenant_id",
        "customers",
        type_="foreignkey",
    )

    op.drop_column(
        "customers",
        "tenant_id",
    )

    op.drop_index(
        "ix_users_tenant_id",
        table_name="users",
    )

    op.drop_constraint(
        "fk_users_tenant_id",
        "users",
        type_="foreignkey",
    )

    op.drop_column(
        "users",
        "is_platform_admin",
    )

    op.drop_column(
        "users",
        "tenant_id",
    )

    op.drop_index(
        "ix_tenants_created_at",
        table_name="tenants",
    )

    op.drop_index(
        "ix_tenants_status",
        table_name="tenants",
    )

    op.drop_index(
        "ix_tenants_code",
        table_name="tenants",
    )

    op.drop_table("tenants")

    postgresql.ENUM(
        "ACTIVE",
        "SUSPENDED",
        "INACTIVE",
        name="tenant_status",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )

    op.create_index(
        "ix_system_configurations_key",
        "system_configurations",
        ["key"],
        unique=True,
    )
