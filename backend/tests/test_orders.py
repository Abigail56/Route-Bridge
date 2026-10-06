from fastapi.testclient import TestClient
from helpers import reset_data
from sqlmodel import Session, delete, select

from routebridge.db.session import engine
from routebridge.db.session import create_db_and_tables
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.events import OutboxEvent
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order, Stop
from routebridge.models.reliability import AuditEvent, IdempotencyRecord

client = TestClient(app)


create_db_and_tables()


def setup_function() -> None:
    with Session(engine) as session:
        reset_data(session, (OutboxEvent, IdempotencyRecord, AuditEvent, Stop, DeliveryJob, Order, Customer, Merchant, Tenant))


def test_create_and_list_order() -> None:
    with Session(engine) as session:
        tenant = Tenant(name="Demo Merchant Group")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Enugu Supply Co")
        session.add(merchant)
        session.commit()
        tenant_id, merchant_id = tenant.id, merchant.id

    payload = {
        "merchant_id": str(merchant_id),
        "customer_name": "Ada Okafor",
        "customer_phone": "+2348012345678",
        "external_ref": "RB-ORDER-001",
        "total_amount": "12500.00",
        "cod_amount": "12500.00",
        "address_text": "12 Independence Layout, Enugu",
        "landmark": "Near Shoprite",
        "delivery_notes": "Call on arrival",
        "latitude": 6.4499,
        "longitude": 7.5086,
        "location_confidence": "driver_confirmed",
    }
    response = client.post(f"/api/v1/tenants/{tenant_id}/orders", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["external_ref"] == "RB-ORDER-001"
    assert data["status"] == "created"
    assert data["stop_status"] == "pending"
    assert data["cod_amount"] == "12500.00"

    listed = client.get(f"/api/v1/tenants/{tenant_id}/orders")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_order_cannot_use_another_tenants_merchant() -> None:
    with Session(engine) as session:
        first = Tenant(name="First Tenant")
        second = Tenant(name="Second Tenant")
        session.add(first)
        session.add(second)
        session.flush()
        merchant = Merchant(tenant_id=first.id, name="First Merchant")
        session.add(merchant)
        session.commit()
        first_id, second_id, merchant_id = first.id, second.id, merchant.id

    payload = {
        "merchant_id": str(merchant_id),
        "customer_name": "Customer",
        "customer_phone": "+2348099999999",
        "external_ref": "RB-ORDER-CROSS-TENANT",
        "address_text": "Lagos Island",
    }
    response = client.post(f"/api/v1/tenants/{second_id}/orders", json=payload)
    assert response.status_code == 404
    # no order may have been created for either tenant
    assert client.get(f"/api/v1/tenants/{second_id}/orders").json() == []
    assert client.get(f"/api/v1/tenants/{first_id}/orders").json() == []


def test_order_idempotency_replays_same_result_and_audit_once() -> None:
    with Session(engine) as session:
        tenant = Tenant(name="Idempotent Tenant")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Idempotent Merchant")
        session.add(merchant)
        session.commit()
        tenant_id, merchant_id = tenant.id, merchant.id

    payload = {
        "merchant_id": str(merchant_id),
        "customer_name": "Customer",
        "customer_phone": "+2348077777777",
        "external_ref": "RB-IDEMPOTENT-001",
        "address_text": "Wuse 2, Abuja",
    }
    headers = {"Idempotency-Key": "mobile-order-001"}
    first = client.post(f"/api/v1/tenants/{tenant_id}/orders", json=payload, headers=headers)
    second = client.post(f"/api/v1/tenants/{tenant_id}/orders", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    with Session(engine) as session:
        assert len(session.exec(select(IdempotencyRecord)).all()) == 1
        assert len(session.exec(select(AuditEvent).where(AuditEvent.event_type == "order.created")).all()) == 1
