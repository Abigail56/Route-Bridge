from sqlmodel import Session, select

from routebridge.models.core import Country, OperatingArea

TARGET_AREAS = (
    ("LAGOS", "Lagos"),
    ("ABUJA", "Abuja"),
    ("KANO", "Kano"),
    ("IBADAN", "Ibadan"),
)


def seed_reference_data(session: Session) -> None:
    nigeria = session.exec(select(Country).where(Country.iso_code == "NG")).first()
    if nigeria is None:
        nigeria = Country(iso_code="NG", name="Nigeria", default_currency="NGN", default_timezone="Africa/Lagos")
        session.add(nigeria)
        session.flush()
    for code, name in TARGET_AREAS:
        existing = session.exec(
            select(OperatingArea).where(
                OperatingArea.country_id == nigeria.id,
                OperatingArea.code == code,
            )
        ).first()
        if existing is None:
            session.add(OperatingArea(country_id=nigeria.id, code=code, name=name))
    session.commit()
