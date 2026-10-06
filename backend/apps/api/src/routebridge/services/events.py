import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from redis import Redis
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.events import OutboxEvent
from routebridge.models.reliability import AuditEvent


def record_event(session: Session, tenant_id: UUID, event_type: str, aggregate_type: str, aggregate_id: UUID, payload: dict, actor_type: str = "system", actor_id: UUID | None = None) -> OutboxEvent:
    """Write the outbox event and the immutable audit entry in the caller's transaction."""
    session.add(AuditEvent(tenant_id=tenant_id, event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id, actor_type=actor_type, actor_id=actor_id, payload=payload))
    event = OutboxEvent(tenant_id=tenant_id, event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id, payload=payload)
    session.add(event)
    return event


def stream_key(tenant_id: UUID) -> str:
    return f"routebridge:events:tenant:{tenant_id}"


def publish_pending_outbox(limit: int = 100) -> int:
    settings = get_settings()
    if not settings.redis_url:
        return 0
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    published = 0
    with Session(_engine()) as session:
        now = datetime.now(timezone.utc)
        events = session.exec(select(OutboxEvent).where(OutboxEvent.status == "pending", OutboxEvent.available_at <= now).order_by(OutboxEvent.created_at).limit(limit)).all()
        for event in events:
            try:
                client_id = client.xadd(stream_key(event.tenant_id), {"event_id": str(event.id), "event_type": event.event_type, "aggregate_type": event.aggregate_type, "aggregate_id": str(event.aggregate_id), "payload": json.dumps(event.payload), "occurred_at": event.created_at.isoformat()})
                event.status = "published"
                event.published_at = datetime.now(timezone.utc)
                event.attempts += 1
                event.last_error = None
                published += 1
            except Exception as exc:
                event.attempts += 1
                event.last_error = str(exc)[:1000]
                if event.attempts >= settings.max_outbox_attempts:
                    event.status = "dead_letter"
                    client.xadd("routebridge:events:dead-letter", {"event_id": str(event.id), "tenant_id": str(event.tenant_id), "event_type": event.event_type, "payload": json.dumps(event.payload), "last_error": event.last_error})
                else:
                    event.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** event.attempts))
        session.commit()
    return published


def _engine():
    from routebridge.db.session import engine
    return engine
