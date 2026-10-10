"""The customer's delivery code is what stops a rider from marking a parcel delivered when it was not."""
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.orders import Merchant
from routebridge.models.reliability import AuditEvent

client = TestClient(app)
create_db_and_tables()


@pytest.fixture(autouse=True)
def settings_for_codes():
    settings = get_settings()
    old = (settings.driver_token_secret, settings.otp_delivery, settings.require_delivery_code)
    settings.driver_token_secret, settings.otp_delivery, settings.require_delivery_code = "d" * 32, "dashboard", True
    yield settings
    settings.driver_token_secret, settings.otp_delivery, settings.require_delivery_code = old


def arrived_job():
    with Session(engine) as session:
        tenant = Tenant(name="Code Required Logistics")
        session.add(tenant)
        session.flush()
        shop = Merchant(tenant_id=tenant.id, name="Code Shop")
        session.add(shop)
        session.commit()
        t, m = str(tenant.id), str(shop.id)
    order = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": m, "customer_name": "Chidi", "customer_phone": "08031112222", "external_ref": f"CR-{uuid4().hex[:5]}", "address_text": "4 Bode Road"}).json()
    driver = client.post(f"/api/v1/tenants/{t}/drivers", json={"name": "Musa Rider", "phone": f"+23480{uuid4().int % 10**8:08d}"}).json()
    job = order["delivery_job_id"]
    client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/assignments", json={"driver_id": driver["id"]})
    for target in ("accepted", "en_route", "arrived"):
        assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/transitions", json={"target_status": target}).status_code == 200
    token = client.post(f"/api/v1/tenants/{t}/drivers/{driver['id']}/token").json()["access_token"]
    return t, job, order["id"], {"Authorization": f"Bearer {token}"}


def order_view(t, order_id):
    return next(o for o in client.get(f"/api/v1/tenants/{t}/orders").json() if o["id"] == order_id)


def test_a_photo_alone_cannot_complete_a_delivery_when_codes_are_required() -> None:
    t, job, order_id, auth = arrived_job()
    refused = client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/proof", json={"photo_url": "https://example.test/parcel.jpg"})
    assert refused.status_code == 409 and "delivery code" in refused.json()["detail"]
    view = order_view(t, order_id)
    assert view["job_status"] == "arrived" and view["code_verified"] is False  # still not delivered
    assert client.get(f"/api/v1/driver/tenants/{t}/jobs", headers=auth).json()[0]["code_required"] is True


def test_the_right_code_completes_it_a_wrong_one_is_recorded_and_the_owner_sees_it_verified() -> None:
    t, job, order_id, auth = arrived_job()
    assert client.post(f"/api/v1/driver/tenants/{t}/jobs/{job}/otp", headers=auth).status_code == 201
    code = client.get(f"/api/v1/tenants/{t}/delivery-codes").json()[0]["code"]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/otp/verify", json={"code": wrong}).status_code == 400
    with Session(engine) as session:
        events = session.exec(select(AuditEvent).where(AuditEvent.tenant_id == UUID(t), AuditEvent.event_type == "delivery.code_wrong")).all()
    assert len(events) == 1 and events[0].payload == {"job_id": job, "attempts": 1}  # the guess itself is never stored
    assert order_view(t, order_id)["code_verified"] is False
    event = {"event_id": str(uuid4()), "device_id": "android-1", "event_type": "delivery.proof", "aggregate_type": "delivery_job", "aggregate_id": job, "payload": {"otp_code": code}}
    result = client.post(f"/api/v1/driver/tenants/{t}/sync", json={"events": [event]}, headers=auth).json()
    assert result["accepted_event_ids"] == [event["event_id"]]
    view = order_view(t, order_id)
    assert view["job_status"] == "delivered" and view["code_verified"] is True


def test_with_the_rule_off_a_photo_still_works_but_is_not_marked_as_code_verified(settings_for_codes) -> None:
    settings_for_codes.require_delivery_code = False
    t, job, order_id, auth = arrived_job()
    assert client.get(f"/api/v1/driver/tenants/{t}/jobs", headers=auth).json()[0]["code_required"] is False
    done = client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/proof", json={"photo_url": "https://example.test/parcel.jpg"})
    assert done.status_code == 201, done.text
    view = order_view(t, order_id)
    assert view["job_status"] == "delivered" and view["code_verified"] is False
