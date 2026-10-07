"""Customer/merchant notifications: templating, consent, queueing, sending with retry and SMS fallback."""
import logging
from datetime import timedelta
from uuid import UUID

from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.core import utc_now
from routebridge.models.operations import Driver
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order
from routebridge.models.plans import ConsentRecord, NotificationDelivery, TrackingToken
from routebridge.models.workflows import Notification
from routebridge.providers import get_messaging_provider
from routebridge.services.events import record_event

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5

TEMPLATES: dict[str, str] = {
    "order_confirmed": "{merchant}: your order {reference} is confirmed. Track it: {tracking_url}",
    "driver_assigned": "{merchant}: a driver has been assigned to order {reference}. Track it: {tracking_url}",
    "en_route": "{merchant}: order {reference} is on the way. Track it: {tracking_url}",
    "arrived": "{merchant}: your driver has arrived with order {reference}. Please be ready to receive it.",
    "delivered": "{merchant}: order {reference} was delivered. Thank you!",
    "failed_attempt": "{merchant}: we could not deliver order {reference}. We will contact you to reschedule. {tracking_url}",
    "rescheduled": "{merchant}: delivery of order {reference} has been rescheduled. {tracking_url}",
    "delivery_otp": "{merchant}: your delivery code for order {reference} is {code}. Share it only with your driver.",
    "delay": "{merchant}: order {reference} is running late. Track it: {tracking_url}",
    "driver_message": "{merchant} - your driver {driver} says about order {reference}: {text}",
}

# Job status -> template queued automatically when the status changes.
STATUS_TEMPLATES = {
    "assigned": "driver_assigned",
    "en_route": "en_route",
    "arrived": "arrived",
    "delivered": "delivered",
    "failed_attempt": "failed_attempt",
    "rescheduled": "rescheduled",
}


def has_consent(session: Session, tenant_id: UUID, customer_id: UUID, purpose: str) -> bool:
    """Transactional delivery messages are allowed unless the customer has explicitly opted out."""
    latest = session.exec(
        select(ConsentRecord)
        .where(ConsentRecord.tenant_id == tenant_id, ConsentRecord.customer_id == customer_id, ConsentRecord.purpose == purpose)
        .order_by(ConsentRecord.recorded_at.desc())
    ).first()
    return latest is None or latest.granted


def tracking_url(session: Session, job_id: UUID | None) -> str:
    if job_id is None:
        return ""
    token = session.exec(select(TrackingToken).where(TrackingToken.delivery_job_id == job_id, TrackingToken.revoked.is_(False)).order_by(TrackingToken.created_at.desc())).first()
    return f"{get_settings().public_tracking_base_url.rstrip('/')}/{token.token}" if token else ""


def queue_notification(
    session: Session,
    order: Order,
    template: str,
    channel: str = "sms",
    job: DeliveryJob | None = None,
    extra: dict[str, str] | None = None,
) -> Notification | None:
    """Queue a message to the order's customer. Returns None when the customer opted out of the channel."""
    if template not in TEMPLATES:
        raise ValueError(f"Unknown notification template: {template}")
    customer = session.get(Customer, order.customer_id)
    if customer is None or customer.status != "active":
        return None
    if not has_consent(session, order.tenant_id, customer.id, channel):
        return None
    merchant = session.get(Merchant, order.merchant_id)
    if job is None:
        job = session.exec(select(DeliveryJob).where(DeliveryJob.order_id == order.id)).first()
    variables = {"merchant": merchant.name if merchant else "RouteBridge", "reference": order.external_ref, "tracking_url": tracking_url(session, job.id if job else None), "code": "", **(extra or {})}
    body = TEMPLATES[template].format(**variables).replace("  ", " ").strip()
    notification = Notification(tenant_id=order.tenant_id, order_id=order.id, channel=channel, recipient=customer.phone, template=template)
    session.add(notification)
    session.flush()
    session.add(NotificationDelivery(notification_id=notification.id, tenant_id=order.tenant_id, body=body[:1000]))
    record_event(session, order.tenant_id, "notification.queued", "order", order.id, {"notification_id": str(notification.id), "channel": channel, "template": template})
    return notification


def queue_merchant_message(session: Session, tenant_id: UUID, merchant: Merchant, template: str, body: str, order_id: UUID | None = None) -> Notification | None:
    """A text to the shop's own contact number (about its orders). Nothing is queued when the shop has no number or switched these off."""
    if not merchant.contact_phone or not merchant.notify_orders:
        return None
    notification = Notification(tenant_id=tenant_id, order_id=order_id, channel="sms", recipient=merchant.contact_phone, template=template)
    session.add(notification)
    session.flush()
    session.add(NotificationDelivery(notification_id=notification.id, tenant_id=tenant_id, body=body[:1000]))
    record_event(session, tenant_id, "notification.queued", "merchant", merchant.id, {"notification_id": str(notification.id), "channel": "sms", "template": template})
    return notification


def notify_status_change(session: Session, job: DeliveryJob, new_status: str) -> None:
    template = STATUS_TEMPLATES.get(new_status)
    if template is None:
        return
    order = session.get(Order, job.order_id)
    if order is not None:
        queue_notification(session, order, template, job=job)


def dispatch_pending(session: Session, limit: int = 50, tenant_id: UUID | None = None) -> dict[str, int]:
    """Send due notifications. WhatsApp failures fall back to SMS; failures retry with exponential backoff."""
    now = utc_now()
    query = (
        select(Notification, NotificationDelivery)
        .join(NotificationDelivery, NotificationDelivery.notification_id == Notification.id)
        .where(Notification.status == "queued", NotificationDelivery.next_attempt_at <= now)
    )
    if tenant_id is not None:
        query = query.where(Notification.tenant_id == tenant_id)
    due = session.exec(query.order_by(Notification.created_at).limit(limit)).all()
    counts = {"sent": 0, "retry": 0, "failed": 0}
    for notification, delivery in due:
        message_id = None
        error = ""
        for channel in ([notification.channel, "sms"] if notification.channel == "whatsapp" else [notification.channel]):
            provider = get_messaging_provider(channel)
            if provider is None:
                error = f"No provider configured for {channel}"
                continue
            try:
                message_id = provider.send(notification.recipient, delivery.body)
                notification.channel = channel  # record the channel that actually delivered it
                break
            except Exception as exc:  # provider/network failure: keep for retry
                error = f"{channel}: {exc}"[:500]
        if message_id is not None:
            notification.status = "sent"
            notification.provider_message_id = message_id[:200]
            notification.sent_at = utc_now()
            delivery.body = "[sent]"  # do not retain OTPs or tracking links after delivery
            delivery.last_error = None
            counts["sent"] += 1
        else:
            delivery.attempts += 1
            delivery.last_error = error
            if delivery.attempts >= MAX_ATTEMPTS:
                notification.status = "failed"
                counts["failed"] += 1
            else:
                delivery.next_attempt_at = now + timedelta(seconds=min(900, 30 * 2 ** delivery.attempts))
                counts["retry"] += 1
        session.add(notification)
        session.add(delivery)
    session.commit()
    return counts


def load_driver_name(session: Session, driver_id: UUID | None) -> str | None:
    driver = session.get(Driver, driver_id) if driver_id else None
    return driver.name if driver else None
