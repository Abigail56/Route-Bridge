from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.orders import Merchant
from routebridge.models.plans import NotificationDelivery
from routebridge.models.workflows import Notification

client = TestClient(app)
create_db_and_tables()


def texts_to(phone: str) -> dict[str, str]:
    with Session(engine) as session:
        rows = session.exec(select(Notification).where(Notification.recipient == phone)).all()
        return {n.template: session.exec(select(NotificationDelivery).where(NotificationDelivery.notification_id == n.id)).one().body for n in rows}


def test_the_customer_is_texted_when_the_rider_arrives_and_when_the_order_is_delivered() -> None:
    with Session(engine) as session:
        tenant = Tenant(name="Arrival Logistics")
        session.add(tenant)
        session.flush()
        shop = Merchant(tenant_id=tenant.id, name="Arrival Shop")
        session.add(shop)
        session.commit()
        t, m = str(tenant.id), str(shop.id)
    phone = f"+23480{uuid4().int % 10**8:08d}"
    order = client.post(f"/api/v1/tenants/{t}/orders", json={"merchant_id": m, "customer_name": "Ngozi", "customer_phone": phone, "external_ref": "ARR-1", "address_text": "9 Admiralty Way"}).json()
    driver = client.post(f"/api/v1/tenants/{t}/drivers", json={"name": "Rider", "phone": f"+23481{uuid4().int % 10**8:08d}"}).json()
    job = order["delivery_job_id"]
    client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/assignments", json={"driver_id": driver["id"]})
    for target in ("accepted", "en_route"):
        assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/transitions", json={"target_status": target}).status_code == 200
    assert "arrived" not in texts_to(phone)  # not before the rider is there
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/transitions", json={"target_status": "arrived"}).status_code == 200
    arrived = texts_to(phone)["arrived"]
    assert "has arrived" in arrived and "ARR-1" in arrived and "Arrival Shop" in arrived
    assert "delivered" not in texts_to(phone)
    assert client.post(f"/api/v1/tenants/{t}/delivery-jobs/{job}/transitions", json={"target_status": "delivered"}).status_code == 200
    assert "ARR-1 was delivered" in texts_to(phone)["delivered"]
