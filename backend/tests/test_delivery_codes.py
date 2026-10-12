from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant, utc_now
from routebridge.models.orders import Merchant
from routebridge.models.plans import DeliveryOtp, TrackingToken
from routebridge.models.workflows import Notification

client = TestClient(app)
create_db_and_tables()


@pytest.fixture(autouse=True)
def relay_mode():
    settings = get_settings()
    old = (settings.driver_token_secret, settings.otp_delivery)
    settings.driver_token_secret, settings.otp_delivery = "d" * 32, "dashboard"
    yield
    settings.driver_token_secret, settings.otp_delivery = old


def make_job(on_the_road: bool = True):
    with Session(engine) as session:
        tenant = Tenant(name="Relay Logistics")
        session.add(tenant)
        session.flush()
        shop = Merchant(tenant_id=tenant.id, name="Relay Shop")
        session.add(shop)
        session.commit()
        t, m = str(tenant.id), str(shop.id)
    order = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": m, "customer_name": "Chidi Okafor", "customer_phone": "08031112222", "external_ref": f"RL-{uuid4().hex[:5]}", "address_text": "4 Bode Thomas"}).json()
    driver = client.post(f"/api/v1/tenants/{t}/drivers", json={"name": "Musa Rider", "phone": f"+23480{uuid4().int % 10**8:08d}"}).json()
    job = order["delivery_job_id"]
    client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/assignments", json={"driver_id": driver["id"]})
    if on_the_road:
        for target in ("accepted", "en_route"):
            assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/transitions", json={"target_status": target}).status_code == 200
    token = client.post(f"/api/v1/tenants/{t}/drivers/{driver['id']}/token").json()["access_token"]
    return t, job, order["external_ref"], {"Authorization": f"Bearer {token}"}


def ask(t, job, auth):
    return client.post(f"/api/v1/driver/tenants/{t}/jobs/{job}/otp", headers=auth)


def pending(t):
    res = client.get(f"/api/v1/tenants/{t}/delivery-codes")
    assert res.status_code == 200, res.text
    return res.json()


def test_the_rider_asks_and_the_dashboard_gets_a_card_and_the_customer_is_texted() -> None:
    t, job, ref, auth = make_job()
    answer = ask(t, job, auth)
    assert answer.status_code == 201 or answer.status_code == 200, answer.text
    body = answer.json()
    assert body["relay"] is True and body["sent"] is True and "code" not in body and "debug_code" not in body  # the rider never sees it
    with Session(engine) as session:
        queued = session.exec(select(Notification).where(Notification.tenant_id == UUID(t), Notification.template == "delivery_otp")).all()
        assert sorted(n.channel for n in queued) == ["sms", "whatsapp"]  # the customer is texted on both (recorded only until a sender is connected)
    cards = pending(t)
    assert len(cards) == 1
    card = cards[0]
    assert card["order_ref"] == ref and card["customer_name"] == "Chidi Okafor" and card["customer_phone"] == "08031112222" and card["driver_name"] == "Musa Rider"
    assert len(card["code"]) == 6 and card["code"].isdigit() and ref in card["message"] and card["code"] in card["message"] and card["minutes_left"] >= 1


def test_a_new_request_replaces_the_old_card_and_marking_it_sent_removes_it() -> None:
    t, job, _, auth = make_job()
    ask(t, job, auth)
    first = pending(t)[0]
    ask(t, job, auth)
    cards = pending(t)
    assert len(cards) == 1 and cards[0]["id"] != first["id"]  # only the latest code of a job is shown
    assert client.post(f"/api/v1/tenants/{t}/delivery-codes/{cards[0]['id']}/sent").json() == {"sent": True}
    assert pending(t) == []
    with Session(engine) as session:  # still kept until used or expired: the customer's own tracking page may still need it
        assert any(o.relay_code for o in session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == UUID(job))).all())


def test_the_code_staff_passed_on_is_the_code_that_opens_the_delivery() -> None:
    t, job, _, auth = make_job()
    ask(t, job, auth)
    code = pending(t)[0]["code"]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/otp/verify", json={"code": wrong}).status_code == 400
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/otp/verify", json={"code": code}).json() == {"verified": True}
    assert pending(t) == []  # used: the card is gone
    with Session(engine) as session:
        assert all(o.relay_code is None for o in session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == UUID(job))).all())


def test_an_expired_code_disappears_and_is_erased() -> None:
    t, job, _, auth = make_job()
    ask(t, job, auth)
    with Session(engine) as session:
        for otp in session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == UUID(job))).all():
            otp.expires_at = utc_now() - timedelta(minutes=1)
            session.add(otp)
        session.commit()
    assert pending(t) == []
    with Session(engine) as session:
        assert all(o.relay_code is None for o in session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == UUID(job))).all())


def test_one_company_cannot_see_or_close_another_companys_codes() -> None:
    t1, job1, _, auth1 = make_job()
    t2, _, _, _ = make_job()
    ask(t1, job1, auth1)
    assert pending(t2) == []
    foreign = pending(t1)[0]["id"]
    assert client.post(f"/api/v1/tenants/{t2}/delivery-codes/{foreign}/sent").status_code == 404
    assert len(pending(t1)) == 1  # still waiting


def test_in_text_mode_nothing_changes() -> None:
    get_settings().otp_delivery = "sms"
    t, job, _, auth = make_job()
    body = ask(t, job, auth).json()
    assert body["relay"] is False and body["sent"] is True
    assert pending(t) == []  # no card: with a sender nobody passes codes on by hand
    with Session(engine) as session:
        assert len(session.exec(select(Notification).where(Notification.tenant_id == UUID(t), Notification.template == "delivery_otp")).all()) == 2


def _link(job: str, t: str) -> str:
    with Session(engine) as session:
        token = f"code-{uuid4().hex[:20]}"
        session.add(TrackingToken(tenant_id=UUID(t), delivery_job_id=UUID(job), token=token, expires_at=utc_now() + timedelta(hours=2)))
        session.commit()
    return token


def test_the_customer_sees_the_code_on_their_tracking_page_only_while_it_is_usable() -> None:
    t, job, ref, auth = make_job()
    link = _link(job, t)
    page = client.get(f"/api/v1/public/tracking/{link}")
    assert page.status_code == 200 and page.json()["delivery_code"] is None  # nothing asked for yet
    assert page.headers["cache-control"] == "no-store"
    ask(t, job, auth)
    card = pending(t)[0]
    shown = client.get(f"/api/v1/public/tracking/{link}").json()["delivery_code"]
    assert shown["code"] == card["code"] and shown["minutes_left"] >= 1
    # passing it on by hand does not hide it from the customer's own page
    client.post(f"/api/v1/tenants/{t}/delivery-codes/{card['id']}/sent")
    assert client.get(f"/api/v1/public/tracking/{link}").json()["delivery_code"]["code"] == card["code"]
    # a new request replaces it, and the old one no longer works
    ask(t, job, auth)
    newest = client.get(f"/api/v1/public/tracking/{link}").json()["delivery_code"]["code"]
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/otp/verify", json={"code": newest}).json() == {"verified": True}
    assert client.get(f"/api/v1/public/tracking/{link}").json()["delivery_code"] is None  # used: gone from the page


def test_an_expired_code_leaves_the_customers_page() -> None:
    t, job, _, auth = make_job()
    link = _link(job, t)
    ask(t, job, auth)
    with Session(engine) as session:
        for otp in session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == UUID(job))).all():
            otp.expires_at = utc_now() - timedelta(minutes=1)
            session.add(otp)
        session.commit()
    assert client.get(f"/api/v1/public/tracking/{link}").json()["delivery_code"] is None
