"""delivery codes that staff pass on by hand

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("deliveryotp", sa.Column("relay_code", sa.String(length=12), nullable=True))
    op.add_column("deliveryotp", sa.Column("relayed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deliveryotp", sa.Column("relayed_by", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("deliveryotp", "relayed_by")
    op.drop_column("deliveryotp", "relayed_at")
    op.drop_column("deliveryotp", "relay_code")
