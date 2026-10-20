"""What the console shows next to an order beyond its status: the link the customer follows, and the evidence of delivery."""
import base64
from typing import Any

from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.operations import Driver, DriverAssignment, PaymentRecord, ProofOfDelivery
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order
from routebridge.models.workflows import Notification
from routebridge.services import storage
from routebridge.services.notifications import TEMPLATES, tracking_url
from routebridge.services.events import record_event

MAX_INLINE_BYTES = 4 * 1024 * 1024
SHARE_CHANNELS = ("sms", "whatsapp")


def _job_of(session: Session, order: Order) -> DeliveryJob | None:
    return session.exec(select(DeliveryJob).where(DeliveryJob.order_id == order.id)).first()


def tracking_share(session: Session, order: Order) -> dict[str, Any]:
    """The customer's tracking link, who it goes to, the ready-to-send text, and what was already sent."""
    job = _job_of(session, order)
    customer = session.get(Customer, order.customer_id)
    merchant = session.get(Merchant, order.merchant_id)
    link = tracking_url(session, job.id if job else None)
    message = TEMPLATES["tracking_link"].format(merchant=merchant.name if merchant else "RouteBridge", reference=order.external_ref, tracking_url=link).replace("  ", " ").strip() if link else ""
    sent = session.exec(select(Notification).where(Notification.order_id == order.id, Notification.template == "tracking_link").order_by(Notification.created_at.desc()).limit(10)).all()
    return {
        "link": link or None,
        "phone": customer.phone if customer else None,
        "customer_name": customer.name if customer else None,
        "message": message,
        "sent": [{"channel": n.channel, "status": n.status, "at": n.created_at} for n in sent],
        # honest about what a press of "Send" does: with the log provider the text is only recorded, not delivered
        "sms_connected": get_settings().sms_provider != "log",
    }


def media_view(url: str | None) -> str | None:
    """A picture the browser can show: a short-lived link when files live in object storage, else the file itself inlined."""
    if not url:
        return None
    if not url.startswith("media://"):
        return url if url.startswith("https://") else None
    key = url.removeprefix("media://")
    if not storage.valid_key(key):
        return None
    settings = get_settings()
    if storage.s3_enabled(settings):
        return storage.presign_for(settings, "GET", key)
    try:
        data, content_type = storage.local_storage().get(key)
    except (FileNotFoundError, ValueError):
        return None
    if len(data) > MAX_INLINE_BYTES:
        return None
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


def evidence(session: Session, order: Order, staff: bool) -> dict[str, Any]:
    """Proof of a delivery: who received it, when, whether the customer's code was checked, the photo and the signature."""
    job = _job_of(session, order)
    proof = session.exec(select(ProofOfDelivery).where(ProofOfDelivery.delivery_job_id == job.id).order_by(ProofOfDelivery.captured_at.desc())).first() if job else None
    if job is None or proof is None:
        return {"available": False, "status": job.status if job else order.status}
    payment = session.exec(select(PaymentRecord).where(PaymentRecord.order_id == order.id).order_by(PaymentRecord.recorded_at.desc())).first()
    result: dict[str, Any] = {
        "available": True,
        "status": job.status,
        "delivered_at": proof.captured_at,
        "recipient_name": proof.recipient_name,
        "code_verified": proof.otp_verified,
        "photo": media_view(proof.photo_url),
        "signature": media_view(proof.signature_url),
        "has_photo": bool(proof.photo_url),
        "cash_expected": str(payment.expected_amount) if payment else str(order.cod_amount),
        "cash_collected": str(payment.collected_amount) if payment else None,
    }
    if staff:
        assignment = session.exec(select(DriverAssignment).where(DriverAssignment.delivery_job_id == job.id).order_by(DriverAssignment.assigned_at.desc())).first()
        rider = session.get(Driver, assignment.driver_id) if assignment else None
        result["rider_name"] = rider.name if rider else None
    return result


def send_tracking_link(session: Session, order: Order, channel: str, by: str) -> Notification:
    from fastapi import HTTPException

    from routebridge.services.notifications import queue_notification

    if channel not in SHARE_CHANNELS:
        raise HTTPException(status_code=422, detail="Choose sms or whatsapp")
    job = _job_of(session, order)
    if not tracking_url(session, job.id if job else None):
        raise HTTPException(status_code=409, detail="This order has no active tracking link. Reissue the link first.")
    notification = queue_notification(session, order, "tracking_link", channel=channel, job=job)
    if notification is None:
        raise HTTPException(status_code=409, detail="The customer has opted out of this channel or has no phone number.")
    record_event(session, order.tenant_id, "tracking.link_sent", "order", order.id, {"channel": channel, "by": by})
    session.commit()
    session.refresh(notification)
    return notification
