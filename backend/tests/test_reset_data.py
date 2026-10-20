"""The reset tool keeps one owner, their workspace and its zones, and clears everything else, on its own throw-away database."""
from uuid import uuid4

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

import routebridge.db.session  # noqa: F401  (registers every table)
from routebridge.config.settings import get_settings
from routebridge.models.access import TenantMembership, User
from routebridge.models.catalog import RateCard, ServiceZone
from routebridge.models.core import Country, OperatingArea, Tenant
from routebridge.models.operations import Driver
from routebridge.models.orders import Merchant
from routebridge.models.reliability import AuditEvent
from routebridge.tools import reset_data


def _seed(engine):
    with Session(engine) as s:
        country = Country(iso_code="NG", name="Nigeria")
        s.add(country)
        s.flush()
        area = OperatingArea(country_id=country.id, code="LAG", name="Lagos")
        mine, other, history = Tenant(name="RouteBridge"), Tenant(name="Old Test Co"), Tenant(name="Audited Co")
        owner, stranger = User(clerk_user_id="user_owner", email="Owner@Example.com"), User(clerk_user_id="user_other", email="x@example.com")
        s.add_all([area, mine, other, history, owner, stranger])
        s.flush()
        zone = ServiceZone(tenant_id=mine.id, operating_area_id=area.id, code="LAG", name="Lagos")
        s.add_all([
            zone, ServiceZone(tenant_id=other.id, operating_area_id=area.id, code="X", name="Elsewhere"),
            TenantMembership(tenant_id=mine.id, user_id=owner.id, role="tenant_owner"),
            TenantMembership(tenant_id=mine.id, user_id=stranger.id, role="driver"),
            Merchant(tenant_id=mine.id, name="Shop"), Driver(tenant_id=mine.id, name="Rider", phone="+2348011111111"),
            Merchant(tenant_id=other.id, name="Other shop"),
            AuditEvent(tenant_id=history.id, event_type="x", aggregate_type="x", aggregate_id=uuid4()),
        ])
        s.flush()
        s.add(RateCard(tenant_id=mine.id, service_zone_id=zone.id, name="Lagos"))
        s.commit()


def test_dry_run_changes_nothing_and_yes_keeps_only_the_owner(tmp_path, monkeypatch, capsys) -> None:
    url = f"sqlite:///{tmp_path / 'reset.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    _seed(engine)
    monkeypatch.setattr(get_settings(), "database_url", url)

    reset_data.main(["--keep-email", "owner@example.com"])
    assert "Nothing changed" in capsys.readouterr().out
    with Session(engine) as s:
        assert len(s.exec(select(User)).all()) == 2

    reset_data.main(["--keep-email", "owner@example.com", "--yes"])
    with Session(engine) as s:
        assert [u.clerk_user_id for u in s.exec(select(User)).all()] == ["user_owner"]
        assert [m.role for m in s.exec(select(TenantMembership)).all()] == ["tenant_owner"]
        assert {t.name: t.status for t in s.exec(select(Tenant)).all()} == {"RouteBridge": "active", "Audited Co": "suspended"}
        assert [z.name for z in s.exec(select(ServiceZone)).all()] == ["Lagos"]
        assert not s.exec(select(Merchant)).all() and not s.exec(select(Driver)).all() and not s.exec(select(RateCard)).all()
        assert len(s.exec(select(AuditEvent)).all()) == 1  # history stays


def test_an_unknown_email_changes_nothing(tmp_path, monkeypatch) -> None:
    url = f"sqlite:///{tmp_path / 'reset.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    _seed(engine)
    monkeypatch.setattr(get_settings(), "database_url", url)
    try:
        reset_data.main(["--keep-email", "nobody@example.com", "--yes"])
        raise AssertionError("should have stopped")
    except SystemExit as stop:
        assert "found 0" in str(stop)
    with Session(engine) as s:
        assert len(s.exec(select(User)).all()) == 2


def test_the_owner_can_be_named_by_clerk_user_id(tmp_path, monkeypatch) -> None:
    url = f"sqlite:///{tmp_path / 'reset.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    _seed(engine)
    monkeypatch.setattr(get_settings(), "database_url", url)
    reset_data.main(["--keep-user", "user_owner", "--yes"])
    with Session(engine) as s:
        assert [u.clerk_user_id for u in s.exec(select(User)).all()] == ["user_owner"]
