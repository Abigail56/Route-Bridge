import json
import time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.orders import Merchant
from routebridge.models.reliability import MobileSyncEvent
from routebridge.routes.intake import sign, tenant_signing_secret
from routebridge.services.connectors import ConnectorError, from_shopify, from_woocommerce

client = TestClient(app)
create_db_and_tables()


@pytest.fixture(autouse=True)
def secrets_configured():
    settings = get_settings()
    old = (settings.webhook_signing_secret, settings.driver_token_secret)
    settings.webhook_signing_secret = "w" * 32
    settings.driver_token_secret = "d" * 32
    yield
    settings.webhook_signing_secret, settings.driver_token_secret = old


def _tenant():
    with Session(engine) as session:
        tenant = Tenant(name="Intake Tenant")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Shop")
        session.add(merchant)
        session.commit()
        return tenant.id, merchant.id


def _post_signed(tenant_id, merchant_id, payload, source="shopify", event_id=None, timestamp=None, secret=None):
    body = json.dumps(payload).encode()
    ts = str(timestamp if timestamp is not None else int(time.time()))
    sig = sign(secret or tenant_signing_secret(tenant_id), ts, body)
    headers = {"X-Webhook-Timestamp": ts, "X-Webhook-Signature": sig, "Content-Type": "application/json"}
    if event_id:
        headers["X-Webhook-Event-ID"] = event_id
    return client.post(f"/api/v1/webhooks/orders/{tenant_id}", params={"merchant_id": str(merchant_id), "source": source}, content=body, headers=headers)


SHOPIFY = {
    "id": 9001, "name": "#1001", "total_price": "15000.00", "currency": "NGN", "gateway": "Cash on Delivery (COD)",
    "customer": {"first_name": "Ngozi", "last_name": "Eze", "phone": "+2348012340000"},
    "shipping_address": {"name": "Ngozi Eze", "address1": "5 Admiralty Way", "city": "Lekki", "province": "Lagos", "phone": "+2348012340000"},
    "note": "Call at the gate",
}


def test_connectors_map_cod_and_prepaid() -> None:
    merchant = uuid4()
    cod = from_shopify(SHOPIFY, merchant)
    assert cod.cod_amount == Decimal("15000.00") and cod.external_ref == "#1001" and "Lekki" in cod.address_text
    prepaid = from_shopify({**SHOPIFY, "gateway": "paystack", "financial_status": "paid"}, merchant)
    assert prepaid.cod_amount == Decimal("0.00") and prepaid.total_amount == Decimal("15000.00")
    woo = from_woocommerce({"number": "77", "total": "5000", "payment_method": "cod", "shipping": {"first_name": "A", "last_name": "B", "address_1": "1 Road", "city": "Ikeja", "phone": "08031234567"}, "billing": {}}, merchant)
    assert woo.cod_amount == Decimal("5000.00") and woo.customer_name == "A B"
    with pytest.raises(ConnectorError):
        from_shopify({**SHOPIFY, "shipping_address": {}}, merchant)


def test_signed_intake_creates_order_once_and_enforces_signature_and_replay_window() -> None:
    tenant_id, merchant_id = _tenant()
    ok = _post_signed(tenant_id, merchant_id, SHOPIFY, event_id="evt-1")
    assert ok.status_code == 202, ok.text
    assert ok.json()["status"] == "accepted"
    assert _post_signed(tenant_id, merchant_id, SHOPIFY, event_id="evt-1").json()["status"] == "duplicate"
    # same storefront order re-sent under a new event id must not duplicate it
    assert _post_signed(tenant_id, merchant_id, SHOPIFY, event_id="evt-2").json()["status"] == "duplicate"
    orders = client.get(f"/api/v1/tenants/{tenant_id}/orders").json()
    assert len(orders) == 1 and orders[0]["external_ref"] == "#1001" and orders[0]["customer_name"] == "Ngozi Eze"

    assert _post_signed(tenant_id, merchant_id, SHOPIFY, event_id="evt-3", secret="wrong").status_code == 401
    assert _post_signed(tenant_id, merchant_id, {**SHOPIFY, "name": "#1002"}, event_id="evt-4", timestamp=int(time.time()) - 3600).status_code == 401
    assert _post_signed(tenant_id, merchant_id, {"id": 1}, event_id="evt-5").status_code == 422
    # another tenant's secret is useless here
    other, _ = _tenant()
    assert _post_signed(tenant_id, merchant_id, {**SHOPIFY, "name": "#1003"}, event_id="evt-6", secret=tenant_signing_secret(other)).status_code == 401


def _driver_setup():
    tenant_id, merchant_id = _tenant()
    order = client.post(f"/api/v1/tenants/{tenant_id}/orders", json={
        "merchant_id": str(merchant_id), "customer_name": "Ada", "customer_phone": "+2348055550000", "external_ref": "D-1",
        "cod_amount": "4000", "total_amount": "4000", "address_text": "Surulere", "landmark": "By the bridge"}).json()
    driver = client.post(f"/api/v1/tenants/{tenant_id}/drivers", json={"name": "Chisom Obi", "phone": "08066660000"}).json()
    job = order["delivery_job_id"]
    assert client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job}/assignments", json={"driver_id": driver["id"]}).status_code == 201
    token = client.post(f"/api/v1/tenants/{tenant_id}/drivers/{driver['id']}/token").json()["access_token"]
    return tenant_id, order, driver, job, {"Authorization": f"Bearer {token}"}


