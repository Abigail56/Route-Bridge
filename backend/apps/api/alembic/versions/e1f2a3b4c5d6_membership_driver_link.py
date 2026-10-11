"""link a dispatcher (rider) login to its rider record

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenantmembership", sa.Column("driver_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_tenantmembership_driver_id"), "tenantmembership", ["driver_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_tenantmembership_driver_id"), table_name="tenantmembership")
    op.drop_column("tenantmembership", "driver_id")
