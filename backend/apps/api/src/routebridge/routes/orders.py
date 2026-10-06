import hashlib
import json
import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlmodel import Session, select

from routebridge.db.session import get_session
from routebridge.config.settings import get_settings
from routebridge.models.catalog import ServiceZone
from routebridge.models.core import Tenant, utc_now
from routebridge.models.plans import JobPlan, StopCorrection, TrackingToken
from routebridge.services.notifications import queue_notification
from routebridge.services.location import apply_corrections, decode_plus_code, is_valid_plus_code, location_score
from routebridge.models.orders import (
    Customer,
    DeliveryJob,
    Merchant,
    Order,
    OrderCreate,
    OrderRead,
    Stop,
)
from routebridge.models.operations import Driver, DriverAssignment
from routebridge.models.reliability import IdempotencyRecord
from routebridge.auth.authorization import tenant_member, tenant_roles
from routebridge.services.events import record_event

ORDERS_WRITE_ROLES = ("tenant_owner", "tenant_admin", "dispatcher", "operations_manager")
router = APIRouter(prefix="/tenants/{tenant_id}/orders", tags=["orders"], dependencies=[Depends(tenant_member)])


def get_tenant_or_404(session: Session, tenant_id: UUID) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


def to_order_reads(session: Session, orders: list[Order]) -> list[OrderRead]:
    """Build enriched read models for orders using batched lookups (no per-order queries)."""
    if not orders:
        return []
    order_ids = [o.id for o in orders]
    jobs = {j.order_id: j for j in session.exec(select(DeliveryJob).where(DeliveryJob.order_id.in_(order_ids))).all()}
    job_ids = [j.id for j in jobs.values()]
    stops: dict[UUID, Stop] = {}
    assignments: dict[UUID, DriverAssignment] = {}
    if job_ids:
        for stop in session.exec(select(Stop).where(Stop.delivery_job_id.in_(job_ids)).order_by(Stop.sequence)).all():
            stops.setdefault(stop.delivery_job_id, stop)
        for assignment in session.exec(
            select(DriverAssignment)
            .where(DriverAssignment.delivery_job_id.in_(job_ids), DriverAssignment.unassigned_at.is_(None))
            .order_by(DriverAssignment.assigned_at)
        ).all():
            assignments[assignment.delivery_job_id] = assignment  # latest active assignment wins
    plans: dict[UUID, JobPlan] = {}
    corrections: dict[UUID, list[StopCorrection]] = {}
    tokens: dict[UUID, str] = {}
    if job_ids:
        plans = {p.delivery_job_id: p for p in session.exec(select(JobPlan).where(JobPlan.delivery_job_id.in_(job_ids))).all()}
        for corr in session.exec(select(StopCorrection).where(StopCorrection.delivery_job_id.in_(job_ids)).order_by(StopCorrection.created_at)).all():
            corrections.setdefault(corr.delivery_job_id, []).append(corr)
        now = utc_now()
        for tok in session.exec(select(TrackingToken).where(TrackingToken.delivery_job_id.in_(job_ids), TrackingToken.revoked.is_(False)).order_by(TrackingToken.created_at)).all():
            expires = tok.expires_at if tok.expires_at.tzinfo else tok.expires_at.replace(tzinfo=now.tzinfo)
            if expires > now:
                tokens[tok.delivery_job_id] = tok.token
    customers = {c.id: c for c in session.exec(select(Customer).where(Customer.id.in_({o.customer_id for o in orders}))).all()}
    merchants = {m.id: m for m in session.exec(select(Merchant).where(Merchant.id.in_({o.merchant_id for o in orders}))).all()}
    drivers = {}
    if assignments:
        drivers = {d.id: d for d in session.exec(select(Driver).where(Driver.id.in_({a.driver_id for a in assignments.values()}))).all()}
    reads: list[OrderRead] = []
    for order in orders:
        job = jobs.get(order.id)
        stop = stops.get(job.id) if job else None
        assignment = assignments.get(job.id) if job else None
        driver = drivers.get(assignment.driver_id) if assignment else None
        plan = plans.get(job.id) if job else None
        loc = apply_corrections(stop, plan, corrections.get(job.id, [])) if job else None
        customer = customers.get(order.customer_id)
        merchant = merchants.get(order.merchant_id)
        reads.append(
            OrderRead(
                id=order.id,
                tenant_id=order.tenant_id,
                merchant_id=order.merchant_id,
                customer_id=order.customer_id,
                external_ref=order.external_ref,
                status=order.status,
                currency=order.currency,
                total_amount=order.total_amount,
                cod_amount=order.cod_amount,
                delivery_job_id=job.id if job else None,
                stop_id=stop.id if stop else None,
                stop_status=stop.status if stop else None,
                created_at=order.created_at,
                customer_name=customer.name if customer else None,
                merchant_name=merchant.name if merchant else None,
                address_text=loc.address_text if loc else None,
                landmark=loc.landmark if loc else None,
                location_confidence=loc.confidence if loc else None,
                location_corrected=loc.corrected if loc else False,
                latitude=loc.latitude if loc else None,
                longitude=loc.longitude if loc else None,
                location_score=location_score(loc.confidence, loc.latitude is not None and loc.longitude is not None, bool(loc.plus_code), bool(loc.landmark)) if loc else None,
                plus_code=loc.plus_code if loc else None,
                recipient_available=loc.recipient_available if loc else None,
                service_zone_id=plan.service_zone_id if plan else None,
                window_start=plan.window_start if plan else None,
                window_end=plan.window_end if plan else None,
                tracking_token=tokens.get(job.id) if job else None,
                job_status=job.status if job else None,
                driver_id=driver.id if driver else None,
                driver_name=driver.name if driver else None,
            )
        )
    return reads


