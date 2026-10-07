"""Web push for drivers: a notification on the rider's phone when a delivery is assigned, even if the app is closed.

It is switched on by setting ROUTEBRIDGE_VAPID_PUBLIC_KEY / _PRIVATE_KEY (make them with `python -m routebridge.tools.gen_secrets`). Sending never raises:
a failed push must not lose or delay the assignment itself.
"""
import json
import logging
from uuid import UUID

from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.core import utc_now
from routebridge.models.events import OutboxEvent
from routebridge.models.orders import DeliveryJob, Order, Stop
from routebridge.models.push import PushSubscription

log = logging.getLogger(__name__)
GONE = (404, 410)  # the phone's push service says this subscription no longer exists
MAX_FAILURES = 5


def push_enabled() -> bool:
    settings = get_settings()
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def _send(subscription: PushSubscription, payload: dict) -> int | None:
    """Returns None when delivered, or the HTTP status that refused it (0 = could not reach the push service)."""
    from pywebpush import WebPushException, webpush

    settings = get_settings()
    try:
        webpush(
            subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=json.dumps(payload), vapid_private_key=settings.vapid_private_key, vapid_claims={"sub": settings.vapid_subject}, ttl=3600, timeout=5,
        )
        return None
    except WebPushException as exc:
        return exc.response.status_code if exc.response is not None else 0
    except Exception:  # noqa: BLE001 - never let a push problem escape
        log.exception("push send failed")
        return 0


def notify_driver(session: Session, driver_id: UUID, title: str, body: str, url: str = "/driver") -> int:
    """Push to every phone registered for this driver. Returns how many were delivered. The caller commits."""
    if not push_enabled():
        return 0
    delivered = 0
    for sub in session.exec(select(PushSubscription).where(PushSubscription.driver_id == driver_id)).all():
        failed = _send(sub, {"title": title, "body": body, "url": url})
        if failed is None:
            sub.failures, sub.last_sent_at = 0, utc_now()
            session.add(sub)
            delivered += 1
        elif failed in GONE or sub.failures + 1 >= MAX_FAILURES:
            session.delete(sub)
        else:
            sub.failures += 1
            session.add(sub)
    return delivered


def handle_event(session: Session, event: OutboxEvent) -> None:
    """Called by the outbox worker once per event. Only a new assignment pushes anything."""
    if event.event_type != "delivery.assignment.created" or not push_enabled():
        return
    try:
        driver_id = UUID(str(event.payload.get("driver_id")))
        job = session.get(DeliveryJob, event.aggregate_id)
        order = session.get(Order, job.order_id) if job else None
        stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id).order_by(Stop.sequence)).first() if job else None
        body = " · ".join(part for part in (order.external_ref if order else None, stop.address_text if stop else None) if part) or "Open the app to see it"
        notify_driver(session, driver_id, "New delivery assigned", body)
    except Exception:  # noqa: BLE001
        log.exception("could not push assignment %s", event.id)
