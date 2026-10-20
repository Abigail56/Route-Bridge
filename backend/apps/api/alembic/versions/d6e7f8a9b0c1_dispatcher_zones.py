"""the zones a Dispatcher works in

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("rider_zones", sa.String(length=1000), nullable=True))
    op.create_table(
        "driverzone",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("driver_id", sa.Uuid(), sa.ForeignKey("driver.id"), nullable=False),
        sa.Column("service_zone_id", sa.Uuid(), sa.ForeignKey("servicezone.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("driver_id", "service_zone_id", name="uq_driverzone_driver_zone"),
    )
    op.create_index("ix_driverzone_tenant_id", "driverzone", ["tenant_id"])
    op.create_index("ix_driverzone_driver_id", "driverzone", ["driver_id"])
    op.create_index("ix_driverzone_service_zone_id", "driverzone", ["service_zone_id"])


def downgrade() -> None:
    op.drop_index("ix_driverzone_service_zone_id", table_name="driverzone")
    op.drop_index("ix_driverzone_driver_id", table_name="driverzone")
    op.drop_index("ix_driverzone_tenant_id", table_name="driverzone")
    op.drop_table("driverzone")
    op.drop_column("user", "rider_zones")
