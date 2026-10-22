"""join requests: a new shop or rider sends their user id to the Admin from the "not linked yet" screen

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "joinrequest",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("shop_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_joinrequest_tenant_user"),
    )
    op.create_index("ix_joinrequest_tenant_id", "joinrequest", ["tenant_id"])
    op.create_index("ix_joinrequest_user_id", "joinrequest", ["user_id"])
    op.create_index("ix_joinrequest_status", "joinrequest", ["status"])
    op.create_index("ix_joinrequest_sent_at", "joinrequest", ["sent_at"])


def downgrade() -> None:
    op.drop_table("joinrequest")
