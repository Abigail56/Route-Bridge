from fastapi.testclient import TestClient
from sqlmodel import Session

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.operations import Driver
from routebridge.services.geo import has_spatial_column, nearby_drivers

client = TestClient(app)
create_db_and_tables()

# Ikeja, Lagos and points at increasing distance from it
IKEJA = (6.6018, 3.3515)


def _tenant_with_drivers():
    with Session(engine) as session:
        tenant = Tenant(name="Geo Tenant")
        session.add(tenant)
        session.flush()
        drivers = [
            Driver(tenant_id=tenant.id, name="Near", phone="08000000001", latitude=6.6050, longitude=3.3540),  # ~0.5 km
            Driver(tenant_id=tenant.id, name="Mid", phone="08000000002", latitude=6.6500, longitude=3.3900),  # ~6.5 km
            Driver(tenant_id=tenant.id, name="Far", phone="08000000003", latitude=6.4500, longitude=3.4000),  # ~18 km
            Driver(tenant_id=tenant.id, name="Offline", phone="08000000004", latitude=6.6020, longitude=3.3520, status="offline"),
            Driver(tenant_id=tenant.id, name="NoGps", phone="08000000005"),
        ]
        session.add_all(drivers)
        session.commit()
        return tenant.id


def test_nearby_drivers_endpoint_sorted_and_filtered() -> None:
    tenant_id = _tenant_with_drivers()
    res = client.get(f"/api/v1/tenants/{tenant_id}/drivers/nearby", params={"lat": IKEJA[0], "lng": IKEJA[1], "radius_km": 10})
    assert res.status_code == 200, res.text
    rows = res.json()
    assert [r["name"] for r in rows] == ["Near", "Mid"]  # offline, no-GPS and out-of-radius drivers are excluded
    assert 300 < rows[0]["distance_m"] < 800 and 5000 < rows[1]["distance_m"] < 8000
    wide = client.get(f"/api/v1/tenants/{tenant_id}/drivers/nearby", params={"lat": IKEJA[0], "lng": IKEJA[1], "radius_km": 30}).json()
    assert [r["name"] for r in wide] == ["Near", "Mid", "Far"]
    assert client.get(f"/api/v1/tenants/{tenant_id}/drivers/nearby", params={"lat": 123, "lng": 0}).status_code == 422


def test_spatial_path_matches_python_fallback_when_postgis_is_present() -> None:
    tenant_id = _tenant_with_drivers()
    with Session(engine) as session:
        spatial = has_spatial_column(session, "driver")
        if session.bind.dialect.name == "postgresql":
            from sqlalchemy import text

            available = bool(session.exec(text("SELECT 1 FROM pg_available_extensions WHERE name='postgis'")).first())
            assert spatial == available  # the migration adds the column exactly when PostGIS exists
        names = [d.name for d, _ in nearby_drivers(session, tenant_id, *IKEJA, radius_m=10_000)]
        assert names == ["Near", "Mid"]
