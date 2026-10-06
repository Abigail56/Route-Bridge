from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.platform import PlatformAdmin, PlatformAuditEvent

client = TestClient(app)
create_db_and_tables()


@pytest.fixture
def as_user():
    settings = get_settings()
    old = (settings.require_clerk_auth, list(settings.platform_admin_subjects))
    settings.require_clerk_auth = True

    def sign_in(subject: str, listed_admin: bool = False):
        app.dependency_overrides[get_optional_user] = lambda: ClerkUser(subject, {"email": f"{subject}@example.test"})
        settings.platform_admin_subjects[:] = [subject] if listed_admin else []

    yield sign_in
    app.dependency_overrides.pop(get_optional_user, None)
    settings.require_clerk_auth = old[0]
    settings.platform_admin_subjects[:] = old[1]
    with Session(engine) as session:
        for row in session.exec(select(PlatformAdmin)).all():
            session.delete(row)
        session.commit()


def _workspace(name: str = "Acme Logistics") -> str:
    with Session(engine) as session:
        tenant = Tenant(name=name)
        session.add(tenant)
        session.commit()
        return str(tenant.id)


def test_only_platform_admins_reach_the_platform_console(as_user) -> None:
    as_user(f"user_{uuid4().hex[:12]}")
    for path in ("/tenants", "/users", "/admins", "/health", "/audit"):
        assert client.get(f"/api/v1/platform{path}").status_code == 403, path


def test_companies_can_be_suspended_and_their_members_are_locked_out(as_user) -> None:
    tenant_id = _workspace()
    owner = f"user_{uuid4().hex[:12]}"
    boss = f"user_{uuid4().hex[:12]}"
    as_user(boss, listed_admin=True)
    assigned = client.post(f"/api/v1/platform/tenants/{tenant_id}/owner", json={"clerk_user_id": owner, "email": "owner@acme.test"})
    assert assigned.status_code == 200, assigned.text
    row = next(c for c in client.get("/api/v1/platform/tenants").json() if c["tenant_id"] == tenant_id)
    assert row["owners"] == ["owner@acme.test"] and row["status"] == "active"

    as_user(owner)
    assert client.get(f"/api/v1/tenants/{tenant_id}/members").status_code == 200
    as_user(boss, listed_admin=True)
    assert client.post(f"/api/v1/platform/tenants/{tenant_id}/status", json={"status": "suspended"}).json()["status"] == "suspended"
    as_user(owner)
    locked = client.get(f"/api/v1/tenants/{tenant_id}/members")
    assert locked.status_code == 403 and "suspended" in locked.json()["detail"]
    assert client.get("/api/v1/auth/me/profile").json()["tenants"] == []
    as_user(boss, listed_admin=True)
    client.post(f"/api/v1/platform/tenants/{tenant_id}/status", json={"status": "active"})
    as_user(owner)
    assert client.get(f"/api/v1/tenants/{tenant_id}/members").status_code == 200


def test_changing_the_owner_demotes_the_old_one(as_user) -> None:
    tenant_id = _workspace("Swift Riders")
    first, second = f"user_{uuid4().hex[:12]}", f"user_{uuid4().hex[:12]}"
    as_user(f"user_{uuid4().hex[:12]}", listed_admin=True)
    client.post(f"/api/v1/platform/tenants/{tenant_id}/owner", json={"clerk_user_id": first})
    client.post(f"/api/v1/platform/tenants/{tenant_id}/owner", json={"clerk_user_id": second, "replace_existing": True})
    people = {p["clerk_user_id"]: p for p in client.get("/api/v1/platform/users").json()}
    assert people[first]["workspaces"][0]["role"] == "tenant_admin"
    assert people[second]["workspaces"][0]["role"] == "tenant_owner"


def test_people_search_add_to_company_and_deactivate(as_user) -> None:
    tenant_id = _workspace("Metro Dispatch")
    person = f"user_{uuid4().hex[:12]}"
    as_user(f"user_{uuid4().hex[:12]}", listed_admin=True)
    added = client.post(f"/api/v1/platform/tenants/{tenant_id}/members", json={"clerk_user_id": person, "role": "dispatcher", "email": f"rider.{person}@metro.test"})
    assert added.status_code == 201, added.text
    assert client.post(f"/api/v1/platform/tenants/{tenant_id}/members", json={"clerk_user_id": person, "role": "wizard"}).status_code == 422
    found = client.get("/api/v1/platform/users", params={"q": f"rider.{person}"}).json()
    assert [p["clerk_user_id"] for p in found] == [person] and found[0]["workspaces"][0]["role"] == "dispatcher"
    assert client.post(f"/api/v1/platform/users/{person}/status", json={"status": "inactive"}).json()["status"] == "inactive"
    as_user(person)
    assert client.get(f"/api/v1/tenants/{tenant_id}/members").status_code == 403


def test_platform_admins_live_in_the_database_with_a_last_admin_guard(as_user) -> None:
    bootstrap = f"user_{uuid4().hex[:12]}"
    as_user(bootstrap, listed_admin=True)
    listed = client.get("/api/v1/platform/admins").json()
    assert [(a["clerk_user_id"], a["source"]) for a in listed] == [(bootstrap, "settings")]
    assert client.delete(f"/api/v1/platform/admins/{bootstrap}").status_code == 409  # settings admins are removed in settings

    newcomer = f"user_{uuid4().hex[:12]}"
    assert client.post("/api/v1/platform/admins", json={"clerk_user_id": newcomer, "email": "staff@routebridge.test"}).status_code == 201
    assert client.post("/api/v1/platform/admins", json={"clerk_user_id": newcomer}).status_code == 409

    as_user(newcomer)  # not in settings: authorised purely by the database row
    assert client.get("/api/v1/auth/me/profile").json()["is_platform_admin"] is True
    assert client.get("/api/v1/platform/tenants").status_code == 200
    assert client.delete(f"/api/v1/platform/admins/{newcomer}").status_code == 409  # the last administrator cannot be removed

    as_user(bootstrap, listed_admin=True)
    assert client.delete(f"/api/v1/platform/admins/{newcomer}").status_code == 200
    as_user(newcomer)
    assert client.get("/api/v1/platform/tenants").status_code == 403


def test_health_and_audit_report_what_happened(as_user) -> None:
    as_user(f"user_{uuid4().hex[:12]}", listed_admin=True)
    tenant_id = _workspace("Audit Co")
    client.post(f"/api/v1/platform/tenants/{tenant_id}/status", json={"status": "suspended"})
    health = client.get("/api/v1/platform/health").json()
    names = {item["name"] for item in health["items"]}
    assert {"Database", "Redis", "SMS", "Event queue", "Messages"} <= names
    assert health["totals"]["workspaces"] >= 1 and health["totals"]["suspended_workspaces"] >= 1
    audit = client.get("/api/v1/platform/audit").json()
    assert any(row["scope"] == "platform" and row["action"] == "tenant.status_changed" for row in audit)
    with Session(engine) as session:
        event = session.exec(select(PlatformAuditEvent)).first()
        event.action = "tampered"
        session.add(event)
        with pytest.raises(ValueError):
            session.commit()
