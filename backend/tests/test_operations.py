from fastapi.testclient import TestClient
from helpers import reset_data
from sqlmodel import Session, delete

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.events import OutboxEvent
from routebridge.models.operations import Driver, DriverAssignment, PaymentRecord, ReconciliationItem
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order, Stop
from routebridge.models.reliability import AuditEvent

client = TestClient(app)
create_db_and_tables()


def setup_function() -> None:
    with Session(engine) as session:
        reset_data(session, (OutboxEvent, AuditEvent, ReconciliationItem, PaymentRecord, DriverAssignment, Driver, Stop, DeliveryJob, Order, Customer, Merchant, Tenant))


def seed_job() -> tuple[str, str, str]:
    with Session(engine) as session:
        tenant = Tenant(name="Operations Tenant")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Merchant")
        customer = Customer(tenant_id=tenant.id, name="Customer", phone="+2348000000000")
        session.add(merchant)
        session.add(customer)
        session.flush()
        order = Order(
            tenant_id=tenant.id,
            merchant_id=merchant.id,
            customer_id=customer.id,
            external_ref="OPS-001",
            total_amount="5000.00",
            cod_amount="5000.00",
        )
        session.add(order)
        session.flush()
        job = DeliveryJob(tenant_id=tenant.id, order_id=order.id)
        session.add(job)
        session.flush()
        session.add(Stop(tenant_id=tenant.id, delivery_job_id=job.id, address_text="Lagos Mainland"))
        session.commit()
        return str(tenant.id), str(job.id), str(order.id)


def test_assignment_proof_and_exact_cod_payment() -> None:
    tenant_id, job_id, _ = seed_job()
    driver = client.post(
        f"/api/v1/tenants/{tenant_id}/drivers",
        json={"name": "Chinedu Driver", "phone": "+2348111111111"},
    )
    assert driver.status_code == 201, driver.text
    driver_id = driver.json()["id"]

    assignment = client.post(
        f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/assignments",
        json={"driver_id": driver_id},
    )
    assert assignment.status_code == 201

    for target in ("accepted", "en_route", "arrived"):
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/transitions",
            json={"target_status": target},
        )
        assert response.status_code == 200, response.text

    base = f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}"
    # A client-asserted OTP is not proof: the server must have verified a code it issued.
    forged = client.post(f"{base}/proof", json={"otp_verified": True, "recipient_name": "Customer"})
    assert forged.status_code == 409, forged.text
    issued = client.post(f"{base}/otp")
    assert issued.status_code == 201, issued.text
    wrong = client.post(f"{base}/otp/verify", json={"code": "000000" if issued.json()["debug_code"] != "000000" else "111111"})
    assert wrong.status_code == 400
    assert client.post(f"{base}/otp/verify", json={"code": issued.json()["debug_code"]}).json() == {"verified": True}
    proof = client.post(f"{base}/proof", json={"otp_verified": True, "photo_url": "https://storage.test/proof.jpg", "recipient_name": "Customer"})
    assert proof.status_code == 201, proof.text
    assert proof.json()["otp_verified"] is True

    payment = client.post(
        f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/payments",
        json={"method": "cod", "collected_amount": "5000.00"},
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["reconciliation_status"] == "matched"


def test_under_collection_creates_reconciliation_exception() -> None:
    tenant_id, job_id, _ = seed_job()
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/payments",
        json={"method": "cod", "collected_amount": "4500.00"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["reconciliation_status"] == "exception"
    assert data["expected_amount"] == "5000.00"
