import os

import pytest
from sqlalchemy import create_engine, text

POSTGRES_URL = os.getenv("ROUTEBRIDGE_POSTGRES_TEST_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="Set ROUTEBRIDGE_POSTGRES_TEST_URL to run PostgreSQL/PostGIS integration tests")
def test_postgresql_postgis_extension_and_connection() -> None:
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version()" )).scalar()
        assert connection.execute(text("SELECT PostGIS_Version()" )).scalar()
