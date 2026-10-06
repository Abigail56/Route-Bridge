"""Spatial queries: PostGIS when the `geog` columns exist, haversine in Python otherwise."""
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, select

from routebridge.models.operations import Driver
from routebridge.services.routing import haversine_km

_postgis_columns: dict[str, bool] = {}


def has_spatial_column(session: Session, table: str) -> bool:
    """True when `<table>.geog` exists (PostgreSQL + PostGIS migration applied)."""
    if session.bind.dialect.name != "postgresql":
        return False
    cached = _postgis_columns.get(table)
    if cached is None:
        cached = bool(session.exec(text("SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = 'geog'").bindparams(t=table)).first())
        _postgis_columns[table] = cached
    return cached


def nearby_drivers(session: Session, tenant_id: UUID, latitude: float, longitude: float, radius_m: float, limit: int = 10) -> list[tuple[Driver, float]]:
    """Available drivers within `radius_m` metres, nearest first, as (driver, distance in metres)."""
    if has_spatial_column(session, "driver"):
        rows = session.exec(
            text(
                """
                SELECT id, ST_Distance(geog, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) AS meters
                FROM driver
                WHERE tenant_id = :tenant AND status = 'available' AND geog IS NOT NULL
                  AND ST_DWithin(geog, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius)
                ORDER BY meters LIMIT :limit
                """
            ).bindparams(tenant=tenant_id, lat=latitude, lng=longitude, radius=radius_m, limit=limit)
        ).all()
        drivers = {d.id: d for d in session.exec(select(Driver).where(Driver.id.in_([r[0] for r in rows]))).all()} if rows else {}
        return [(drivers[r[0]], float(r[1])) for r in rows if r[0] in drivers]
    candidates = session.exec(select(Driver).where(Driver.tenant_id == tenant_id, Driver.status == "available", Driver.latitude.is_not(None), Driver.longitude.is_not(None))).all()
    scored = [(d, haversine_km((latitude, longitude), (d.latitude, d.longitude)) * 1000) for d in candidates]
    return sorted([item for item in scored if item[1] <= radius_m], key=lambda item: item[1])[:limit]
