from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.catalog import ServiceZone
from routebridge.models.core import Country, OperatingArea, Tenant
from routebridge.models.orders import Customer, Merchant, Stop
from routebridge.models.reliability import AuditEvent
from routebridge.models.plans import TrackingToken

client = TestClient(app)
create_db_and_tables()


def _setup():
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
        tenant = Tenant(name="Reports Tenant")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Reports Merchant")
        zone = ServiceZone(tenant_id=tenant.id, operating_area_id=area.id, code="Z1", name="Zone A")
        session.add_all([merchant, zone])
        session.commit()
        return tenant.id, merchant.id, zone.id


def _order(tenant_id, merchant_id, ref, **extra):
    body = {"merchant_id": str(merchant_id), "customer_name": "Ada", "customer_phone": f"+234{uuid4().int % 10**9:09d}", "external_ref": ref,
            "cod_amount": "2000", "total_amount": "2000", "address_text": "Ikeja", **extra}
    res = client.post(f"/api/v1/tenants/{tenant_id}/orders", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _deliver(tenant_id, job_id, driver_id=None, otp=True):
    base = f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}"
    if driver_id:
        assert client.post(f"{base}/assignments", json={"driver_id": driver_id}).status_code == 201
    for t in ("accepted", "en_route", "arrived"):
        assert client.post(f"{base}/transitions", json={"target_status": t}).status_code == 200
    assert client.post(f"{base}/proof", json={"photo_url": "https://s.test/p.jpg"}).status_code == 201


def test_summary_exceptions_and_payout_export() -> None:
    tenant_id, merchant_id, zone_id = _setup()
    client.post(f"/api/v1/tenants/{tenant_id}/rate-cards", json={"service_zone_id": str(zone_id), "name": "Std", "base_amount": "1500"})
    driver = client.post(f"/api/v1/tenants/{tenant_id}/drivers", json={"name": "Musa", "phone": "08011110000", "fleet_type": "partner"}).json()
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    past_start = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    past_end = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    ok = _order(tenant_id, merchant_id, "R-1", service_zone_id=str(zone_id), window_start=past_start, window_end=soon)
    _deliver(tenant_id, ok["delivery_job_id"], driver["id"])
    failing = _order(tenant_id, merchant_id, "R-2", service_zone_id=str(zone_id), window_start=past_start, window_end=past_end)
    base = f"/api/v1/tenants/{tenant_id}/delivery-jobs/{failing['delivery_job_id']}"
    client.post(f"{base}/assignments", json={"driver_id": driver["id"]})
    for t in ("accepted", "en_route", "arrived"):
        client.post(f"{base}/transitions", json={"target_status": t})
    client.post(f"{base}/transitions", json={"target_status": "failed_attempt", "reason_code": "recipient_unreachable"})

    s = client.get(f"/api/v1/tenants/{tenant_id}/reports/summary").json()
    assert s["jobs_total"] == 2 and s["jobs_delivered"] == 1
    assert s["on_time_rate"] == 1.0 and s["first_attempt_success_rate"] == 1.0
    assert s["failure_reasons"][0]["reason_code"] == "recipient_unreachable" and s["failure_reasons"][0]["zone_name"] == "Zone A"
    assert s["cost_per_stop"] == "1500.00" and s["stops_per_driver"] == 1.0

    kinds = {i["kind"] for i in client.get(f"/api/v1/tenants/{tenant_id}/exceptions").json()}
    assert {"delivery_failed", "late"} <= kinds

    start = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    export = client.get(f"/api/v1/tenants/{tenant_id}/payouts/export", params={"from": start, "to": end})
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")
    lines = export.text.strip().splitlines()
    assert lines[0].startswith("driver_id,driver_name") and "Musa,partner,1,0,1500" in lines[1]


