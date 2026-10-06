"""add users and tenant memberships

Revision ID: 9e5f6a7b8c9d
Revises: 8d4f5b6c7e8f
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "9e5f6a7b8c9d"
down_revision: Union[str, None] = "8d4f5b6c7e8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_user_id", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_clerk_user_id", "user", ["clerk_user_id"], unique=True)
    for name in ("email", "status"):
        op.create_index(f"ix_user_{name}", "user", [name], unique=False)
    op.create_table(
        "tenantmembership",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenantmembership_tenant_user"),
    )
    for name in ("tenant_id", "user_id", "role", "status", "merchant_id"):
        op.create_index(f"ix_tenantmembership_{name}", "tenantmembership", [name], unique=False)


def downgrade() -> None:
    for name in ("merchant_id", "status", "role", "user_id", "tenant_id"):
        op.drop_index(f"ix_tenantmembership_{name}", table_name="tenantmembership")
    op.drop_table("tenantmembership")
    for name in ("status", "email", "clerk_user_id"):
        op.drop_index(f"ix_user_{name}", table_name="user")
    op.drop_table("user")
