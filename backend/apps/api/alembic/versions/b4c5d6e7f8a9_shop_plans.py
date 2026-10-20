"""a shop's own plan, and which shop paid

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchantplan",
        sa.Column("merchant_id", sa.Uuid(), sa.ForeignKey("merchant.id"), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_merchantplan_tenant_id", "merchantplan", ["tenant_id"])
    with op.batch_alter_table("billingpayment") as batch:  # batch form so SQLite (which cannot add a foreign key in place) works too
        batch.add_column(sa.Column("merchant_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_billingpayment_merchant_id", "merchant", ["merchant_id"], ["id"])
    op.create_index("ix_billingpayment_merchant_id", "billingpayment", ["merchant_id"])


def downgrade() -> None:
    op.drop_index("ix_billingpayment_merchant_id", table_name="billingpayment")
    with op.batch_alter_table("billingpayment") as batch:
        batch.drop_constraint("fk_billingpayment_merchant_id", type_="foreignkey")
        batch.drop_column("merchant_id")
    op.drop_index("ix_merchantplan_tenant_id", table_name="merchantplan")
    op.drop_table("merchantplan")
