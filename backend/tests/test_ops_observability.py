from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant, utc_now
from routebridge.models.reliability import IdempotencyRecord
from routebridge.services.retention import purge_expired

client = TestClient(app)
create_db_and_tables()


def test_request_id_ready_and_metrics() -> None:
    res = client.get("/ready", headers={"X-Request-ID": "trace-123"})
    assert res.status_code == 200 and res.headers["X-Request-ID"] == "trace-123"
    assert client.get("/health").headers["X-Request-ID"]
    body = client.get("/metrics").text
    assert 'routebridge_http_requests_total{route="/ready",status="2xx"}' in body
    assert "routebridge_outbox_pending" in body and "routebridge_notifications_queued" in body


def test_retention_purges_expired_idempotency_records_only() -> None:
    with Session(engine) as session:
        tenant = Tenant(name="Retention Tenant")
        session.add(tenant)
        session.flush()
        old = IdempotencyRecord(tenant_id=tenant.id, key=f"old-{uuid4()}", request_hash="x", response_json="{}", expires_at=utc_now() - timedelta(hours=1))
        fresh = IdempotencyRecord(tenant_id=tenant.id, key=f"new-{uuid4()}", request_hash="x", response_json="{}", expires_at=utc_now() + timedelta(hours=1))
        session.add_all([old, fresh])
        session.commit()
        counts = purge_expired(session)
        assert counts["idempotency_records"] >= 1
        remaining = {r.key for r in session.exec(select(IdempotencyRecord).where(IdempotencyRecord.tenant_id == tenant.id)).all()}
        assert remaining == {fresh.key}