def to_order_read(session: Session, order: Order) -> OrderRead:
    return to_order_reads(session, [order])[0]


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(tenant_roles(*ORDERS_WRITE_ROLES))])
def create_order(
    tenant_id: UUID,
    payload: OrderCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> OrderRead:
    get_tenant_or_404(session, tenant_id)

    request_hash = hashlib.sha256(
        json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    if idempotency_key:
        previous = session.exec(
            select(IdempotencyRecord).where(
                IdempotencyRecord.tenant_id == tenant_id,
                IdempotencyRecord.key == idempotency_key,
            )
        ).first()
        if previous is not None:
            if previous.request_hash != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key was reused with a different request")
            return OrderRead.model_validate_json(previous.response_json)

    if payload.plus_code is not None and not is_valid_plus_code(payload.plus_code):
        raise HTTPException(status_code=422, detail="plus_code is not a valid Open Location Code")
    if payload.window_start and payload.window_end and payload.window_end <= payload.window_start:
        raise HTTPException(status_code=422, detail="window_end must be after window_start")
    if payload.service_zone_id is not None:
        zone = session.get(ServiceZone, payload.service_zone_id)
        if zone is None or zone.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Service zone not found for tenant")

    merchant = session.get(Merchant, payload.merchant_id)
    if merchant is None or merchant.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Merchant not found for tenant")

    duplicate = session.exec(
        select(Order).where(
            Order.tenant_id == tenant_id,
            Order.external_ref == payload.external_ref,
        )
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Order external_ref already exists")

    customer = session.exec(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.phone == payload.customer_phone,
        )
    ).first()
    if customer is None:
        customer = Customer(
            tenant_id=tenant_id,
            name=payload.customer_name,
            phone=payload.customer_phone,
        )
        session.add(customer)
        session.flush()

    order = Order(
        tenant_id=tenant_id,
        merchant_id=payload.merchant_id,
        customer_id=customer.id,
        external_ref=payload.external_ref,
        currency=payload.currency.upper(),
        total_amount=payload.total_amount,
        cod_amount=payload.cod_amount,
    )
    session.add(order)
    session.flush()

    job = DeliveryJob(tenant_id=tenant_id, order_id=order.id)
    session.add(job)
    session.flush()

    stop = Stop(
        tenant_id=tenant_id,
        delivery_job_id=job.id,
        address_text=payload.address_text,
        landmark=payload.landmark,
        delivery_notes=payload.delivery_notes,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_confidence=payload.location_confidence,
        recipient_available=payload.recipient_available,
    )
    # A plus code that decodes to a point supplies coordinates when no map pin was given.
    pin = decode_plus_code(payload.plus_code) if payload.plus_code else None
    if pin and stop.latitude is None and stop.longitude is None:
        stop.latitude, stop.longitude = pin
    session.add(stop)
    session.add(
        JobPlan(
            tenant_id=tenant_id,
            delivery_job_id=job.id,
            service_zone_id=payload.service_zone_id,
            window_start=payload.window_start,
            window_end=payload.window_end,
            plus_code=payload.plus_code.upper() if payload.plus_code else None,
        )
    )
    session.add(
        TrackingToken(
            tenant_id=tenant_id,
            delivery_job_id=job.id,
            token=secrets.token_urlsafe(24),
            expires_at=utc_now() + timedelta(days=get_settings().tracking_token_ttl_days),
        )
    )
    session.flush()
    queue_notification(session, order, "order_confirmed", job=job)
    result = to_order_read(session, order)
    if idempotency_key:
        session.add(
            IdempotencyRecord(
                tenant_id=tenant_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_json=result.model_dump_json(),
                response_status=status.HTTP_201_CREATED,
            )
        )
    record_event(session, tenant_id, "order.created", "order", order.id, {"external_ref": order.external_ref, "delivery_job_id": str(job.id)})
    session.commit()
    return result


@router.get("", response_model=list[OrderRead])
def list_orders(
    tenant_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[OrderRead]:
    get_tenant_or_404(session, tenant_id)
    orders = session.exec(
        select(Order)
        .where(Order.tenant_id == tenant_id)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return to_order_reads(session, list(orders))
