"""add webhook receipt idempotency

Revision ID: 7c9e4a1d2b3c
Revises: 6f7ec0865d57
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7c9e4a1d2b3c"
down_revision: Union[str, None] = "6f7ec0865d57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhookreceipt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
    )
    op.create_index("ix_webhookreceipt_provider", "webhookreceipt", ["provider"], unique=False)
    op.create_index("ix_webhookreceipt_event_id", "webhookreceipt", ["event_id"], unique=False)
    op.create_index("ix_webhookreceipt_status", "webhookreceipt", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_webhookreceipt_status", table_name="webhookreceipt")
    op.drop_index("ix_webhookreceipt_event_id", table_name="webhookreceipt")
    op.drop_index("ix_webhookreceipt_provider", table_name="webhookreceipt")
    op.drop_table("webhookreceipt")
