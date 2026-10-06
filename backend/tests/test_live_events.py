from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.db.session import engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.events import OutboxEvent
from routebridge.services.events import record_event


def test_event_record_is_tenant_scoped_and_persisted() -> None:
    tenant_id = uuid4()
    with Session(engine) as session:
        session.add(Tenant(id=tenant_id, name="Live Events Test", status="active"))
        record_event(session, tenant_id, "delivery.job.updated", "delivery_job", uuid4(), {"status": "en_route"})
        session.commit()
        event = session.exec(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id)).first()
        assert event is not None
        assert event.status == "pending"
        assert event.payload["status"] == "en_route"


def test_live_events_route_is_registered_and_tenant_scoped() -> None:
    with TestClient(app) as client:
        openapi = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/tenants/{tenant_id}/events" in openapi
