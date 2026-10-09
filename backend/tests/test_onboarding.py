from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.access import User
from routebridge.models.core import Country, OperatingArea

client = TestClient(app)
create_db_and_tables()


@pytest.fixture
def as_clerk_user():
    """Pretend the request carries a verified Clerk token for the given subject (production-style: no dev bypass)."""
    settings = get_settings()
    old = (settings.require_clerk_auth, list(settings.platform_admin_subjects))
    settings.require_clerk_auth = True

    def sign_in(subject: str, admin: bool = False, **claims):
        app.dependency_overrides[get_optional_user] = lambda: ClerkUser(subject, claims)
        settings.platform_admin_subjects[:] = [subject] if admin else []

    yield sign_in
    app.dependency_overrides.pop(get_optional_user, None)
    settings.require_clerk_auth = old[0]
    settings.platform_admin_subjects[:] = old[1]


def _area() -> str:
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
        session.commit()
        return str(area.id)


def test_first_sign_in_is_provisioned_automatically_with_no_workspaces(as_clerk_user) -> None:
    subject = f"user_{uuid4().hex[:16]}"
    as_clerk_user(subject, email="new.person@example.test", name="New Person")
    res = client.get("/api/v1/auth/me/profile")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tenants"] == [] and body["is_platform_admin"] is False and body["email"] == "new.person@example.test"
    with Session(engine) as session:
        assert session.exec(select(User).where(User.clerk_user_id == subject)).one().full_name == "New Person"
    # the older endpoint no longer errors for a brand-new user either
    assert client.get("/api/v1/auth/me/tenants").json() == []


def test_platform_admin_can_set_up_a_workspace_end_to_end(as_clerk_user) -> None:
    subject = f"user_{uuid4().hex[:16]}"
    as_clerk_user(subject, admin=True, name="Founder")
    assert client.get("/api/v1/auth/me/profile").json()["is_platform_admin"] is True

    tenant = client.post("/api/v1/admin/tenants", json={"name": "Lagos Dispatch Ltd"})
    assert tenant.status_code == 201, tenant.text
    tid = tenant.json()["id"]
    profile = client.get("/api/v1/auth/me/profile").json()
    assert [(t["tenant_id"], t["role"]) for t in profile["tenants"]] == [(tid, "tenant_owner")]  # creator is the owner

    merchant = client.post(f"/api/v1/admin/tenants/{tid}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "HealthPlus Pharmacy"})
    assert merchant.status_code == 201, merchant.text
    assert [m["name"] for m in client.get(f"/api/v1/admin/tenants/{tid}/merchants").json()] == ["HealthPlus Pharmacy"]

    area_id = _area()
    areas = client.get("/api/v1/admin/operating-areas").json()
    assert any(a["id"] == area_id for a in areas)
    zone = client.post(f"/api/v1/admin/tenants/{tid}/zones", json={"operating_area_id": area_id, "code": "IKJ", "name": "Ikeja"})
    assert zone.status_code == 201, zone.text
    assert [z["name"] for z in client.get(f"/api/v1/tenants/{tid}/zones").json()] == ["Ikeja"]


def test_ordinary_users_cannot_create_workspaces_or_touch_others(as_clerk_user) -> None:
    as_clerk_user(f"user_{uuid4().hex[:16]}", admin=True)
    tid = client.post("/api/v1/admin/tenants", json={"name": "Someone Else Ltd"}).json()["id"]
    as_clerk_user(f"user_{uuid4().hex[:16]}")  # a different, ordinary user
    assert client.post("/api/v1/admin/tenants", json={"name": "Nope"}).status_code == 403
    assert client.get(f"/api/v1/tenants/{tid}/zones").status_code == 403
    assert client.post(f"/api/v1/admin/tenants/{tid}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "Sneaky"}).status_code == 403


def test_deactivated_user_is_blocked_and_unauthenticated_is_rejected(as_clerk_user) -> None:
    subject = f"user_{uuid4().hex[:16]}"
    as_clerk_user(subject)
    client.get("/api/v1/auth/me/profile")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.clerk_user_id == subject)).one()
        user.status = "inactive"
        session.add(user)
        session.commit()
    assert client.get("/api/v1/auth/me/profile").status_code == 403
    app.dependency_overrides[get_optional_user] = lambda: None
    assert client.get("/api/v1/auth/me/profile").status_code == 401
