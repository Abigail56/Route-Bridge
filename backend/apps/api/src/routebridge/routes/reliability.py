from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from routebridge.db.session import get_session
from routebridge.models.core import Tenant, utc_now
from routebridge.models.operations import DeliveryAttempt, Driver, DriverAssignment
from routebridge.models.orders import DeliveryJob, Order, Stop
from routebridge.models.reliability import (
    MobileSyncEvent,
    MobileSyncRequest,
    MobileSyncResponse,
)
from routebridge.routes.operations import ALLOWED_TRANSITIONS, TERMINAL_STATUSES, complete_assignment
from routebridge.auth.authorization import tenant_member
from routebridge.services.events import record_event
from routebridge.services.notifications import notify_status_change
from routebridge.integrations.rate_limit import limiter
from routebridge.models.reliability import MobileSyncEventInput
from routebridge.models.operations import PaymentCreate, ProofCreate
from pydantic import ValidationError

router = APIRouter(prefix="/tenants/{tenant_id}/mobile-sync", tags=["mobile-sync"], dependencies=[Depends(tenant_member)])


def require_tenant(session: Session, tenant_id: UUID) -> None:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")


def apply_delivery_transition(
    session: Session,
    tenant_id: UUID,
    job: DeliveryJob,
    target: str,
    payload: dict,
) -> bool:
    if target not in ALLOWED_TRANSITIONS.get(job.status, set()):
        return False
    if target in {"failed_attempt", "rescheduled", "returned"}:
        previous = session.exec(
            select(DeliveryAttempt).where(DeliveryAttempt.delivery_job_id == job.id)
        ).all()
        session.add(
            DeliveryAttempt(
                tenant_id=tenant_id,
                delivery_job_id=job.id,
                attempt_number=len(previous) + 1,
                status=target,
                reason_code=payload.get("reason_code"),
                notes=payload.get("notes"),
            )
        )
    job.status = target
    job.updated_at = utc_now()
    stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id)).first()
    if stop is not None and target in {"delivered", "failed_attempt", "returned", "cancelled"}:
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

    notify_status_change(session, job, target)
    return True


SECRET_PAYLOAD_KEYS = {"otp_code", "code"}  # never persisted in the sync log, audit trail or event stream


def _driver_has_job(session: Session, driver: Driver, job: DeliveryJob) -> bool:
    return session.exec(
        select(DriverAssignment).where(
            DriverAssignment.delivery_job_id == job.id,
            DriverAssignment.driver_id == driver.id,
            DriverAssignment.status.in_(("active", "completed")),  # completed: COD/proof events often arrive after delivery
        )
    ).first() is not None


def _apply_event(session: Session, tenant_id: UUID, incoming: MobileSyncEventInput, driver: Driver | None) -> bool:
    """Apply one device event. Returns False (or raises HTTPException) when it must be rejected."""
    # imported here: operations/planning import this module's siblings at import time
    from routebridge.routes.operations import OtpVerify, capture_proof, record_payment, verify_delivery_otp
    from routebridge.routes.planning import CorrectionCreate, build_correction

    kind = incoming.event_type
    payload = incoming.payload

    if kind == "driver.location":
        if driver is None:
            return True  # telemetry from staff devices is stored but has no driver to update
        lat, lng = payload.get("latitude"), payload.get("longitude")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return False
        driver.latitude, driver.longitude, driver.last_location_at = float(lat), float(lng), incoming.occurred_at
        return True

    if kind not in {"delivery.transition", "delivery.proof", "delivery.payment", "location.correction"}:
        return True  # unknown event types are kept for later processing (forward compatible)

    job = session.get(DeliveryJob, incoming.aggregate_id)
    if job is None or job.tenant_id != tenant_id:
        return False
    if driver is not None and not _driver_has_job(session, driver, job):
        return False

    if kind == "delivery.transition":
        target = payload.get("target_status")
        return isinstance(target, str) and apply_delivery_transition(session, tenant_id, job, target, payload)
    if kind == "delivery.proof":
        code = payload.get("otp_code")
        if isinstance(code, str) and code:
            verify_delivery_otp(tenant_id, job.id, OtpVerify(code=code), session)
        capture_proof(tenant_id, job.id, ProofCreate(otp_verified=bool(code), photo_url=payload.get("photo_url"), signature_url=payload.get("signature_url"), recipient_name=payload.get("recipient_name")), session)
        return True
    if kind == "delivery.payment":
        record_payment(tenant_id, job.id, PaymentCreate(method=str(payload.get("method", "cod")), collected_amount=payload.get("collected_amount"), provider_reference=payload.get("provider_reference")), session)
        return True
    # location.correction
    build_correction(session, tenant_id, job, "driver" if driver is not None else "operator", CorrectionCreate(**{k: v for k, v in payload.items() if k in CorrectionCreate.model_fields}))
    return True


def process_events(session: Session, tenant_id: UUID, events: list[MobileSyncEventInput], driver: Driver | None = None) -> MobileSyncResponse:
    """Idempotent, per-event atomic processing: a bad event is rejected without losing the others."""
    accepted: list[UUID] = []
    duplicates: list[UUID] = []
    rejected: list[UUID] = []
    for incoming in events:
        if session.exec(select(MobileSyncEvent).where(MobileSyncEvent.tenant_id == tenant_id, MobileSyncEvent.event_id == incoming.event_id)).first() is not None:
            duplicates.append(incoming.event_id)
            continue
        safe_payload = {k: v for k, v in incoming.payload.items() if k not in SECRET_PAYLOAD_KEYS}
        try:
            if not _apply_event(session, tenant_id, incoming, driver):
                session.rollback()
                rejected.append(incoming.event_id)
                continue
            session.add(
                MobileSyncEvent(
                    tenant_id=tenant_id,
                    event_id=incoming.event_id,
                    device_id=incoming.device_id,
                    event_type=incoming.event_type,
                    aggregate_type=incoming.aggregate_type,
                    aggregate_id=incoming.aggregate_id,
                    payload=safe_payload,
                    occurred_at=incoming.occurred_at,
                )
            )
            record_event(session, tenant_id, incoming.event_type, incoming.aggregate_type, incoming.aggregate_id, safe_payload, actor_type="driver_device", actor_id=driver.id if driver else None)
            session.commit()
            accepted.append(incoming.event_id)
        except (HTTPException, ValidationError, ValueError, TypeError):
            session.rollback()
            rejected.append(incoming.event_id)
    return MobileSyncResponse(accepted_event_ids=accepted, duplicate_event_ids=duplicates, rejected_event_ids=rejected)


@router.post("", response_model=MobileSyncResponse)
def sync_mobile_events(
    tenant_id: UUID,
    request: MobileSyncRequest,
    session: Session = Depends(get_session),
) -> MobileSyncResponse:
    require_tenant(session, tenant_id)
    # Rate limit: max 60 sync requests per minute per tenant
    retry_after = limiter.check(f"mobile-sync:{tenant_id}", limit=60, window_seconds=60)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=f"Too many sync requests. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    return process_events(session, tenant_id, request.events)
