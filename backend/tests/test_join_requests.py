"""A new shop or rider presses "Send to the Admin": the request reaches only the receiving company's owner, drops out once they are added,
and grants nothing by itself."""
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.sessions import AuthUser
from routebridge.main import app
from routebridge.models.core import Tenant

client = TestClient(app)
create_db_and_tables()

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _id() -> str:
    return f"user_{uuid4().hex[:12]}"


@pytest.fixture
def as_user():
    settings = get_settings()
    old = (settings.require_auth, list(settings.platform_admin_subjects), settings.join_requests_tenant_id)
    settings.require_auth = True

    def sign_in(subject: str | None, listed_admin: bool = False):
        if subject is None:
            app.dependency_overrides[get_optional_user] = lambda: None
        else:
            app.dependency_overrides[get_optional_user] = lambda: AuthUser(subject, {"email": f"{subject}@example.test"})
        settings.platform_admin_subjects[:] = [subject] if listed_admin and subject else []

    yield sign_in
    app.dependency_overrides.pop(get_optional_user, None)
    settings.require_auth = old[0]
    settings.platform_admin_subjects[:] = old[1]
    settings.join_requests_tenant_id = old[2]


def _company(as_user, name: str) -> dict[str, str]:
    with Session(engine) as session:
        tenant = Tenant(name=name)
        session.add(tenant)
        session.commit()
        t = str(tenant.id)
    owner, boss = _id(), _id()
    as_user(boss, listed_admin=True)
    assert client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": owner}).status_code == 200
    return {"tenant": t, "owner": owner}


@pytest.fixture
def company(as_user):
    first = _company(as_user, "Join Test Logistics")
    get_settings().join_requests_tenant_id = UUID(first["tenant"])
    return first


def _requests(company):
    return client.get(f"/api/v1/tenants/{company['tenant']}/join-requests")


def test_a_shop_sends_its_id_and_only_that_owner_sees_it(as_user, company):
    other = _company(as_user, "Some Other Company")
    shop = _id()
    as_user(shop)
    sent = client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user", "shop_name": "  Ada   Foods "})
    assert sent.status_code == 200, sent.text
    assert sent.json()["sent"] is True and sent.json()["company"] == "Join Test Logistics"
    assert client.get("/api/v1/auth/me/join-request").json()["role"] == "merchant_user"
    # the person asking cannot read the company's list
    assert _requests(company).status_code == 403

    as_user(company["owner"])
    rows = _requests(company).json()
    assert [(r["clerk_user_id"], r["role"], r["shop_name"]) for r in rows] == [(shop, "merchant_user", "Ada Foods")]
    assert rows[0]["email"] == f"{shop}@example.test"

    as_user(other["owner"])
    assert client.get(f"/api/v1/tenants/{other['tenant']}/join-requests").json() == []
    assert client.get(f"/api/v1/tenants/{company['tenant']}/join-requests").status_code == 403


def test_a_rider_must_register_first(as_user, company):
    rider = _id()
    as_user(rider)
    refused = client.post("/api/v1/auth/me/join-request", json={"role": "driver"})
    assert refused.status_code == 422 and "driver details" in refused.json()["detail"]
    assert client.put("/api/v1/auth/me/rider-registration", json={"full_name": "Musa Bello", "phone": "+2348012345678", "photo": PNG, "zones": ["Lagos"]}).status_code == 200
    assert client.post("/api/v1/auth/me/join-request", json={"role": "driver"}).status_code == 200

    as_user(company["owner"])
    [row] = [r for r in _requests(company).json() if r["clerk_user_id"] == rider]
    assert row["role"] == "driver" and row["rider_registered"] and row["phone"] == "+2348012345678" and row["zones"] == ["Lagos"]


def test_once_added_the_request_goes_away_and_cannot_be_sent_again(as_user, company):
    shop = _id()
    as_user(shop)
    assert client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"}).status_code == 200
    as_user(company["owner"])
    assert client.post(f"/api/v1/admin/tenants/{company['tenant']}/merchants", json={"clerk_user_id": shop}).status_code == 201
    assert all(r["clerk_user_id"] != shop for r in _requests(company).json())
    as_user(shop)
    assert client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"}).status_code == 409


def test_resending_soon_does_not_ring_again_and_dismiss_hides_it(as_user, company):
    shop = _id()
    as_user(shop)
    first = client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"}).json()["sent_at"]
    assert client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"}).json()["sent_at"] == first

    as_user(company["owner"])
    [row] = [r for r in _requests(company).json() if r["clerk_user_id"] == shop]
    assert client.post(f"/api/v1/tenants/{company['tenant']}/join-requests/{row['id']}/dismiss").status_code == 200
    assert all(r["clerk_user_id"] != shop for r in _requests(company).json())

    as_user(shop)
    assert client.get("/api/v1/auth/me/join-request").json()["sent"] is False
    assert client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"}).status_code == 200
    as_user(company["owner"])
    assert any(r["clerk_user_id"] == shop for r in _requests(company).json())


def test_with_several_companies_it_goes_to_the_one_the_admin_owns(as_user, company):
    settings = get_settings()
    settings.join_requests_tenant_id = None
    admin = _id()
    with Session(engine) as session:
        tenant = Tenant(name="Admin's Own Company")
        session.add(tenant)
        session.commit()
        t = str(tenant.id)
    as_user(_id(), listed_admin=True)
    assert client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": admin}).status_code == 200
    settings.platform_admin_subjects[:] = [admin]  # the owner of that company is the RouteBridge Admin
    app.dependency_overrides[get_optional_user] = lambda: AuthUser("user_shop_for_admin", {"email": "shop@example.test"})
    sent = client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"})
    assert sent.status_code == 200 and sent.json()["company"] == "Admin's Own Company"
    app.dependency_overrides[get_optional_user] = lambda: AuthUser(admin, {"email": "admin@example.test"})
    assert [r["clerk_user_id"] for r in client.get(f"/api/v1/tenants/{t}/join-requests").json()] == ["user_shop_for_admin"]


def test_no_receiving_company_means_no_send(as_user, company):
    _company(as_user, "A Second Company")  # several workspaces and no setting: nobody is guessed
    get_settings().join_requests_tenant_id = None
    as_user(_id())
    refused = client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"})
    assert refused.status_code == 409 and "WhatsApp" in refused.json()["detail"]
    as_user(None)
    assert client.post("/api/v1/auth/me/join-request", json={"role": "merchant_user"}).status_code == 401
