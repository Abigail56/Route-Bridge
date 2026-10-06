from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.catalog import ServiceZone
from routebridge.models.core import Country, OperatingArea, Tenant
from routebridge.models.orders import Merchant, Stop
from routebridge.models.plans import DeliveryOtp  # noqa: F401
from routebridge.models.workflows import Notification
from routebridge.models.plans import NotificationDelivery
from routebridge.services.notifications import dispatch_pending
from routebridge.services.location import decode_plus_code, is_valid_plus_code, location_score

client = TestClient(app)
create_db_and_tables()


def _tenant_with_zone():
    with Session(engine) as session:
        country = session.exec(select(Country).where(Country.iso_code == "ZZ")).first()
        if country is None:
            country = Country(iso_code="ZZ", name="Testland")
            session.add(country)
            session.flush()
        area = session.exec(select(OperatingArea).where(OperatingArea.code == "TST")).first()
        if area is None:
            area = OperatingArea(country_id=country.id, code="TST", name="Test City")
            session.add(area)
        tenant = Tenant(name="Plan Tenant")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Plan Merchant")
        zone = ServiceZone(tenant_id=tenant.id, operating_area_id=area.id, code="ZN1", name="Zone One")
        session.add_all([merchant, zone])
        session.commit()
        return tenant.id, merchant.id, zone.id


def _order(tenant_id, merchant_id, ref, **extra):
    body = {
        "merchant_id": str(merchant_id), "customer_name": "Ada Okafor", "customer_phone": "+2348033333333",
        "external_ref": ref, "cod_amount": "3000", "total_amount": "3000", "address_text": "12 Allen Ave, Ikeja",
        "landmark": "Opposite the blue gate", **extra,
    }
    return client.post(f"/api/v1/tenants/{tenant_id}/orders", json=body)


def test_plus_code_helpers_and_score() -> None:
    assert is_valid_plus_code("8FVC9G8F+6X") and not is_valid_plus_code("nonsense")
    lat, lng = decode_plus_code("8FVC9G8F+6X")
    assert 47.36 < lat < 47.37 and 8.52 < lng < 8.53
    assert location_score("unverified", False, False, False) < location_score("driver_confirmed", True, True, True) == 100


def test_order_with_zone_window_plus_code_and_tracking_token() -> None:
    tenant_id, merchant_id, zone_id = _tenant_with_zone()
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    res = _order(tenant_id, merchant_id, "P-1", plus_code="8FVC9G8F+6X", recipient_available=True, service_zone_id=str(zone_id),
                 window_start=start.isoformat(), window_end=(start + timedelta(hours=2)).isoformat())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["plus_code"] == "8FVC9G8F+6X" and body["service_zone_id"] == str(zone_id) and body["recipient_available"] is True
    assert body["tracking_token"] and body["location_score"] >= 30
    # plus code supplied coordinates for the stop
    with Session(engine) as session:
        stop = session.exec(select(Stop).where(Stop.id == UUID(body["stop_id"]))).one()
        assert stop.latitude is not None

    bad_window = _order(tenant_id, merchant_id, "P-2", window_start=start.isoformat(), window_end=(start - timedelta(hours=1)).isoformat())
    assert bad_window.status_code == 422
    assert _order(tenant_id, merchant_id, "P-3", plus_code="not-a-code").status_code == 422


