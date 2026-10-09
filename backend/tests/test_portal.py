from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.orders import Merchant

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


def _id() -> str:
    return f"user_{uuid4().hex[:12]}"


@pytest.fixture
def company(as_user):
    """A company with an owner, two shops (A and B), one merchant user per shop, a dispatcher, and one order for each shop."""
    with Session(engine) as session:
        tenant = Tenant(name="Portal Test Logistics")
        session.add(tenant)
        session.flush()
        shop_a, shop_b = Merchant(tenant_id=tenant.id, name="Shop A"), Merchant(tenant_id=tenant.id, name="Shop B")
        other = Tenant(name="Another Company")
        session.add_all([shop_a, shop_b, other])
        session.flush()
        foreign = Merchant(tenant_id=other.id, name="Foreign Shop")
        session.add(foreign)
        session.commit()
        ids = {"tenant": str(tenant.id), "a": str(shop_a.id), "b": str(shop_b.id), "foreign": str(foreign.id)}
    people = {"owner": _id(), "a": _id(), "b": _id(), "dispatcher": _id(), "boss": _id()}
    as_user(people["boss"], listed_admin=True)
    t = ids["tenant"]
    assert client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": people["owner"]}).status_code == 200
    assert client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": people["a"], "role": "merchant_user", "merchant_id": ids["a"]}).status_code == 201
    assert client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": people["b"], "role": "merchant_user", "merchant_id": ids["b"]}).status_code == 201
    assert client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": people["dispatcher"], "role": "dispatcher"}).status_code == 201
    as_user(people["owner"])
    orders = {}
    for key in ("a", "b"):
        res = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": ids[key], "customer_name": f"Cust {key}", "customer_phone": "+2348011111111", "external_ref": f"REF-{key}-{uuid4().hex[:6]}", "cod_amount": "1000", "total_amount": "1000", "address_text": f"{key} street"})
        assert res.status_code == 201, res.text
        orders[key] = res.json()["id"]
    return {**ids, "people": people, "orders": orders}


def test_a_merchant_sees_only_its_own_orders(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["people"]["a"])
    me = client.get(f"/api/v1/tenants/{t}/portal/me").json()
    assert me["merchant_name"] == "Shop A" and me["workspace_name"] == "Portal Test Logistics"
    listed = client.get(f"/api/v1/tenants/{t}/portal/orders").json()
    assert [o["id"] for o in listed] == [company["orders"]["a"]]
    assert "driver_id" not in listed[0] and "customer_phone" not in listed[0]
    assert client.get(f"/api/v1/tenants/{t}/portal/orders/{company['orders']['a']}").status_code == 200
    assert client.get(f"/api/v1/tenants/{t}/portal/orders/{company['orders']['b']}").status_code == 404  # another shop's order does not exist for you
    summary = client.get(f"/api/v1/tenants/{t}/portal/summary").json()
    assert summary["orders_total"] == 1 and summary["in_progress"] == 1 and summary["delivered"] == 0 and summary["cod_to_collect"] == "1000.00"
    profile = client.get("/api/v1/auth/me/profile").json()["tenants"][0]
    assert profile["role"] == "merchant_user" and profile["merchant_name"] == "Shop A"


def test_orders_created_in_the_portal_always_belong_to_that_merchant(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["people"]["b"])
    assert client.put(f"/api/v1/tenants/{t}/portal/phone", json={"phone": "+2348011110000"}).status_code == 200
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json={"contact_phone": "+2348011110000", "address_line": "1 Shop Road", "city": "Lagos", "state": "Lagos", "bank_name": "GTBank", "account_number": "0123456789", "account_name": "Shop B Ltd"}).status_code == 200
    created = client.post(f"/api/v1/tenants/{t}/portal/orders", json={"customer_name": "Walk In", "customer_phone": "+2348022222222", "address_text": "1 Test Road", "cod_amount": "2500", "total_amount": "2500"})
    assert created.status_code == 201, created.text
    assert created.json()["external_ref"].startswith("M-")
    # the request cannot pick a merchant: naming one is rejected outright
    sneaky = client.post(f"/api/v1/tenants/{t}/portal/orders", json={"merchant_id": company["a"], "customer_name": "X", "customer_phone": "+2348033333333", "address_text": "2 Road"})
    assert sneaky.status_code == 422
    as_user(company["people"]["owner"])
    mine = [o for o in client.get(f"/api/v1/tenants/{t}/orders").json() if o["id"] == created.json()["id"]]
    assert mine[0]["merchant_name"] == "Shop B"
    as_user(company["people"]["a"])
    assert created.json()["id"] not in [o["id"] for o in client.get(f"/api/v1/tenants/{t}/portal/orders").json()]


def test_a_merchant_is_locked_out_of_everything_else(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["people"]["a"])
    for path in ("/orders", "/reports/summary", "/drivers", "/members", "/reconciliation", "/exceptions", "/audit", "/dispatch/batches"):
        res = client.get(f"/api/v1/tenants/{t}{path}")
        assert res.status_code == 403, (path, res.status_code)
    assert client.get(f"/api/v1/admin/tenants/{t}/merchants").status_code == 403
    assert client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": company["a"], "customer_name": "x", "customer_phone": "+2348000000000", "external_ref": "hack", "address_text": "x"}).status_code == 403
    assert client.post(f"/api/v1/admin/tenants/{t}/merchants", json={"clerk_user_id": f"user_shop_{__import__('uuid').uuid4().hex[:10]}", "name": "Mine now"}).status_code == 403
    assert client.get("/api/v1/platform/tenants").status_code == 403


