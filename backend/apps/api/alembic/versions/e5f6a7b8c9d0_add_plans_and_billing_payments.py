"""add tenant plan and billing payments

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # a test run once created this table by itself; an empty leftover must not stop the upgrade
    leftover = sa.inspect(op.get_bind()).has_table("billingpayment")
    if leftover:
        op.drop_table("billingpayment")
    op.add_column("tenant", sa.Column("plan", sa.String(length=20), nullable=False, server_default="trial"))
    op.add_column("tenant", sa.Column("plan_valid_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "billingpayment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("amount_kobo", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payer_email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billingpayment_tenant_id", "billingpayment", ["tenant_id"])
    op.create_index("ix_billingpayment_reference", "billingpayment", ["reference"], unique=True)
    op.create_index("ix_billingpayment_status", "billingpayment", ["status"])


def downgrade() -> None:
    op.drop_table("billingpayment")
    op.drop_column("tenant", "plan_valid_until")
    op.drop_column("tenant", "plan")
