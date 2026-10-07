"""Checks the database layer against real PostgreSQL + PostGIS, using a throw-away database. The real database is never touched.

    docker compose exec -T api python -m routebridge.tools.db_selfcheck

It (1) creates an empty scratch database, (2) runs every migration from nothing up to the latest, (3) checks PostGIS answers and that
the spatial `driver.geog` column stays in step with latitude/longitude, (4) checks the nearest-driver query gives the same answer as
the plain-Python fallback, then (5) drops the scratch database.
"""
import os
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.core import Tenant
from routebridge.models.operations import Driver
from routebridge.services import geo
from routebridge.services.routing import haversine_km

# Lagos landmarks (latitude, longitude), nearest to Ikeja first
ORIGIN = (6.6018, 3.3515)
DRIVERS = [("Ikeja rider", 6.6050, 3.3490), ("Yaba rider", 6.5095, 3.3711), ("Lekki rider", 6.4474, 3.4723), ("Abuja rider", 9.0765, 7.3986)]


def main() -> int:
    real = make_url(get_settings().database_url)
    if not real.drivername.startswith("postgresql"):
        print("SKIP: this check needs PostgreSQL (the configured database is", real.drivername + ")")
        return 0
    name = f"rb_selfcheck_{uuid.uuid4().hex[:8]}"
    admin = create_engine(real.set(database="postgres"), isolation_level="AUTOCOMMIT")
    scratch_url = real.set(database=name)
    problems: list[str] = []
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    print(f"1/5 created scratch database {name}")
    try:
        migrated = subprocess.run([sys.executable, "-m", "routebridge.tools.migrate"], env={**os.environ, "ROUTEBRIDGE_DATABASE_URL": scratch_url.render_as_string(hide_password=False)}, capture_output=True, text=True, timeout=600)
        if migrated.returncode != 0:
            print("FAIL: migrations did not run from an empty database:\n" + (migrated.stderr or migrated.stdout)[-1500:])
            return 1
        engine = create_engine(scratch_url)
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = connection.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
            postgis = connection.execute(text("SELECT PostGIS_Version()")).scalar()
        print(f"2/5 migrations ran from empty to {head} ({tables} tables)")
        print(f"3/5 PostGIS {postgis} answers")

        with Session(engine) as session:
            tenant = Tenant(name="Self check")
            session.add(tenant)
            session.flush()
            for index, (label, lat, lng) in enumerate(DRIVERS):
                session.add(Driver(tenant_id=tenant.id, name=label, phone=f"+23480000000{index}", latitude=lat, longitude=lng))
            session.add(Driver(tenant_id=tenant.id, name="No position", phone="+234800000099"))
            session.commit()
            filled = session.execute(text("SELECT count(*) FROM driver WHERE geog IS NOT NULL")).scalar()
            if filled != len(DRIVERS):
                problems.append(f"driver.geog is filled for {filled} drivers, expected {len(DRIVERS)}")
            geo._postgis_columns.clear()
            if not geo.has_spatial_column(session, "driver"):
                problems.append("the spatial column driver.geog is missing, so the nearest-driver query would silently fall back to Python")
            spatial = geo.nearby_drivers(session, tenant.id, *ORIGIN, radius_m=30_000, limit=10)
            plain = sorted(((d.name, haversine_km(ORIGIN, (d.latitude, d.longitude)) * 1000) for d in session.exec(select(Driver).where(Driver.latitude.is_not(None))) if haversine_km(ORIGIN, (d.latitude, d.longitude)) * 1000 <= 30_000), key=lambda item: item[1])
            if [d.name for d, _ in spatial] != [n for n, _ in plain]:
                problems.append(f"nearest drivers differ: PostGIS {[d.name for d, _ in spatial]} versus plain {[n for n, _ in plain]}")
            for (driver, meters), (_, expected) in zip(spatial, plain):
                if abs(meters - expected) > 0.01 * expected + 25:  # PostGIS measures on the real spheroid, haversine on a sphere: within ~1% is expected
                    problems.append(f"{driver.name}: {meters:.0f} m by PostGIS but {expected:.0f} m by haversine")
            print(f"4/5 nearest drivers within 30 km: {[(d.name, round(m)) for d, m in spatial]}")
        engine.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        print(f"5/5 removed scratch database {name}")
    if problems:
        print("FAIL:\n - " + "\n - ".join(problems))
        return 1
    print("PASS: migrations, PostGIS and the spatial query all check out on real PostgreSQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
