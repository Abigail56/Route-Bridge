from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from redis import Redis
from sqlalchemy import func, text
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.models.core import HealthResponse, utc_now
from routebridge.models.events import OutboxEvent
from routebridge.models.operations import ReconciliationItem
from routebridge.models.plans import NotificationDelivery
from routebridge.models.workflows import Notification
from routebridge.observability import render_metrics

router = APIRouter(tags=["system"])


@router.get("/ready", response_model=HealthResponse)
def readiness(session: Session = Depends(get_session)) -> HealthResponse:
    """Readiness covers hard dependencies: the database always, Redis when configured."""
    settings = get_settings()
    try:
        session.exec(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    if settings.redis_url:
        try:
            Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    return HealthResponse(status="ready", service=settings.app_name, environment=settings.environment)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request, session: Session = Depends(get_session)) -> str:
    settings = get_settings()
    if settings.environment not in {"development", "test"}:
        if not settings.internal_api_key or request.headers.get("X-API-Key") != settings.internal_api_key:
            raise HTTPException(status_code=404)  # do not advertise the endpoint to the public
    def count(statement) -> int:
        return int(session.exec(statement).one())

    now = utc_now()
    gauges = {
        "routebridge_outbox_pending": count(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "pending")),
        "routebridge_outbox_dead_letter": count(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "dead_letter")),
        "routebridge_notifications_queued": count(select(func.count()).select_from(Notification).where(Notification.status == "queued")),
        "routebridge_notifications_failed": count(select(func.count()).select_from(Notification).where(Notification.status == "failed")),
        "routebridge_notification_oldest_due_seconds": 0,
        "routebridge_reconciliation_open": count(select(func.count()).select_from(ReconciliationItem).where(ReconciliationItem.status == "open")),
    }
    oldest = session.exec(select(func.min(NotificationDelivery.next_attempt_at)).join(Notification, Notification.id == NotificationDelivery.notification_id).where(Notification.status == "queued")).one()
    if oldest is not None:
        oldest = oldest if oldest.tzinfo else oldest.replace(tzinfo=now.tzinfo)
        gauges["routebridge_notification_oldest_due_seconds"] = max(0, int((now - oldest).total_seconds()))
    return render_metrics(gauges)
