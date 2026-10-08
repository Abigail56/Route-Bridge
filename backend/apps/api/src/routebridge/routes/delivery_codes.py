"""Delivery codes that staff pass on by hand.

When ROUTEBRIDGE_OTP_DELIVERY=dashboard (no SMS sender yet), the driver's "Text the customer a delivery code" does not send a text. The server makes
the code, keeps it for a short time, and a card appears on the dashboard. Staff give the customer the code (WhatsApp, a call or a text from their
own phone) and press "Mark as sent". Only company staff can see these; a code is erased the moment it is used, when it expires, or when it is replaced.
"""
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from routebridge.auth.authorization import TenantPrincipal, tenant_member, tenant_roles
from routebridge.db.session import get_session
from routebridge.models.core import utc_now
from routebridge.models.operations import Driver, DriverAssignment
from routebridge.models.orders import Customer, DeliveryJob, Order
from routebridge.models.plans import DeliveryOtp
from routebridge.routes.operations import require_tenant
from routebridge.services.events import record_event

ROLES = ("tenant_owner", "tenant_admin", "dispatcher", "operations_manager")
router = APIRouter(prefix="/tenants/{tenant_id}/delivery-codes", tags=["delivery-codes"], dependencies=[Depends(tenant_member)])


class DeliveryCodeRequest(SQLModel):
    id: str
    job_id: str
    order_ref: str | None
    customer_name: str | None
    customer_phone: str | None
    driver_name: str | None
    code: str
    message: str
    requested_at: str
    expires_at: str
    minutes_left: int


def _aware(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=utc_now().tzinfo)


def wipe_stale_codes(session: Session, tenant_id: UUID) -> None:
    """Erase the saved code of anything expired, so a code does not sit in the database after it can no longer be used."""
    now = utc_now()
    stale = session.exec(select(DeliveryOtp).where(DeliveryOtp.tenant_id == tenant_id, DeliveryOtp.relay_code.is_not(None))).all()
    changed = False
    for otp in stale:
        if _aware(otp.expires_at) <= now or otp.verified_at is not None:
            otp.relay_code, changed = None, True
            session.add(otp)
    if changed:
        session.commit()


@router.get("", response_model=list[DeliveryCodeRequest], dependencies=[Depends(tenant_roles(*ROLES))])
def pending_codes(tenant_id: UUID, session: Session = Depends(get_session)) -> list[DeliveryCodeRequest]:
    """Codes a rider has asked for that nobody has passed on yet, newest first."""
    require_tenant(session, tenant_id)
    wipe_stale_codes(session, tenant_id)
    now = utc_now()
    rows = session.exec(select(DeliveryOtp).where(DeliveryOtp.tenant_id == tenant_id, DeliveryOtp.relay_code.is_not(None), DeliveryOtp.relayed_at.is_(None), DeliveryOtp.verified_at.is_(None)).order_by(DeliveryOtp.created_at.desc())).all()
    result, seen = [], set()
    for otp in rows:
        if otp.delivery_job_id in seen:
            continue  # only the latest code of a job counts
        seen.add(otp.delivery_job_id)
        job = session.get(DeliveryJob, otp.delivery_job_id)
        if job is None or job.status not in ("en_route", "arrived"):
            continue
        order = session.get(Order, job.order_id)
        customer = session.get(Customer, order.customer_id) if order else None
        assignment = session.exec(select(DriverAssignment).where(DriverAssignment.delivery_job_id == job.id, DriverAssignment.status == "active")).first()
        driver = session.get(Driver, assignment.driver_id) if assignment else None
        minutes = max(1, int((_aware(otp.expires_at) - now).total_seconds() // 60))
        ref = order.external_ref if order else "your order"
        result.append(DeliveryCodeRequest(
            id=str(otp.id), job_id=str(job.id), order_ref=order.external_ref if order else None, customer_name=customer.name if customer else None, customer_phone=customer.phone if customer else None,
            driver_name=driver.name if driver else None, code=otp.relay_code or "", requested_at=_aware(otp.created_at).isoformat(), expires_at=_aware(otp.expires_at).isoformat(), minutes_left=minutes,
            message=f"RouteBridge Logistics: your delivery code for order {ref} is {otp.relay_code}. Give it to the rider only when you receive your parcel. It is valid for {minutes} minutes.",
        ))
    return result


@router.post("/{otp_id}/sent", dependencies=[Depends(tenant_roles(*ROLES))])
def mark_sent(tenant_id: UUID, otp_id: UUID, principal: TenantPrincipal = Depends(tenant_member), session: Session = Depends(get_session)) -> dict:
    """Staff say they passed the code on. The saved code is erased: the customer has it, and the rider will check it."""
    otp = session.get(DeliveryOtp, otp_id)
    if otp is None or otp.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Code request not found")
    otp.relayed_at, otp.relay_code = utc_now(), None
    if principal.user is not None:
        otp.relayed_by = principal.user.id
    session.add(otp)
    record_event(session, tenant_id, "delivery.code_relayed", "delivery_job", otp.delivery_job_id, {"job_id": str(otp.delivery_job_id)}, actor_type="user", actor_id=principal.user.id if principal.user else None)
    session.commit()
    return {"sent": True}
