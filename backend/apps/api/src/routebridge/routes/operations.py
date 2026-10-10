import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ConfigDict
from sqlmodel import Field, Session, SQLModel, select
from routebridge.services.billing import enforce

from routebridge.db.session import get_session
from routebridge.models.core import Tenant, utc_now
from routebridge.models.operations import (
    AssignmentCreate,
    DeliveryAttempt,
    DeliveryTransition,
    Driver,
    DriverAssignment,
    DriverCreate,
    PaymentCreate,
    PaymentRecord,
    ProofCreate,
    ProofOfDelivery,
    ReconciliationItem,
)
from routebridge.models.orders import DeliveryJob, Merchant, Order, Stop
from routebridge.config.settings import get_settings
from routebridge.models.plans import DeliveryOtp
from routebridge.services.events import record_event
from routebridge.services.notifications import notify_status_change, queue_notification
from routebridge.auth.authorization import tenant_roles

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"delivered", "cancelled", "returned"}

OPERATIONS_ROLES = ("tenant_owner", "tenant_admin", "dispatcher", "operations_manager")
router = APIRouter(prefix="/tenants/{tenant_id}", tags=["delivery-operations"], dependencies=[Depends(tenant_roles(*OPERATIONS_ROLES))])

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"assigned", "cancelled"},
    "assigned": {"accepted", "cancelled"},
    "accepted": {"en_route", "cancelled"},
    "en_route": {"arrived", "cancelled"},
    "arrived": {"delivered", "failed_attempt", "cancelled"},
    "failed_attempt": {"rescheduled", "returned", "cancelled"},
    "rescheduled": {"assigned", "cancelled"},
}


def require_tenant(session: Session, tenant_id: UUID) -> None:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")


def get_job(session: Session, tenant_id: UUID, job_id: UUID) -> DeliveryJob:
    job = session.get(DeliveryJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Delivery job not found")
    return job


def complete_assignment(session: Session, assignment: DriverAssignment, final_status: str = "completed") -> None:
    """Close an assignment; the driver only becomes available again when no other active assignment remains."""
    assignment.status = final_status
    assignment.unassigned_at = utc_now()
    session.flush()
    still_active = session.exec(
        select(DriverAssignment).where(
            DriverAssignment.driver_id == assignment.driver_id,
            DriverAssignment.status == "active",
            DriverAssignment.id != assignment.id,
        )
    ).first()
    driver = session.get(Driver, assignment.driver_id)
    if driver is not None and still_active is None and driver.status == "busy":
        driver.status = "available"


@router.post("/drivers", response_model=Driver, status_code=status.HTTP_201_CREATED)
def create_driver(
    tenant_id: UUID,
    payload: DriverCreate,
    session: Session = Depends(get_session),
) -> Driver:
    require_tenant(session, tenant_id)
    enforce(session, tenant_id, 'riders')
    driver = Driver(tenant_id=tenant_id, **payload.model_dump())
    session.add(driver)
    session.commit()
    session.refresh(driver)
    return driver


@router.get("/merchants", response_model=list[Merchant])
def list_tenant_merchants(tenant_id: UUID, session: Session = Depends(get_session)) -> list[Merchant]:
    require_tenant(session, tenant_id)
    return list(session.exec(select(Merchant).where(Merchant.tenant_id == tenant_id, Merchant.status == "active").order_by(Merchant.name)).all())


@router.get("/drivers", response_model=list[Driver])
def list_drivers(tenant_id: UUID, session: Session = Depends(get_session)) -> list[Driver]:
    require_tenant(session, tenant_id)
    return list(session.exec(select(Driver).where(Driver.tenant_id == tenant_id).order_by(Driver.name)).all())


@router.post("/delivery-jobs/{job_id}/assignments", response_model=DriverAssignment, status_code=201)
def assign_driver(
    tenant_id: UUID,
    job_id: UUID,
    payload: AssignmentCreate,
    session: Session = Depends(get_session),
) -> DriverAssignment:
    job = get_job(session, tenant_id, job_id)
    driver = session.get(Driver, payload.driver_id)
    if driver is None or driver.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Driver not found for tenant")
    if job.status not in {"pending", "rescheduled"}:
        raise HTTPException(status_code=409, detail=f"Job cannot be assigned from {job.status}")
    if driver.status == "offline":
        raise HTTPException(status_code=409, detail="Driver is offline")

    active = session.exec(
        select(DriverAssignment).where(
            DriverAssignment.tenant_id == tenant_id,
            DriverAssignment.delivery_job_id == job_id,
            DriverAssignment.status == "active",
        )
    ).first()
    if active is not None:
        complete_assignment(session, active, "replaced")

    assignment = DriverAssignment(tenant_id=tenant_id, delivery_job_id=job_id, driver_id=driver.id)
    job.status = "assigned"
    driver.status = "busy"
    session.add(assignment)
    record_event(session, tenant_id, "delivery.assignment.created", "delivery_job", job.id, {"job_id": str(job.id), "driver_id": str(driver.id), "status": job.status})
    notify_status_change(session, job, "assigned")
    session.commit()
    session.refresh(assignment)
    return assignment


@router.post("/delivery-jobs/{job_id}/transitions", response_model=DeliveryJob)
def transition_delivery_job(
    tenant_id: UUID,
    job_id: UUID,
    payload: DeliveryTransition,
    session: Session = Depends(get_session),
) -> DeliveryJob:
    job = get_job(session, tenant_id, job_id)
    target = payload.target_status
    if target not in ALLOWED_TRANSITIONS.get(job.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid transition: {job.status} -> {target}")

    if target in {"failed_attempt", "rescheduled", "returned"}:
        previous_attempts = session.exec(
            select(DeliveryAttempt).where(DeliveryAttempt.delivery_job_id == job.id)
        ).all()
        session.add(
            DeliveryAttempt(
                tenant_id=tenant_id,
                delivery_job_id=job.id,
                attempt_number=len(previous_attempts) + 1,
                status=target,
                reason_code=payload.reason_code,
                notes=payload.notes,
            )
        )

    job.status = target
    job.updated_at = utc_now()
    stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id)).first()
    if stop is not None:
        if target == "delivered":
            stop.status = "delivered"
        elif target in {"failed_attempt", "returned", "cancelled"}:
            stop.status = target

    # Sync parent Order status on terminal transitions
    order = session.get(Order, job.order_id)
    if order is not None and target in TERMINAL_STATUSES:
        order.status = target

    # Release driver back to available on terminal transitions
    if target in TERMINAL_STATUSES:
        active_assignment = session.exec(
            select(DriverAssignment).where(
                DriverAssignment.delivery_job_id == job.id,
                DriverAssignment.status == "active",
            )
        ).first()
        if active_assignment:
            complete_assignment(session, active_assignment)

    record_event(session, tenant_id, "delivery.job.updated", "delivery_job", job.id, {"job_id": str(job.id), "status": target, "reason_code": payload.reason_code})
    notify_status_change(session, job, target)
    session.commit()
    session.refresh(job)
    return job


