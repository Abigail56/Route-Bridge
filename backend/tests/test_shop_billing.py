"""A shop's own plan: shown on its page, chosen and paid online, and enforced when the trial or plan ends."""
import hashlib
import hmac
import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from helpers import make_zone
from sqlmodel import Session, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.plans import SHOP_PLANS, ShopPlan
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.billing import BillingPayment, MerchantPlan
from routebridge.models.core import Tenant, utc_now
from routebridge.models.orders import Merchant

client = TestClient(app)
create_db_and_tables()
SECRET = "sk_test_unit_secret"


@pytest.fixture
def as_user():
    settings = get_settings()
    old = (settings.require_clerk_auth, list(settings.platform_admin_subjects), settings.paystack_secret_key, settings.shop_billing_enforced)
    settings.require_clerk_auth = True

    def sign_in(subject: str, listed_admin: bool = False):
        app.dependency_overrides[get_optional_user] = lambda: ClerkUser(subject, {"email": f"{subject}@example.test"})
        settings.platform_admin_subjects[:] = [subject] if listed_admin else []

    yield sign_in
    app.dependency_overrides.pop(get_optional_user, None)
    settings.require_clerk_auth, settings.paystack_secret_key, settings.shop_billing_enforced = old[0], old[2], old[3]
    settings.platform_admin_subjects[:] = old[1]


def _id() -> str:
    return f"user_{uuid4().hex[:12]}"


@pytest.fixture
def company(as_user):
    """A company with an owner and two registered shops (A and B), each with its own login."""
    with Session(engine) as session:
        tenant = Tenant(name="Shop Billing Logistics")
        session.add(tenant)
        session.flush()
        a, b = Merchant(tenant_id=tenant.id, name="Shop A"), Merchant(tenant_id=tenant.id, name="Shop B")
        session.add_all([a, b])
        session.commit()
        ids = {"tenant": str(tenant.id), "a": str(a.id), "b": str(b.id)}
    people = {"owner": _id(), "a": _id(), "b": _id(), "boss": _id()}
    as_user(people["boss"], listed_admin=True)
    t = ids["tenant"]
    assert client.post(f"/api/v1/platform/tenants/{t}/owner", json={"clerk_user_id": people["owner"]}).status_code == 200
    for key in ("a", "b"):
        assert client.post(f"/api/v1/platform/tenants/{t}/members", json={"clerk_user_id": people[key], "role": "merchant_user", "merchant_id": ids[key]}).status_code == 201
    for key in ("a", "b"):
        as_user(people[key])
        assert client.put(f"/api/v1/tenants/{t}/portal/profile", json={"contact_phone": "+2348011110000", "address_line": "1 Shop Road", "city": "Lagos", "state": "Lagos", "bank_name": "GTBank", "account_number": "0123456789", "account_name": "Shop Ltd"}).status_code == 200
    ids["zone"] = make_zone(t, "Lagos")
    return {**ids, "people": people}


def place(company, key="a"):
    return client.post(f"/api/v1/tenants/{company['tenant']}/portal/orders", json={"customer_name": "Walk In", "customer_phone": "+2348022222222", "address_text": "1 Test Road", "cod_amount": "1000", "total_amount": "1000", "service_zone_id": company["zone"]})


def set_plan(shop_id: str, plan: str, days: int, tenant_id: str) -> None:
    with Session(engine) as session:
        row = session.get(MerchantPlan, UUID(shop_id)) or MerchantPlan(merchant_id=UUID(shop_id), tenant_id=UUID(tenant_id))
        row.plan, row.valid_until = plan, utc_now() + timedelta(days=days)
        session.add(row)
        session.commit()


def test_a_new_shop_starts_a_free_trial_and_sees_its_plan(company, as_user) -> None:
    as_user(company["people"]["a"])
    body = client.get(f"/api/v1/tenants/{company['tenant']}/portal/billing").json()
    assert body["plan"]["key"] == "trial" and body["status"] == "active" and body["days_left"] in (13, 14)
    assert [p["key"] for p in body["plans"]] == ["trial", "basic", "standard", "pro"]
    assert body["payments"] == [] and body["orders_this_month"] == 0


def test_payment_is_enforced_once_the_plan_ends_but_only_when_online_payment_is_on(company, as_user) -> None:
    as_user(company["people"]["a"])
    settings = get_settings()
    set_plan(company["a"], "trial", -2, company["tenant"])
    settings.paystack_secret_key = ""  # no way to pay online yet: nobody is locked out
    assert place(company).status_code == 201
    settings.paystack_secret_key = SECRET
    refused = place(company)
    assert refused.status_code == 402 and "Pay online" in refused.json()["detail"]
    set_plan(company["a"], "basic", 20, company["tenant"])
    assert place(company).status_code == 201
    settings.shop_billing_enforced = False  # the switch off
    set_plan(company["a"], "trial", -2, company["tenant"])
    assert place(company).status_code == 201


def test_a_plan_stops_orders_when_its_month_is_used_up(company, as_user, monkeypatch) -> None:
    as_user(company["people"]["a"])
    get_settings().paystack_secret_key = SECRET
    set_plan(company["a"], "trial", 10, company["tenant"])
    monkeypatch.setitem(SHOP_PLANS, "trial", ShopPlan("trial", "Free trial", 0, orders_per_month=1))
    assert place(company).status_code == 201
    second = place(company)
    assert second.status_code == 402 and "Upgrade" in second.json()["detail"]


