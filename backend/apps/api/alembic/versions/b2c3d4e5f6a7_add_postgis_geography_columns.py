"""add PostGIS geography columns and spatial indexes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6

Adds a generated `geog` geography(Point, 4326) column (derived from latitude/longitude, so the application keeps
writing plain coordinates) plus GiST indexes on `stop` and `driver`. On a PostgreSQL server without the PostGIS
extension installed, or on SQLite, this migration does nothing and the application falls back to haversine
distance in Python. Set ROUTEBRIDGE_REQUIRE_POSTGIS=true in production to refuse to start without PostGIS.
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")
TABLES = ("stop", "driver")
GEOG_EXPR = "ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography"


def _postgis_available(bind) -> bool:
    if bind.dialect.name != "postgresql":
        return False
    return bool(bind.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")).scalar())


def upgrade() -> None:
    bind = op.get_bind()
    if not _postgis_available(bind):
        logger.warning("PostGIS is not available; skipping spatial columns (haversine fallback will be used)")
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS geog geography(Point, 4326) GENERATED ALWAYS AS ({GEOG_EXPR}) STORED")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_geog ON {table} USING GIST (geog)")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_geog")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS geog")
