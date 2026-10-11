"""the zone a shop is in

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("merchantprofile", sa.Column("service_zone_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("merchantprofile", "service_zone_id")
