"""a person's own registration as a Dispatcher: phone and photo

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("phone", sa.String(length=30), nullable=True))
    op.add_column("user", sa.Column("photo", sa.String(length=60000), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "photo")
    op.drop_column("user", "phone")