def _event(job, kind, payload):
    return {"event_id": str(uuid4()), "device_id": "android-1", "event_type": kind, "aggregate_type": "delivery_job", "aggregate_id": job, "payload": payload}


def test_driver_token_pull_and_offline_sync_full_delivery() -> None:
    tenant_id, order, driver, job, auth = _driver_setup()
    assert client.get(f"/api/v1/driver/tenants/{tenant_id}/jobs").status_code == 401
    assert client.get(f"/api/v1/driver/tenants/{tenant_id}/jobs", headers={"Authorization": "Bearer junk"}).status_code == 401
    jobs = client.get(f"/api/v1/driver/tenants/{tenant_id}/jobs", headers=auth).json()
    assert len(jobs) == 1 and jobs[0]["reference"] == "D-1" and jobs[0]["customer_phone_masked"].endswith("0000") and "*" in jobs[0]["customer_phone_masked"]
    assert "customer_phone" not in jobs[0]
    # a token is only valid for its own tenant
    other_tenant, _ = _tenant()
    assert client.get(f"/api/v1/driver/tenants/{other_tenant}/jobs", headers=auth).status_code == 403

    # server texts the OTP; the driver never sees it. (Dev log provider exposes it to staff only via debug_code.)
    otp = client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/otp", headers=auth)
    assert otp.status_code == 409  # not en route yet
    events = [_event(job, "delivery.transition", {"target_status": t}) for t in ("accepted", "en_route", "arrived")]
    res = client.post(f"/api/v1/driver/tenants/{tenant_id}/sync", json={"events": events}, headers=auth).json()
    assert len(res["accepted_event_ids"]) == 3
    otp = client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/otp", headers=auth)
    assert otp.status_code == 201 and "debug_code" not in otp.json()
    staff_otp = client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job}/otp").json()["debug_code"]  # re-issue as staff to read dev code

    bad_proof = _event(job, "delivery.proof", {"otp_code": "999999" if staff_otp != "999999" else "111111", "recipient_name": "Ada"})
    good_proof = _event(job, "delivery.proof", {"otp_code": staff_otp, "recipient_name": "Ada"})
    gps = _event(job, "driver.location", {"latitude": 6.5, "longitude": 3.35})
    payment = _event(job, "delivery.payment", {"collected_amount": "4000.00", "method": "cod"})
    res = client.post(f"/api/v1/driver/tenants/{tenant_id}/sync", json={"events": [bad_proof, good_proof, gps, payment, good_proof]}, headers=auth).json()
    assert res["rejected_event_ids"] == [bad_proof["event_id"]]
    assert set(res["accepted_event_ids"]) == {good_proof["event_id"], gps["event_id"], payment["event_id"]}
    assert good_proof["event_id"] in res["accepted_event_ids"]
    # idempotent replay of the whole queue
    again = client.post(f"/api/v1/driver/tenants/{tenant_id}/sync", json={"events": [good_proof, payment]}, headers=auth).json()
    assert set(again["duplicate_event_ids"]) == {good_proof["event_id"], payment["event_id"]}

    row = client.get(f"/api/v1/tenants/{tenant_id}/orders").json()[0]
    assert row["job_status"] == "delivered"
    with Session(engine) as session:
        # OTP codes never reach the sync log
        stored = session.exec(select(MobileSyncEvent).where(MobileSyncEvent.tenant_id == tenant_id)).all()
        assert stored and not any("otp_code" in e.payload for e in stored)
    drivers = client.get(f"/api/v1/tenants/{tenant_id}/drivers").json()
    assert drivers[0]["latitude"] == 6.5 and drivers[0]["status"] == "available"


def test_driver_cannot_touch_jobs_not_assigned_to_them_and_correction_event() -> None:
    tenant_id, order, driver, job, auth = _driver_setup()
    other_order = client.post(f"/api/v1/tenants/{tenant_id}/orders", json={
        "merchant_id": order["merchant_id"], "customer_name": "Bola", "customer_phone": "+2348077770000", "external_ref": "D-2", "address_text": "Yaba"}).json()
    stranger = _event(other_order["delivery_job_id"], "delivery.transition", {"target_status": "cancelled"})
    fix = _event(job, "location.correction", {"landmark": "Blue gate, 2nd floor", "latitude": 6.49, "longitude": 3.36})
    res = client.post(f"/api/v1/driver/tenants/{tenant_id}/sync", json={"events": [stranger, fix]}, headers=auth).json()
    assert res["rejected_event_ids"] == [stranger["event_id"]] and res["accepted_event_ids"] == [fix["event_id"]]
    mine = [o for o in client.get(f"/api/v1/tenants/{tenant_id}/orders").json() if o["external_ref"] == "D-1"][0]
    assert mine["landmark"] == "Blue gate, 2nd floor" and mine["location_confidence"] == "driver_confirmed" and mine["location_corrected"]
    # an offline driver's token stops working
    client.patch(f"/api/v1/tenants/{tenant_id}/drivers/{driver['id']}", json={"status": "offline"})
