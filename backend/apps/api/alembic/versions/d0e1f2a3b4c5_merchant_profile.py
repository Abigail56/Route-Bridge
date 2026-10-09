"""shop registration details (address, contact person, bank account)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchantprofile",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("contact_person", sa.String(length=200), nullable=True),
        sa.Column("address_line", sa.String(length=300), nullable=True),
        sa.Column("landmark", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("bank_name", sa.String(length=120), nullable=True),
        sa.Column("account_number", sa.String(length=20), nullable=True),
        sa.Column("account_name", sa.String(length=200), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id", name="uq_merchantprofile_merchant"),
    )
    op.create_index(op.f("ix_merchantprofile_tenant_id"), "merchantprofile", ["tenant_id"])
    op.create_index(op.f("ix_merchantprofile_merchant_id"), "merchantprofile", ["merchant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_merchantprofile_merchant_id"), table_name="merchantprofile")
    op.drop_index(op.f("ix_merchantprofile_tenant_id"), table_name="merchantprofile")
    op.drop_table("merchantprofile")
