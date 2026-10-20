"""the conversation under a problem a shop reports

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "claimmessage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("claim_id", sa.Uuid(), sa.ForeignKey("claim.id"), nullable=False),
        sa.Column("author", sa.String(length=10), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claimmessage_tenant_id", "claimmessage", ["tenant_id"])
    op.create_index("ix_claimmessage_claim_id", "claimmessage", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_claimmessage_claim_id", table_name="claimmessage")
    op.drop_index("ix_claimmessage_tenant_id", table_name="claimmessage")
    op.drop_table("claimmessage")
