from sqlalchemy import text

from routebridge.config.settings import get_settings
from routebridge.db.session import engine


def validate_production_database() -> None:
    settings = get_settings()
    if not settings.require_postgis:
        return
    if not settings.database_url.startswith(("postgresql", "postgres")):
        raise RuntimeError("PostgreSQL is required when ROUTEBRIDGE_REQUIRE_POSTGIS=true")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT PostGIS_Version()"))
        if not version.scalar():
            raise RuntimeError("PostGIS extension is not available")
