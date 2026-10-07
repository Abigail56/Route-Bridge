"""Public, tokenized customer tracking. No login: access is by an unguessable, expiring, revocable token."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ConfigDict
from sqlmodel import Field, Session, SQLModel, select

from routebridge.db.session import get_session
from routebridge.integrations.rate_limit import limiter
from routebridge.models.core import utc_now
from routebridge.models.operations import Driver, DriverAssignment
from routebridge.models.orders import Customer, DeliveryJob, Merchant, Order
from routebridge.models.plans import ConsentRecord, TrackingToken
from routebridge.models.reliability import AuditEvent
from routebridge.routes.orders import to_order_reads
from routebridge.routes.planning import CorrectionCreate, build_correction
from routebridge.services.flags import enabled
from routebridge.services.tracking import rider_for_customer

router = APIRouter(prefix="/public/tracking", tags=["public-tracking"])

TERMINAL = {"delivered", "cancelled", "returned"}
STATUS_LABELS = {
    "pending": "Order received",
    "assigned": "Driver assigned",
    "accepted": "Driver accepted",
    "en_route": "On the way",
    "arrived": "Driver has arrived",
    "delivered": "Delivered",
    "failed_attempt": "Delivery attempt failed",
    "rescheduled": "Rescheduled",
    "returned": "Returned to sender",
    "cancelled": "Cancelled",
}


def _throttle(request: Request, token: str) -> None:
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()) or (request.client.host if request.client else "unknown")
    retry_after = limiter.check(f"track:{ip}", limit=60, window_seconds=60)
    if retry_after:
        raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": str(retry_after)})


def _resolve(session: Session, token: str) -> tuple[TrackingToken, DeliveryJob]:
    # One generic error for unknown / revoked / expired tokens so valid tokens cannot be probed.
    not_found = HTTPException(status_code=404, detail="Tracking link not found or expired")
    record = session.exec(select(TrackingToken).where(TrackingToken.token == token)).first()
    if record is None or record.revoked:
        raise not_found
    expires = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=utc_now().tzinfo)
    if expires <= utc_now():
        raise not_found
    job = session.get(DeliveryJob, record.delivery_job_id)
    if job is None:
        raise not_found
    return record, job


@router.get("/{token}")
def tracking_status(token: str, request: Request, session: Session = Depends(get_session)) -> dict:
    _throttle(request, token)
    _, job = _resolve(session, token)
    order = session.get(Order, job.order_id)
    merchant = session.get(Merchant, order.merchant_id) if order else None
    read = to_order_reads(session, [order])[0] if order else None
    assignment = session.exec(select(DriverAssignment).where(DriverAssignment.delivery_job_id == job.id, DriverAssignment.status == "active")).first()
    driver = session.get(Driver, assignment.driver_id) if assignment else None
    events = session.exec(
        select(AuditEvent)
        .where(AuditEvent.aggregate_id == job.id, AuditEvent.aggregate_type == "delivery_job")
        .order_by(AuditEvent.occurred_at)
    ).all()
    history = [
        {"status": e.payload.get("status"), "label": STATUS_LABELS.get(e.payload.get("status"), e.payload.get("status")), "at": e.occurred_at}
        for e in events
        if e.event_type in {"delivery.job.updated", "delivery.assignment.created", "delivery.proof.captured"} and e.payload.get("status")
    ]
    # Only what the customer needs: no phone numbers, internal ids, amounts other than COD due, or driver contact.
    return {
        "reference": order.external_ref if order else None,
        "merchant": merchant.name if merchant else None,
        "status": job.status,
        "status_label": STATUS_LABELS.get(job.status, job.status),
        "is_final": job.status in TERMINAL,
        "driver_first_name": driver.name.split(" ")[0] if driver else None,
        "rider": rider_for_customer(session, job, driver),
        "delivery_window": {"start": read.window_start, "end": read.window_end} if read and (read.window_start or read.window_end) else None,
        "location": {"landmark": read.landmark, "plus_code": read.plus_code, "confirmed": read.location_confidence in {"customer_confirmed", "driver_confirmed"}} if read else None,
        "cod_amount_due": str(order.cod_amount) if order and order.cod_amount else None,
        "history": history,
    }


class CustomerCorrection(SQLModel):
    model_config = ConfigDict(extra="forbid")

    landmark: Optional[str] = Field(default=None, max_length=300)
    delivery_notes: Optional[str] = Field(default=None, max_length=1000)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    plus_code: Optional[str] = Field(default=None, max_length=20)
    recipient_available: Optional[bool] = None


@router.post("/{token}/correction", status_code=201)
def customer_correction(token: str, payload: CustomerCorrection, request: Request, session: Session = Depends(get_session)) -> dict:
    """Customers can confirm/correct where and when they can receive the order. The original address is preserved."""
    _throttle(request, token)
    if not enabled("customer_corrections"):
        raise HTTPException(status_code=403, detail="Location updates are currently unavailable")
    record, job = _resolve(session, token)
    if job.status in TERMINAL:
        raise HTTPException(status_code=409, detail="This delivery is already complete")
    correction = build_correction(session, record.tenant_id, job, "customer", CorrectionCreate(**payload.model_dump(), reason="customer"))
    session.commit()
    return {"id": correction.id, "accepted": True}


class ConsentUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["sms", "whatsapp"]
    granted: bool


@router.post("/{token}/consent", status_code=201)
def update_consent(token: str, payload: ConsentUpdate, request: Request, session: Session = Depends(get_session)) -> dict:
    _throttle(request, token)
    record, job = _resolve(session, token)
    order = session.get(Order, job.order_id)
    customer = session.get(Customer, order.customer_id) if order else None
    if customer is None:
        raise HTTPException(status_code=404, detail="Tracking link not found or expired")
    session.add(ConsentRecord(tenant_id=record.tenant_id, customer_id=customer.id, purpose=payload.purpose, granted=payload.granted))
    session.commit()
    return {"purpose": payload.purpose, "granted": payload.granted}
