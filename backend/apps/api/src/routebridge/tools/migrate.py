"""Apply database migrations safely when many replicas start at once.

`python -m routebridge.tools.migrate` takes a PostgreSQL advisory lock, runs `alembic upgrade head`, and releases the
lock. Concurrent starters queue on the lock; once the first finishes the rest find nothing to do. Run it as an init
container (Kubernetes) or before the server in docker compose. Migrations must stay backward compatible with the
previous release so a rolling deploy can serve both versions during the switch.
"""
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from routebridge.config.settings import get_settings

LOCK_KEY = 727_274_001  # arbitrary, stable application-wide advisory lock id
logger = logging.getLogger("routebridge.migrate")


def _alembic_config() -> Config:
    candidates = [Path.cwd() / "alembic.ini", Path(__file__).resolve().parents[3] / "alembic.ini"]
    for path in candidates:
        if path.exists():
            config = Config(str(path))
            config.set_main_option("script_location", str(path.parent / "alembic"))
            return config
    raise FileNotFoundError("alembic.ini not found (run from the API directory)")


def migrate() -> None:
    settings = get_settings()
    config = _alembic_config()
    if not settings.database_url.startswith(("postgresql", "postgres")):
        command.upgrade(config, "head")  # SQLite (dev/test): single process, no lock needed
        return
    engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as lock_connection:
        logger.info("waiting for the migration lock")
        lock_connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
        try:
            command.upgrade(config, "head")
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
    engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        migrate()
    except Exception:
        logger.exception("migration failed")
        sys.exit(1)
    logger.info("migrations are up to date")
