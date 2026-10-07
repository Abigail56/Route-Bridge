from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.core import Tenant, utc_now
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
    with Session(engine) as session:
        tenant, other = Tenant(name="Claims Logistics"), Tenant(name="Elsewhere")
        session.add_all([tenant, other])
        session.flush()
        a, b = Merchant(tenant_id=tenant.id, name="Shop A"), Merchant(tenant_id=tenant.id, name="Shop B")
        session.add_all([a, b])
        session.commit()
        ids = {"tenant": str(tenant.id), "a": str(a.id), "b": str(b.id)}
    people = {k: _id() for k in ("owner", "a", "b", "boss", "dispatcher", "finance")}
    as_user(people["boss"], listed_admin=True)
    t = ids["tenant"]
    client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": people["owner"]})
    for who, role, shop in (("a", "merchant_user", "a"), ("b", "merchant_user", "b"), ("dispatcher", "dispatcher", None), ("finance", "finance", None)):
        body = {"clerk_user_id": people[who], "role": role, **({"merchant_id": ids[shop]} if shop else {})}
        assert client.post(f"/api/v1/platform/tenants/{t}/members", json=body).status_code == 201
    as_user(people["owner"])
    orders = {}
    for key in ("a", "b"):
        res = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": ids[key], "customer_name": "C", "customer_phone": "+2348011111111", "external_ref": f"R-{key}-{uuid4().hex[:5]}", "address_text": "x"})
        orders[key] = res.json()["id"]
    return {**ids, "people": people, "orders": orders}


def raise_claim(company, as_user, who="a", **over) -> dict:
    as_user(company["people"][who])
    body = {"kind": "damage", "description": "The box arrived crushed", "amount_claimed": "8000", "order_id": company["orders"][who], **over}
    res = client.post(f"/api/v1/tenants/{company['tenant']}/portal/claims", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_a_shop_raises_a_claim_and_sees_only_its_own(company, as_user) -> None:
    mine = raise_claim(company, as_user, "a")
    raise_claim(company, as_user, "b")
    as_user(company["people"]["a"])
    listed = client.get(f"/api/v1/tenants/{company['tenant']}/portal/claims").json()
    assert [c["id"] for c in listed] == [mine["id"]]
    assert mine["status"] == "open" and mine["merchant_name"] == "Shop A" and "internal_note" not in mine


def test_a_shop_cannot_claim_against_another_shops_order(company, as_user) -> None:
    as_user(company["people"]["a"])
    res = client.post(f"/api/v1/tenants/{company['tenant']}/portal/claims", json={"kind": "loss", "description": "lost it", "order_id": company["orders"]["b"]})
    assert res.status_code == 404


def test_staff_decide_a_claim_and_the_shop_sees_the_outcome_but_not_internal_notes(company, as_user) -> None:
    claim = raise_claim(company, as_user, "a")
    as_user(company["people"]["owner"])
    url = f"/api/v1/tenants/{company['tenant']}/claims/{claim['id']}"
    assert client.patch(url, json={"status": "investigating", "internal_note": "ask the rider"}).status_code == 200
    done = client.patch(url, json={"status": "approved", "amount_approved": "6000", "resolution_note": "Half the goods survived"})
    assert done.status_code == 200 and Decimal(done.json()["amount_approved"]) == Decimal("6000") and done.json()["decided_at"]
    as_user(company["people"]["a"])
    seen = client.get(f"/api/v1/tenants/{company['tenant']}/portal/claims").json()[0]
    assert seen["status"] == "approved" and seen["resolution_note"] == "Half the goods survived" and "internal_note" not in seen


def test_rules_of_the_workflow(company, as_user) -> None:
    claim = raise_claim(company, as_user, "a")
    as_user(company["people"]["owner"])
    url = f"/api/v1/tenants/{company['tenant']}/claims/{claim['id']}"
    assert client.patch(url, json={"status": "paid"}).status_code == 409  # cannot pay what was never approved
    assert client.patch(url, json={"status": "approved", "amount_approved": "9000"}).status_code == 422  # more than the shop claimed
    assert client.patch(url, json={"status": "rejected"}).status_code == 422  # a reason is required
    assert client.patch(url, json={"status": "rejected", "resolution_note": "Photo shows the box was fine"}).status_code == 200
    assert client.patch(url, json={"status": "approved"}).status_code == 409  # rejected is final


def test_only_finance_level_staff_decide_and_merchants_use_only_the_portal(company, as_user) -> None:
    claim = raise_claim(company, as_user, "a")
    url = f"/api/v1/tenants/{company['tenant']}/claims/{claim['id']}"
    as_user(company["people"]["dispatcher"])
    assert client.get(f"/api/v1/tenants/{company['tenant']}/claims").status_code == 200
    assert client.patch(url, json={"status": "investigating"}).status_code == 403
    as_user(company["people"]["finance"])
    assert client.patch(url, json={"status": "investigating"}).status_code == 200
    as_user(company["people"]["a"])
    assert client.get(f"/api/v1/tenants/{company['tenant']}/claims").status_code == 403
    assert client.patch(url, json={"status": "approved"}).status_code == 403


def test_staff_can_log_a_claim_for_a_shop(company, as_user) -> None:
    as_user(company["people"]["dispatcher"])
    res = client.post(f"/api/v1/tenants/{company['tenant']}/claims", json={"merchant_id": company["b"], "kind": "dispute", "description": "Customer says they paid already"})
    assert res.status_code == 201 and res.json()["raised_by"] == "staff"


def test_an_approved_claim_adds_to_the_shops_statement(company, as_user) -> None:
    claim = raise_claim(company, as_user, "a")
    as_user(company["people"]["owner"])
    client.patch(f"/api/v1/tenants/{company['tenant']}/claims/{claim['id']}", json={"status": "approved", "amount_approved": "6000"})
    window = {"from": (utc_now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "to": (utc_now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    statement = client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['a']}/statement", params=window).json()
    assert Decimal(statement["claim_credits"]) == Decimal("6000") and Decimal(statement["net_payable"]) == Decimal("6000")
    other = client.get(f"/api/v1/tenants/{company['tenant']}/merchants/{company['b']}/statement", params=window).json()
    assert Decimal(other["claim_credits"]) == Decimal("0")
