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
from routebridge.models.plans import DeliveryOtp
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


def test_the_rider_asks_and_nothing_is_texted_but_the_dashboard_gets_a_card() -> None:
    t, job, ref, auth = make_job()
    answer = ask(t, job, auth)
    assert answer.status_code == 201 or answer.status_code == 200, answer.text
    body = answer.json()
    assert body["relay"] is True and body["sent"] is False and "code" not in body and "debug_code" not in body  # the rider never sees it
    with Session(engine) as session:
        assert session.exec(select(Notification).where(Notification.tenant_id == UUID(t), Notification.template == "delivery_otp")).all() == []  # no SMS was queued
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
    with Session(engine) as session:
        assert all(o.relay_code is None for o in session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == UUID(job))).all())  # nothing kept


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
    assert pending(t) == []
    with Session(engine) as session:
        assert len(session.exec(select(Notification).where(Notification.tenant_id == UUID(t), Notification.template == "delivery_otp")).all()) == 1
