"""where a person is: country, state, region (asked at sign-up)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("country", sa.String(length=2), nullable=True))
    op.add_column("user", sa.Column("state", sa.String(length=100), nullable=True))
    op.add_column("user", sa.Column("region", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "region")
    op.drop_column("user", "state")
    op.drop_column("user", "country")
