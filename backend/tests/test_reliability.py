from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from helpers import reset_data
from sqlmodel import Session, delete, select

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.events import OutboxEvent
from routebridge.models.operations import DeliveryAttempt, Driver, DriverAssignment
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order, Stop
from routebridge.models.reliability import AuditEvent, MobileSyncEvent

client = TestClient(app)
create_db_and_tables()


def setup_function() -> None:
    with Session(engine) as session:
        reset_data(session, (OutboxEvent, AuditEvent, MobileSyncEvent, DeliveryAttempt, DriverAssignment, Driver, Stop, DeliveryJob, Order, Customer, Merchant, Tenant))


def seed_job() -> tuple[str, str]:
    with Session(engine) as session:
        tenant = Tenant(name="Sync Tenant")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Sync Merchant")
        customer = Customer(tenant_id=tenant.id, name="Sync Customer", phone="+2348000000001")
        session.add_all([merchant, customer])
        session.flush()
        order = Order(tenant_id=tenant.id, merchant_id=merchant.id, customer_id=customer.id, external_ref=f"SYNC-{uuid4().hex[:8]}")
        session.add(order)
        session.flush()
        job = DeliveryJob(tenant_id=tenant.id, order_id=order.id, status="arrived")
        session.add(job)
        session.flush()
        session.add(Stop(tenant_id=tenant.id, delivery_job_id=job.id, address_text="Lagos"))
        session.commit()
        return str(tenant.id), str(job.id)


def test_mobile_sync_applies_transition_and_deduplicates_retry() -> None:
    tenant_id, job_id = seed_job()
    event_id = str(uuid4())
    payload = {
        "events": [
            {
                "event_id": event_id,
                "device_id": "driver-device-001",
                "event_type": "delivery.transition",
                "aggregate_type": "delivery_job",
                "aggregate_id": job_id,
                "payload": {"target_status": "failed_attempt", "reason_code": "recipient_unreachable"},
            }
        ]
    }

    first = client.post(f"/api/v1/tenants/{tenant_id}/mobile-sync", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["accepted_event_ids"] == [event_id]

    retry = client.post(f"/api/v1/tenants/{tenant_id}/mobile-sync", json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicate_event_ids"] == [event_id]

    with Session(engine) as session:
        job = session.get(DeliveryJob, UUID(job_id))
        assert job is not None and job.status == "failed_attempt"
        assert len(session.exec(select(MobileSyncEvent)).all()) == 1
        assert len(session.exec(select(AuditEvent).where(AuditEvent.actor_type == "driver_device")).all()) == 1  # one audit row per device event, however often it is retried
        assert len(session.exec(select(DeliveryAttempt)).all()) == 1


def test_mobile_sync_rejects_invalid_transition() -> None:
    tenant_id, job_id = seed_job()
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/mobile-sync",
        json={
            "events": [
                {
                    "event_id": str(uuid4()),
                    "device_id": "driver-device-001",
                    "event_type": "delivery.transition",
                    "aggregate_type": "delivery_job",
                    "aggregate_id": job_id,
                    "payload": {"target_status": "assigned"},
                }
            ]
        },
    )
    assert response.status_code == 200
    assert len(response.json()["rejected_event_ids"]) == 1