class OtpVerify(SQLModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=4, max_length=8)


def _otp_hash(job_id: UUID, code: str) -> str:
    return hashlib.sha256(f"{job_id}:{code}".encode("utf-8")).hexdigest()


@router.post("/delivery-jobs/{job_id}/otp", status_code=201)
def issue_delivery_otp(tenant_id: UUID, job_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Generate a one-time delivery code and send it to the customer. The code is never returned by the API
    (except in development/test with the log SMS provider, so flows can be exercised without a gateway)."""
    job = get_job(session, tenant_id, job_id)
    if job.status not in {"en_route", "arrived"}:
        raise HTTPException(status_code=409, detail="OTP can only be issued while the job is en route or arrived")
    order = session.get(Order, job.order_id)
    settings = get_settings()
    code = f"{secrets.randbelow(10 ** 6):06d}"
    relay = settings.otp_delivery == "dashboard"
    if relay:  # a newer code replaces any older one that was waiting for staff
        for old in session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == job.id, DeliveryOtp.relay_code.is_not(None))).all():
            old.relay_code = None
            session.add(old)
    session.add(DeliveryOtp(tenant_id=tenant_id, delivery_job_id=job.id, code_hash=_otp_hash(job.id, code), expires_at=utc_now() + timedelta(minutes=settings.otp_ttl_minutes), relay_code=code if relay else None))
    queued = None if relay else (queue_notification(session, order, "delivery_otp", job=job, extra={"code": code}) if order else None)
    if relay:  # tells the dashboard (the live stream) that a code is waiting; the code itself is never in the event
        record_event(session, tenant_id, "delivery.code_requested", "delivery_job", job.id, {"job_id": str(job.id)})
    session.commit()
    result: dict = {"expires_in_minutes": settings.otp_ttl_minutes, "sent": queued is not None, "relay": relay}
    if settings.environment in {"development", "test"} and settings.sms_provider == "log":
        result["debug_code"] = code
    return result


@router.post("/delivery-jobs/{job_id}/otp/verify")
def verify_delivery_otp(tenant_id: UUID, job_id: UUID, payload: OtpVerify, session: Session = Depends(get_session)) -> dict:
    job = get_job(session, tenant_id, job_id)
    otp = session.exec(select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == job.id).order_by(DeliveryOtp.created_at.desc())).first()
    if otp is None:
        raise HTTPException(status_code=404, detail="No OTP has been issued for this job")
    if otp.verified_at is not None:
        return {"verified": True}
    expires = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=utc_now().tzinfo)
    if expires <= utc_now():
        raise HTTPException(status_code=410, detail="OTP has expired; issue a new one")
    if otp.attempts >= get_settings().otp_max_attempts:
        raise HTTPException(status_code=429, detail="Too many incorrect attempts; issue a new OTP")
    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _otp_hash(job.id, payload.code)):
        # staff can see wrong guesses piling up on one delivery (the guess itself is never stored)
        record_event(session, tenant_id, "delivery.code_wrong", "delivery_job", job.id, {"job_id": str(job.id), "attempts": otp.attempts})
        session.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP")
    otp.verified_at = utc_now()
    otp.relay_code = None  # used: no saved copy is kept
    record_event(session, tenant_id, "delivery.otp.verified", "delivery_job", job.id, {"job_id": str(job.id)})
    session.commit()
    return {"verified": True}


@router.post("/delivery-jobs/{job_id}/proof", response_model=ProofOfDelivery, status_code=201)
def capture_proof(
    tenant_id: UUID,
    job_id: UUID,
    payload: ProofCreate,
    session: Session = Depends(get_session),
) -> ProofOfDelivery:
    job = get_job(session, tenant_id, job_id)
    if job.status != "arrived":
        raise HTTPException(status_code=409, detail="Proof can only be captured when driver has arrived")
    for evidence in (payload.photo_url, payload.signature_url):
        if evidence and evidence.startswith("media://") and not evidence.startswith(f"media://{tenant_id}/{job.id}/"):
            raise HTTPException(status_code=422, detail="Evidence does not belong to this delivery")
    verified_otp = session.exec(
        select(DeliveryOtp).where(DeliveryOtp.delivery_job_id == job.id, DeliveryOtp.verified_at.is_not(None))
    ).first()
    if payload.otp_verified and verified_otp is None:
        raise HTTPException(status_code=409, detail="OTP has not been verified by the server; use the OTP verify endpoint first")
    if verified_otp is None and get_settings().require_delivery_code:
        raise HTTPException(status_code=409, detail="This delivery needs the customer's delivery code. Ask the customer for it and enter it, or mark the delivery as failed.")
    if verified_otp is None and not (payload.photo_url or payload.signature_url):
        raise HTTPException(status_code=422, detail="Proof requires a verified OTP, a photo or a signature")
    attempt = session.exec(
        select(DeliveryAttempt).where(DeliveryAttempt.delivery_job_id == job.id).order_by(DeliveryAttempt.attempt_number.desc())
    ).first()
    if attempt is None:
        attempt = DeliveryAttempt(tenant_id=tenant_id, delivery_job_id=job.id, status="started")
        session.add(attempt)
        session.flush()
    proof = ProofOfDelivery(tenant_id=tenant_id, delivery_job_id=job.id, attempt_id=attempt.id, **{**payload.model_dump(), "otp_verified": verified_otp is not None})
    session.add(proof)
    job.status = "delivered"
    job.updated_at = utc_now()
    stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id)).first()
    if stop is not None:
        stop.status = "delivered"

    # Sync parent Order status
    order = session.get(Order, job.order_id)
    if order is not None:
        order.status = "delivered"

    # Release driver back to available
    active_assignment = session.exec(
        select(DriverAssignment).where(
            DriverAssignment.delivery_job_id == job.id,
            DriverAssignment.status == "active",
        )
    ).first()
    if active_assignment:
        complete_assignment(session, active_assignment)

    record_event(session, tenant_id, "delivery.proof.captured", "delivery_job", job.id, {"job_id": str(job.id), "status": job.status, "proof_id": str(proof.id)})
    notify_status_change(session, job, "delivered")
    session.commit()
    session.refresh(proof)
    return proof


@router.post("/delivery-jobs/{job_id}/payments", response_model=PaymentRecord, status_code=201)
def record_payment(
    tenant_id: UUID,
    job_id: UUID,
    payload: PaymentCreate,
    session: Session = Depends(get_session),
) -> PaymentRecord:
    job = get_job(session, tenant_id, job_id)
    order = session.get(Order, job.order_id)
    if order is None or order.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Order not found for delivery job")

    existing = session.exec(
        select(PaymentRecord).where(PaymentRecord.delivery_job_id == job.id)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Payment already recorded for delivery job")

    expected = order.cod_amount
    variance = payload.collected_amount - expected
    reconciliation_status = "matched" if variance == Decimal("0.00") else "exception"
    payment = PaymentRecord(
        tenant_id=tenant_id,
        order_id=order.id,
        delivery_job_id=job.id,
        method=payload.method,
        expected_amount=expected,
        collected_amount=payload.collected_amount,
        currency=order.currency,
        provider_reference=payload.provider_reference,
        reconciliation_status=reconciliation_status,
    )
    session.add(payment)
    session.flush()
    if reconciliation_status == "exception":
        session.add(
            ReconciliationItem(
                tenant_id=tenant_id,
                payment_id=payment.id,
                status="open",
                variance_amount=variance,
            )
        )
    record_event(session, tenant_id, "payment.recorded", "delivery_job", job.id, {"job_id": str(job.id), "payment_id": str(payment.id), "reconciliation_status": reconciliation_status, "variance": str(variance)})
    session.commit()
    session.refresh(payment)
    return payment
