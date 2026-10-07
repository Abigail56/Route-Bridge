import hashlib
import hmac
import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations import paystack as paystack_module
from routebridge.integrations.clerk import ClerkUser
from routebridge.main import app
from routebridge.models.billing import BillingPayment
from routebridge.models.core import Tenant, utc_now
from routebridge.models.operations import Driver

client = TestClient(app)
create_db_and_tables()
SECRET = "sk_test_unit_secret"


@pytest.fixture
def as_user():
    settings = get_settings()
    old = (settings.require_clerk_auth, list(settings.platform_admin_subjects), settings.billing_enforced, settings.paystack_secret_key)
    settings.require_clerk_auth = True

    def sign_in(subject: str, listed_admin: bool = False):
        app.dependency_overrides[get_optional_user] = lambda: ClerkUser(subject, {"email": f"{subject}@example.test"})
        settings.platform_admin_subjects[:] = [subject] if listed_admin else []

    yield sign_in
    app.dependency_overrides.pop(get_optional_user, None)
    settings.require_clerk_auth, settings.billing_enforced, settings.paystack_secret_key = old[0], old[2], old[3]
    settings.platform_admin_subjects[:] = old[1]


@pytest.fixture
def company(as_user):
    with Session(engine) as session:
        tenant = Tenant(name="Billing Logistics", plan="starter", plan_valid_until=utc_now() + timedelta(days=20))
        session.add(tenant)
        session.commit()
        tenant_id = str(tenant.id)
    owner, boss = f"user_{uuid4().hex[:12]}", f"user_{uuid4().hex[:12]}"
    as_user(boss, listed_admin=True)
    client.post(f"/api/v1/platform/tenants/{tenant_id}/owner", json={"clerk_user_id": owner})
    as_user(owner)
    return {"tenant": tenant_id, "owner": owner, "boss": boss}


def set_tenant(company, **fields) -> None:
    with Session(engine) as session:
        tenant = session.get(Tenant, UUID(company["tenant"]))
        for key, value in fields.items():
            setattr(tenant, key, value)
        session.add(tenant)
        session.commit()


def add_riders(company, how_many: int) -> None:
    with Session(engine) as session:
        for number in range(how_many):
            session.add(Driver(tenant_id=UUID(company["tenant"]), name=f"Rider {number}", phone=f"+23480{uuid4().int % 10**8:08d}"))
        session.commit()


def new_rider(company):
    return client.post(f"/api/v1/tenants/{company['tenant']}/drivers", json={"name": "Extra", "phone": f"+23480{uuid4().int % 10**8:08d}"})


def test_limits_do_nothing_until_billing_is_switched_on(company) -> None:
    add_riders(company, 12)  # starter allows 10
    assert new_rider(company).status_code == 201


def test_a_full_plan_refuses_one_more_rider_with_a_friendly_message(company) -> None:
    get_settings().billing_enforced = True
    add_riders(company, 10)
    res = new_rider(company)
    assert res.status_code == 402
    assert "Starter plan allows up to 10 riders" in res.json()["detail"]


def test_a_plan_that_ended_long_ago_blocks_new_work_but_the_grace_period_does_not(company) -> None:
    get_settings().billing_enforced = True
    set_tenant(company, plan_valid_until=utc_now() - timedelta(days=3))  # inside the 7 day grace
    assert new_rider(company).status_code == 201
    set_tenant(company, plan_valid_until=utc_now() - timedelta(days=30))
    res = new_rider(company)
    assert res.status_code == 402 and "ended" in res.json()["detail"]


def test_enterprise_has_no_limits_and_legacy_workspaces_are_never_blocked(company) -> None:
    get_settings().billing_enforced = True
    add_riders(company, 12)
    set_tenant(company, plan="enterprise", plan_valid_until=None)
    assert new_rider(company).status_code == 201
    set_tenant(company, plan="trial", plan_valid_until=None)  # no end recorded
    assert "ended" not in new_rider(company).text  # over the trial limit maybe, but never "plan ended"


def test_billing_summary_shows_usage_and_plans(company) -> None:
    add_riders(company, 2)
    body = client.get(f"/api/v1/tenants/{company['tenant']}/billing").json()
    assert body["plan"]["key"] == "starter" and body["usage"]["riders"] == 2 and body["status"] == "active"
    assert [p["key"] for p in body["plans"]] == ["trial", "starter", "growth", "business", "enterprise"]


def test_only_owner_roles_can_see_billing(company, as_user) -> None:
    stranger = f"user_{uuid4().hex[:12]}"
    as_user(stranger)
    assert client.get(f"/api/v1/tenants/{company['tenant']}/billing").status_code in (401, 403)


def signed(body: dict, secret: str = SECRET) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    return raw, {"x-paystack-signature": hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest(), "content-type": "application/json"}


