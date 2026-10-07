"""driver profile photo, merchant contact details

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("driver", sa.Column("photo", sa.String(length=60000), nullable=True))
    op.add_column("merchant", sa.Column("contact_phone", sa.String(length=30), nullable=True))
    op.add_column("merchant", sa.Column("contact_email", sa.String(length=320), nullable=True))
    op.add_column("merchant", sa.Column("notify_orders", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("merchant", "notify_orders")
    op.drop_column("merchant", "contact_email")
    op.drop_column("merchant", "contact_phone")
    op.drop_column("driver", "photo")
