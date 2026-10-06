"""add transactional outbox events

Revision ID: 8d4f5b6c7e8f
Revises: 7c9e4a1d2b3c
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8d4f5b6c7e8f"
down_revision: Union[str, None] = "7c9e4a1d2b3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outboxevent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (("tenant_id", "tenant_id"), ("event_type", "event_type"), ("aggregate_type", "aggregate_type"), ("aggregate_id", "aggregate_id"), ("status", "status"), ("available_at", "available_at"), ("created_at", "created_at")):
        op.create_index(f"ix_outboxevent_{name}", "outboxevent", [column], unique=False)


def downgrade() -> None:
    for name in ("created_at", "available_at", "status", "aggregate_id", "aggregate_type", "event_type", "tenant_id"):
        op.drop_index(f"ix_outboxevent_{name}", table_name="outboxevent")
    op.drop_table("outboxevent")