class FakePaystack:
    def __init__(self, amount_kobo: int, status: str = "success") -> None:
        self.amount_kobo, self.status = amount_kobo, status

    def initialize(self, **kwargs):
        assert kwargs["amount_kobo"] == self.amount_kobo and kwargs["callback_url"].endswith("/billing")
        return {"authorization_url": "https://checkout.paystack.test/shop"}

    def verify(self, reference):
        return {"status": self.status, "amount": self.amount_kobo}


def test_a_shop_chooses_a_plan_and_pays_and_only_paystacks_answer_counts(company, as_user, monkeypatch) -> None:
    as_user(company["people"]["a"])
    get_settings().paystack_secret_key = SECRET
    monkeypatch.setattr("routebridge.routes.portal_billing.get_paystack", lambda: FakePaystack(15_000 * 100))
    started = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/checkout", json={"plan": "standard"})
    assert started.status_code == 200 and started.json()["authorization_url"].startswith("https://checkout.paystack.test")
    # going back from the payment page without paying changes nothing
    monkeypatch.setattr("routebridge.routes.portal_billing.get_paystack", lambda: FakePaystack(15_000 * 100, "abandoned"))
    still = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/verify", json={"reference": started.json()["reference"]}).json()
    assert still["plan"]["key"] == "trial"
    monkeypatch.setattr("routebridge.routes.portal_billing.get_paystack", lambda: FakePaystack(15_000 * 100))
    done = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/verify", json={"reference": started.json()["reference"]}).json()
    assert done["plan"]["key"] == "standard" and done["status"] == "active" and done["payments"][0]["status"] == "success"
    again = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/verify", json={"reference": started.json()["reference"]}).json()
    assert again["valid_until"] == done["valid_until"]  # paying twice for one reference never adds time


def test_the_webhook_also_switches_a_shops_plan_on_and_the_wrong_amount_does_not(company, as_user, monkeypatch) -> None:
    as_user(company["people"]["a"])
    get_settings().paystack_secret_key = SECRET
    monkeypatch.setattr("routebridge.routes.portal_billing.get_paystack", lambda: FakePaystack(5_000 * 100))
    ref = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/checkout", json={"plan": "basic"}).json()["reference"]

    def hook(amount: int):
        raw = json.dumps({"event": "charge.success", "data": {"reference": ref, "amount": amount, "status": "success"}}).encode()
        return client.post("/api/v1/webhooks/paystack", content=raw, headers={"x-paystack-signature": hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()})

    assert hook(100).status_code == 200
    with Session(engine) as session:
        assert session.exec(select(BillingPayment).where(BillingPayment.reference == ref)).one().status == "failed"  # wrong amount: no plan
        assert session.get(MerchantPlan, UUID(company["a"])) is None or session.get(MerchantPlan, UUID(company["a"])).plan == "trial"
    ref2 = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/checkout", json={"plan": "basic"}).json()["reference"]
    raw = json.dumps({"event": "charge.success", "data": {"reference": ref2, "amount": 5_000 * 100, "status": "success"}}).encode()
    client.post("/api/v1/webhooks/paystack", content=raw, headers={"x-paystack-signature": hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()})
    with Session(engine) as session:
        assert session.get(MerchantPlan, UUID(company["a"])).plan == "basic"
        assert session.get(Tenant, UUID(company["tenant"])).plan != "basic"  # the company's own plan is untouched


def test_a_shop_cannot_see_or_pay_for_another_shop_and_only_shops_use_the_page(company, as_user, monkeypatch) -> None:
    get_settings().paystack_secret_key = SECRET
    monkeypatch.setattr("routebridge.routes.portal_billing.get_paystack", lambda: FakePaystack(5_000 * 100))
    as_user(company["people"]["a"])
    ref = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/checkout", json={"plan": "basic"}).json()["reference"]
    as_user(company["people"]["b"])
    assert client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/verify", json={"reference": ref}).status_code == 404
    assert client.get(f"/api/v1/tenants/{company['tenant']}/portal/billing").json()["payments"] == []
    as_user(company["people"]["owner"])
    assert client.get(f"/api/v1/tenants/{company['tenant']}/portal/billing").status_code == 403  # the Admin is not a shop


def test_the_admin_sees_every_shops_plan_and_the_company_plan_ignores_shop_payments(company, as_user, monkeypatch) -> None:
    get_settings().paystack_secret_key = SECRET
    monkeypatch.setattr("routebridge.routes.portal_billing.get_paystack", lambda: FakePaystack(5_000 * 100))
    as_user(company["people"]["a"])
    ref = client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/checkout", json={"plan": "basic"}).json()["reference"]
    client.post(f"/api/v1/tenants/{company['tenant']}/portal/billing/verify", json={"reference": ref})
    as_user(company["people"]["owner"])
    rows = {r["name"]: r for r in client.get(f"/api/v1/tenants/{company['tenant']}/billing/shops").json()}
    assert rows["Shop A"]["plan"] == "basic" and rows["Shop A"]["last_paid_at"] is not None
    assert rows["Shop B"]["plan"] == "trial" and rows["Shop B"]["last_paid_at"] is None
    # the company's own verify cannot be used on a shop's payment reference
    assert client.post(f"/api/v1/tenants/{company['tenant']}/billing/verify", json={"reference": ref}).status_code == 404
    as_user(company["people"]["a"])
    assert client.get(f"/api/v1/tenants/{company['tenant']}/billing/shops").status_code == 403  # a shop cannot see the others
