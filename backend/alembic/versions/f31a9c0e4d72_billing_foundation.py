# mypy: ignore-errors
"""Add commercial billing plans, assignments, invoices and immutable line items."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f31a9c0e4d72"
down_revision: Union[str, Sequence[str], None] = "e2f1c4b8a907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pricing_model", sa.String(length=24), nullable=False),
        sa.Column("billing_interval", sa.String(length=16), nullable=False),
        sa.Column(
            "subscription_tier",
            sa.String(length=32),
            server_default="starter",
            nullable=False,
        ),
        sa.Column(
            "currency", sa.String(length=3), server_default="USD", nullable=False
        ),
        sa.Column(
            "base_fee",
            sa.Numeric(precision=14, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "unit_rates",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "included_units",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "limits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "features",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default="ACTIVE", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pricing_model IN ('SUBSCRIPTION', 'USAGE_BASED', 'ENTERPRISE')",
            name="ck_billing_plans_pricing_model",
        ),
        sa.CheckConstraint(
            "billing_interval IN ('MONTHLY', 'ANNUAL', 'CUSTOM')",
            name="ck_billing_plans_billing_interval",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')", name="ck_billing_plans_status"
        ),
        sa.CheckConstraint(
            "base_fee >= 0", name="ck_billing_plans_base_fee_nonnegative"
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_billing_plans_currency_format"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_billing_plans_name"),
    )
    op.create_index("ix_billing_plans_status", "billing_plans", ["status"])

    op.add_column(
        "subscriptions",
        sa.Column("billing_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_subscriptions_billing_plan_id_billing_plans",
        "subscriptions",
        "billing_plans",
        ["billing_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_subscriptions_billing_plan_id", "subscriptions", ["billing_plan_id"]
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("billing_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=40), nullable=False),
        sa.Column("plan_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="DRAFT", nullable=False
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'PAID', 'VOID')", name="ck_invoices_status"
        ),
        sa.CheckConstraint("amount >= 0", name="ck_invoices_amount_nonnegative"),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_invoices_valid_period"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["billing_plan_id"], ["billing_plans.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        sa.UniqueConstraint(
            "tenant_id",
            "period_start",
            "period_end",
            name="uq_invoices_tenant_period",
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_invoices_id_tenant"),
    )
    op.create_index("ix_invoices_tenant_id", "invoices", ["tenant_id"])
    op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])
    op.create_index("ix_invoices_billing_plan_id", "invoices", ["billing_plan_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index(
        "ix_invoices_tenant_created", "invoices", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_invoices_tenant_period",
        "invoices",
        ["tenant_id", "period_start", "period_end"],
    )

    op.create_table(
        "invoice_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.String(length=240), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=True),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity >= 0", name="ck_invoice_line_items_quantity_nonnegative"
        ),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_invoice_line_items_unit_price_nonnegative"
        ),
        sa.CheckConstraint(
            "amount >= 0", name="ck_invoice_line_items_amount_nonnegative"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["invoice_id", "tenant_id"],
            ["invoices.id", "invoices.tenant_id"],
            name="fk_invoice_line_items_invoice_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_invoice_line_items_tenant_id", "invoice_line_items", ["tenant_id"]
    )
    op.create_index(
        "ix_invoice_line_items_tenant_invoice",
        "invoice_line_items",
        ["tenant_id", "invoice_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_invoice_line_items_tenant_invoice", table_name="invoice_line_items"
    )
    op.drop_index("ix_invoice_line_items_tenant_id", table_name="invoice_line_items")
    op.drop_table("invoice_line_items")

    op.drop_index("ix_invoices_tenant_period", table_name="invoices")
    op.drop_index("ix_invoices_tenant_created", table_name="invoices")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_billing_plan_id", table_name="invoices")
    op.drop_index("ix_invoices_subscription_id", table_name="invoices")
    op.drop_index("ix_invoices_tenant_id", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_subscriptions_billing_plan_id", table_name="subscriptions")
    op.drop_constraint(
        "fk_subscriptions_billing_plan_id_billing_plans",
        "subscriptions",
        type_="foreignkey",
    )
    op.drop_column("subscriptions", "billing_plan_id")
    op.drop_index("ix_billing_plans_status", table_name="billing_plans")
    op.drop_table("billing_plans")