def test_corrections_preserve_original_and_update_effective_location() -> None:
    tenant_id, merchant_id, _ = _tenant_with_zone()
    order = _order(tenant_id, merchant_id, "C-1").json()
    job_id = order["delivery_job_id"]
    res = client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/location-corrections", json={"landmark": "Yellow gate behind the church", "latitude": 6.6, "longitude": 3.35, "reason": "driver call"})
    assert res.status_code == 201, res.text
    assert client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/location-corrections", json={}).status_code == 422
    row = client.get(f"/api/v1/tenants/{tenant_id}/orders").json()[0]
    assert row["landmark"] == "Yellow gate behind the church" and row["location_corrected"] is True
    with Session(engine) as session:  # the original stop is untouched
        stop = session.exec(select(Stop).where(Stop.id == UUID(order["stop_id"]))).one()
        assert stop.landmark == "Opposite the blue gate" and stop.latitude is None
    assert len(client.get(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/location-corrections").json()) == 1


def test_public_tracking_correction_consent_and_expiry() -> None:
    tenant_id, merchant_id, _ = _tenant_with_zone()
    order = _order(tenant_id, merchant_id, "T-1").json()
    token = order["tracking_token"]
    info = client.get(f"/api/v1/public/tracking/{token}")
    assert info.status_code == 200
    data = info.json()
    assert data["reference"] == "T-1" and data["status"] == "pending" and "customer_phone" not in str(data)
    assert client.get("/api/v1/public/tracking/not-a-real-token").status_code == 404

    fix = client.post(f"/api/v1/public/tracking/{token}/correction", json={"landmark": "Call me at the junction", "recipient_available": False})
    assert fix.status_code == 201
    assert client.get(f"/api/v1/public/tracking/{token}").json()["location"]["landmark"] == "Call me at the junction"

    # opting out of SMS stops new notifications to this customer
    assert client.post(f"/api/v1/public/tracking/{token}/consent", json={"purpose": "sms", "granted": False}).status_code == 201
    blocked = client.post(f"/api/v1/tenants/{tenant_id}/orders/{order['id']}/notifications", params={"channel": "sms", "template": "delay"})
    assert blocked.status_code == 409


def test_status_changes_queue_and_send_notifications_with_tracking_link() -> None:
    tenant_id, merchant_id, _ = _tenant_with_zone()
    order = _order(tenant_id, merchant_id, "N-1").json()
    driver = client.post(f"/api/v1/tenants/{tenant_id}/drivers", json={"name": "Musa Bello", "phone": "08099999999"}).json()
    job_id = order["delivery_job_id"]
    assert client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/assignments", json={"driver_id": driver["id"]}).status_code == 201
    with Session(engine) as session:
        templates = {n.template for n in session.exec(select(Notification).where(Notification.order_id == UUID(order["id"]))).all()}
        assert {"order_confirmed", "driver_assigned"} <= templates
        counts = dispatch_pending(session, tenant_id=tenant_id)
        assert counts["sent"] >= 2
        sent = session.exec(select(Notification).where(Notification.order_id == UUID(order["id"]), Notification.status == "sent")).all()
        assert sent and all(n.provider_message_id for n in sent)
        assert all(d.body == "[sent]" for d in session.exec(select(NotificationDelivery).where(NotificationDelivery.tenant_id == tenant_id)).all())


def test_batches_group_by_zone_and_assign_multiple_jobs_and_driver_stays_busy() -> None:
    tenant_id, merchant_id, zone_id = _tenant_with_zone()
    jobs = [_order(tenant_id, merchant_id, f"B-{i}", service_zone_id=str(zone_id), latitude=6.5 + i / 100, longitude=3.3).json()["delivery_job_id"] for i in range(3)]
    batches = client.get(f"/api/v1/tenants/{tenant_id}/dispatch/batches").json()
    assert len(batches) == 1 and batches[0]["zone_name"] == "Zone One" and len(batches[0]["suggested_sequence"]) == 3
    driver = client.post(f"/api/v1/tenants/{tenant_id}/drivers", json={"name": "Ibrahim", "phone": "08011112222"}).json()
    result = client.post(f"/api/v1/tenants/{tenant_id}/dispatch/batches/assign", json={"job_ids": jobs, "driver_id": driver["id"]}).json()
    assert len(result["assigned"]) == 3 and not result["failed"]
    # finishing one job must not free a driver who still has others
    first = jobs[0]
    for target in ("accepted", "en_route", "arrived"):
        client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{first}/transitions", json={"target_status": target})
    client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{first}/transitions", json={"target_status": "cancelled"})
    drivers = client.get(f"/api/v1/tenants/{tenant_id}/drivers").json()
    assert [d["status"] for d in drivers if d["id"] == driver["id"]] == ["busy"]
    # roster: offline drivers can't be assigned
    offline = client.post(f"/api/v1/tenants/{tenant_id}/drivers", json={"name": "Off Duty", "phone": "08033334444"}).json()
    assert client.patch(f"/api/v1/tenants/{tenant_id}/drivers/{offline['id']}", json={"status": "offline"}).status_code == 200
    new_job = _order(tenant_id, merchant_id, "B-9").json()["delivery_job_id"]
    assert client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{new_job}/assignments", json={"driver_id": offline["id"]}).status_code == 409


def test_rate_card_and_zones() -> None:
    tenant_id, _, zone_id = _tenant_with_zone()
    card = client.post(f"/api/v1/tenants/{tenant_id}/rate-cards", json={"service_zone_id": str(zone_id), "name": "Standard", "base_amount": "1500"})
    assert card.status_code == 201, card.text
    assert client.get(f"/api/v1/tenants/{tenant_id}/rate-cards").json()[0]["name"] == "Standard"
    assert [z["name"] for z in client.get(f"/api/v1/tenants/{tenant_id}/zones").json()] == ["Zone One"]


def test_reissue_tracking_link_revokes_old_token() -> None:
    tenant_id, merchant_id, _ = _tenant_with_zone()
    order = _order(tenant_id, merchant_id, "RL-1").json()
    old = order["tracking_token"]
    new = client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{order['delivery_job_id']}/tracking-link/reissue").json()["tracking_token"]
    assert new != old
    assert client.get(f"/api/v1/public/tracking/{old}").status_code == 404
    assert client.get(f"/api/v1/public/tracking/{new}").status_code == 200