def make_payment(company, plan="growth", amount_kobo=75_000 * 100) -> str:
    reference = f"rb_{uuid4().hex[:10]}"
    with Session(engine) as session:
        session.add(BillingPayment(tenant_id=UUID(company["tenant"]), reference=reference, plan=plan, amount_kobo=amount_kobo, payer_email="a@b.test"))
        session.commit()
    return reference


def test_a_signed_webhook_activates_the_plan_once(company) -> None:
    get_settings().paystack_secret_key = SECRET
    reference = make_payment(company)
    raw, headers = signed({"event": "charge.success", "data": {"reference": reference, "amount": 75_000 * 100, "status": "success"}})
    assert client.post("/api/v1/webhooks/paystack", content=raw, headers=headers).status_code == 200
    with Session(engine) as session:
        tenant = session.get(Tenant, UUID(company["tenant"]))
        first_end = tenant.plan_valid_until
        assert tenant.plan == "growth"
    client.post("/api/v1/webhooks/paystack", content=raw, headers=headers)  # Paystack retries: must not add another month
    with Session(engine) as session:
        assert session.get(Tenant, UUID(company["tenant"])).plan_valid_until == first_end
        assert session.exec(select(BillingPayment).where(BillingPayment.reference == reference)).one().status == "success"


def test_a_webhook_with_a_bad_signature_is_refused_and_changes_nothing(company) -> None:
    get_settings().paystack_secret_key = SECRET
    reference = make_payment(company)
    raw, headers = signed({"event": "charge.success", "data": {"reference": reference, "amount": 75_000 * 100, "status": "success"}}, secret="someone_else")
    assert client.post("/api/v1/webhooks/paystack", content=raw, headers=headers).status_code == 401
    assert client.post("/api/v1/webhooks/paystack", content=raw).status_code == 401
    with Session(engine) as session:
        assert session.get(Tenant, UUID(company["tenant"])).plan == "starter"


def test_paying_the_wrong_amount_does_not_buy_the_plan(company) -> None:
    get_settings().paystack_secret_key = SECRET
    reference = make_payment(company)
    raw, headers = signed({"event": "charge.success", "data": {"reference": reference, "amount": 100, "status": "success"}})
    client.post("/api/v1/webhooks/paystack", content=raw, headers=headers)
    with Session(engine) as session:
        assert session.get(Tenant, UUID(company["tenant"])).plan == "starter"
        assert session.exec(select(BillingPayment).where(BillingPayment.reference == reference)).one().status == "failed"


def test_checkout_and_verify_use_paystack_and_trust_only_its_answer(company, monkeypatch) -> None:
    get_settings().paystack_secret_key = SECRET

    class Fake:
        def initialize(self, **kwargs):
            assert kwargs["amount_kobo"] == 75_000 * 100
            return {"authorization_url": "https://checkout.paystack.test/abc"}

        def verify(self, reference):
            return {"status": "success", "amount": 75_000 * 100}

    monkeypatch.setattr("routebridge.routes.billing.get_paystack", lambda: Fake())
    started = client.post(f"/api/v1/tenants/{company['tenant']}/billing/checkout", json={"plan": "growth"})
    assert started.status_code == 200 and started.json()["authorization_url"].startswith("https://checkout.paystack.test")
    done = client.post(f"/api/v1/tenants/{company['tenant']}/billing/verify", json={"reference": started.json()["reference"]})
    assert done.status_code == 200 and done.json()["plan"]["key"] == "growth"


def test_checkout_says_so_when_payment_is_not_switched_on(company) -> None:
    get_settings().paystack_secret_key = ""
    res = client.post(f"/api/v1/tenants/{company['tenant']}/billing/checkout", json={"plan": "starter"})
    assert res.status_code == 503 and "not switched on" in res.json()["detail"]


def test_platform_staff_can_set_a_plan_and_others_cannot(company, as_user) -> None:
    res = client.put(f"/api/v1/platform/tenants/{company['tenant']}/plan", json={"plan": "business", "days": 60})
    assert res.status_code in (401, 403)
    as_user(company["boss"], listed_admin=True)
    ok = client.put(f"/api/v1/platform/tenants/{company['tenant']}/plan", json={"plan": "business", "days": 60})
    assert ok.status_code == 200 and ok.json()["plan"] == "business"


def test_signature_helper_is_strict() -> None:
    raw = b'{"a":1}'
    good = hmac.new(b"k", raw, hashlib.sha512).hexdigest()
    assert paystack_module.webhook_signature_ok("k", raw, good)
    assert not paystack_module.webhook_signature_ok("k", raw, "00")
    assert not paystack_module.webhook_signature_ok("", raw, good)
    assert not paystack_module.webhook_signature_ok("k", raw, None)