def test_statement_import_matches_mismatches_and_unknown() -> None:
    tenant_id, merchant_id, _ = _setup()
    refs = {}
    for i, collected in enumerate(("2000.00", "2000.00")):
        o = _order(tenant_id, merchant_id, f"S-{i}")
        job = o["delivery_job_id"]
        pay = client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job}/payments", json={"method": "transfer", "collected_amount": collected, "provider_reference": f"REF-{i}-{uuid4().hex[:6]}"})
        assert pay.status_code == 201, pay.text
        refs[i] = pay.json()["provider_reference"]
    csv_body = f"reference,amount\n{refs[0]},2000.00\n{refs[1]},1800.00\nUNKNOWN-REF,500\n{refs[0]},abc\n"
    res = client.post(f"/api/v1/tenants/{tenant_id}/reconciliation/import-statement", files={"file": ("stmt.csv", csv_body, "text/csv")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["matched"] == 1 and body["mismatched"] == 1 and len(body["unmatched"]) == 1 and len(body["invalid_rows"]) == 1
    items = client.get(f"/api/v1/tenants/{tenant_id}/reconciliation").json()
    assert any(i["status"] == "open" and float(i["variance_amount"]) == -200.0 for i in items)
    assert client.post(f"/api/v1/tenants/{tenant_id}/reconciliation/import-statement", files={"file": ("x.csv", "a,b\n1,2\n", "text/csv")}).status_code == 400


def test_audit_trail_is_readable_and_append_only() -> None:
    tenant_id, merchant_id, _ = _setup()
    order = _order(tenant_id, merchant_id, "A-1")
    rows = client.get(f"/api/v1/tenants/{tenant_id}/audit", params={"aggregate_type": "order"}).json()
    assert any(r["event_type"] == "order.created" for r in rows)
    with Session(engine) as session:
        event = session.exec(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)).first()
        event.event_type = "tampered"
        session.add(event)
        with pytest.raises(RuntimeError):
            session.commit()
        session.rollback()
        session.delete(session.exec(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)).first())
        with pytest.raises(RuntimeError):
            session.commit()


def test_members_roles_and_last_owner_protection() -> None:
    tenant_id, _, _ = _setup()
    owner = client.post(f"/api/v1/tenants/{tenant_id}/members", json={"clerk_user_id": f"user_{uuid4().hex[:8]}", "role": "tenant_owner", "full_name": "Chief Owner"})
    assert owner.status_code == 201, owner.text
    assert client.post(f"/api/v1/tenants/{tenant_id}/members", json={"clerk_user_id": "user_x", "role": "wizard"}).status_code == 422
    # sole owner cannot be demoted or deactivated
    mid = owner.json()["membership_id"]
    assert client.patch(f"/api/v1/tenants/{tenant_id}/members/{mid}", json={"role": "dispatcher"}).status_code == 409
    second = client.post(f"/api/v1/tenants/{tenant_id}/members", json={"clerk_user_id": f"user_{uuid4().hex[:8]}", "role": "tenant_owner"}).json()
    assert client.patch(f"/api/v1/tenants/{tenant_id}/members/{mid}", json={"role": "dispatcher"}).status_code == 200
    assert {m["role"] for m in client.get(f"/api/v1/tenants/{tenant_id}/members").json()} == {"dispatcher", "tenant_owner"}
    assert second["role"] == "tenant_owner"


def test_privacy_export_erase_and_consent() -> None:
    tenant_id, merchant_id, _ = _setup()
    order = _order(tenant_id, merchant_id, "PR-1", landmark="Behind the market", latitude=6.5, longitude=3.3)
    token = order["tracking_token"]
    cid = str(order["customer_id"])
    export = client.get(f"/api/v1/tenants/{tenant_id}/customers/{cid}/export").json()
    assert export["customer"]["name"] == "Ada" and export["delivery_locations"][0]["landmark"] == "Behind the market"
    erase = client.post(f"/api/v1/tenants/{tenant_id}/customers/{cid}/erase")
    assert erase.status_code == 200 and erase.json()["orders_anonymised"] == 1
    with Session(engine) as session:
        customer = session.get(Customer, order["customer_id"] if not isinstance(order["customer_id"], str) else __import__("uuid").UUID(order["customer_id"]))
        assert customer.status == "erased" and customer.name == "Erased customer"
        stop = session.exec(select(Stop).where(Stop.delivery_job_id == __import__("uuid").UUID(order["delivery_job_id"]))).one()
        assert stop.address_text == "[erased]" and stop.latitude is None
    assert client.get(f"/api/v1/public/tracking/{token}").status_code == 404  # tracking link revoked
    assert client.post(f"/api/v1/tenants/{tenant_id}/customers/{cid}/erase").json()["already"] is True
    other = _order(tenant_id, merchant_id, "PR-2")
    consent = client.post(f"/api/v1/tenants/{tenant_id}/customers/{other['customer_id']}/consent", json={"purpose": "sms", "granted": False})
    assert consent.status_code == 201
    blocked = client.post(f"/api/v1/tenants/{tenant_id}/orders/{other['id']}/notifications", params={"channel": "sms", "template": "delay"})
    assert blocked.status_code == 409