def test_other_roles_cannot_use_the_portal(company, as_user) -> None:
    t = company["tenant"]
    for who in ("dispatcher", "owner"):
        as_user(company["people"][who])
        assert client.get(f"/api/v1/tenants/{t}/portal/orders").status_code == 403, who


def test_a_merchant_account_must_be_tied_to_a_real_merchant_of_this_company(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["people"]["owner"])
    base = {"clerk_user_id": _id(), "role": "merchant_user"}
    assert client.post(f"/api/v1/tenants/{t}/members", json=base).status_code == 422
    assert client.post(f"/api/v1/tenants/{t}/members", json={**base, "merchant_id": company["foreign"]}).status_code == 404
    ok = client.post(f"/api/v1/tenants/{t}/members", json={**base, "merchant_id": company["a"]})
    assert ok.status_code == 201 and ok.json()["merchant_name"] == "Shop A"
    # changing someone away from merchant_user clears the link
    changed = client.patch(f"/api/v1/tenants/{t}/members/{ok.json()['membership_id']}", json={"role": "dispatcher"})
    assert changed.status_code == 200 and changed.json()["merchant_id"] is None
    # a merchant-less account is refused the portal with a clear message
    with Session(engine) as session:
        from routebridge.models.access import TenantMembership
        row = session.get(TenantMembership, UUID(ok.json()["membership_id"]))
        row.role = "merchant_user"
        session.add(row)
        session.commit()
    as_user(base["clerk_user_id"])
    res = client.get(f"/api/v1/tenants/{t}/portal/orders")
    assert res.status_code == 403 and "not linked to a merchant" in res.json()["detail"]



ORDER = {"customer_name": "Phone Test", "customer_phone": "+2348044444444", "address_text": "3 Test Road", "cod_amount": "1000", "total_amount": "1000"}


def test_a_shop_must_give_its_phone_number_before_it_can_create_an_order(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["people"]["a"])
    assert client.get(f"/api/v1/tenants/{t}/portal/me").json()["contact_phone"] is None
    refused = client.post(f"/api/v1/tenants/{t}/portal/orders", json=ORDER)
    assert refused.status_code == 422 and "phone number" in refused.json()["detail"]
    for bad in ("call me", "123", "<script>alert(1)</script>"):
        assert client.put(f"/api/v1/tenants/{t}/portal/phone", json={"phone": bad}).status_code == 422, bad
    saved = client.put(f"/api/v1/tenants/{t}/portal/phone", json={"phone": " +234 801 000 1111 "})
    assert saved.status_code == 200 and saved.json()["contact_phone"] == "+234 801 000 1111"
    assert client.get(f"/api/v1/tenants/{t}/portal/me").json()["contact_phone"] == "+234 801 000 1111"
    # a phone alone is not enough any more: the address and bank account come too
    unfinished = client.post(f"/api/v1/tenants/{t}/portal/orders", json=ORDER)
    assert unfinished.status_code == 422 and "registering" in unfinished.json()["detail"]
    assert client.put(f"/api/v1/tenants/{t}/portal/profile", json={"contact_phone": "+2348011110000", "address_line": "5 Market Road", "city": "Lagos", "state": "Lagos", "bank_name": "GTBank", "account_number": "0123456789", "account_name": "Shop A Ltd"}).status_code == 200
    assert client.post(f"/api/v1/tenants/{t}/portal/orders", json=ORDER).status_code == 201  # now it goes through


def test_a_shop_can_only_set_its_own_number_and_nobody_else_can_use_the_route(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["people"]["b"])
    assert client.put(f"/api/v1/tenants/{t}/portal/phone", json={"phone": "+2348055550000", "merchant_id": company["a"]}).status_code == 422  # cannot name a shop
    assert client.put(f"/api/v1/tenants/{t}/portal/phone", json={"phone": "+2348055550000"}).status_code == 200
    as_user(company["people"]["owner"])
    shops = {m["id"]: m for m in client.get(f"/api/v1/tenants/{t}/merchants").json()}
    assert shops[company["b"]]["contact_phone"] == "+2348055550000" and shops[company["a"]]["contact_phone"] is None
    for who in ("dispatcher", "owner"):  # company staff use Settings, not the shop's dashboard
        as_user(company["people"][who])
        assert client.put(f"/api/v1/tenants/{t}/portal/phone", json={"phone": "+2348055550001"}).status_code == 403, who


def test_a_shop_can_add_change_and_remove_an_email_for_its_alerts(company, as_user) -> None:
    t = company["tenant"]
    as_user(company["people"]["a"])
    url = f"/api/v1/tenants/{t}/portal/phone"
    assert client.put(url, json={"phone": "+2348011110000", "email": "not-an-email"}).status_code == 422
    saved = client.put(url, json={"phone": "+2348011110000", "email": " Shop@Example.COM "}).json()
    assert saved["contact_email"] == "shop@example.com"
    assert client.put(url, json={"phone": "+2348011110001"}).json()["contact_email"] == "shop@example.com"  # left out = unchanged
    assert client.put(url, json={"phone": "+2348011110001", "email": ""}).json()["contact_email"] is None  # empty = removed
