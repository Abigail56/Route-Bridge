from sqlalchemy import delete, text
from sqlmodel import Session


def reset_data(session: Session, models: tuple) -> None:
    """Clear tenant data between tests.

    On PostgreSQL the audit table is append-only (row trigger), so row-level DELETEs are rejected by design;
    TRUNCATE ... CASCADE is not a row operation and clears tenants plus everything that references them.
    Reference data (countries, operating areas) is kept.
    """
    if session.bind.dialect.name == "postgresql":
        session.exec(text("TRUNCATE tenant CASCADE"))
    else:
        for model in models:
            session.exec(delete(model))
    session.commit()


def post_order(client, url: str, **kwargs):
    """Place an order the way a shop's integration would (staff cannot create orders any more), for tests that need an order to work on."""
    from routebridge.auth.authorization import no_staff_orders
    from routebridge.main import app

    app.dependency_overrides[no_staff_orders] = lambda: None
    try:
        return client.post(url, **kwargs)
    finally:
        app.dependency_overrides.pop(no_staff_orders, None)


def make_zone(tenant_id, name: str = "Lagos") -> str:
    """A delivery zone for a company, made straight in the database (the way the owner's Settings > Zones would)."""
    from sqlmodel import select

    from routebridge.db.session import engine
    from routebridge.models.catalog import ServiceZone
    from routebridge.models.core import Country, OperatingArea

    with Session(engine) as session:
        country = session.exec(select(Country).where(Country.iso_code == "ZZ")).first()
        if country is None:
            country = Country(iso_code="ZZ", name="Testland")
            session.add(country)
            session.flush()
        area = session.exec(select(OperatingArea).where(OperatingArea.code == "TST")).first()
        if area is None:
            area = OperatingArea(country_id=country.id, code="TST", name="Test City")
            session.add(area)
            session.flush()
        from uuid import UUID

        zone = ServiceZone(tenant_id=UUID(str(tenant_id)), operating_area_id=area.id, code=name[:6].upper() or "Z", name=name)
        session.add(zone)
        session.commit()
        return str(zone.id)
