"""Dispatch planning: zones, rate cards, delivery windows, location corrections, driver roster, batching."""
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ConfigDict
from sqlmodel import Field, Session, SQLModel, select

from routebridge.auth.authorization import TenantPrincipal, tenant_member, tenant_roles
from routebridge.db.session import get_session
from routebridge.models.catalog import RateCard, ServiceZone
from routebridge.models.core import utc_now
from routebridge.models.operations import AssignmentCreate, Driver
from routebridge.models.core import Tenant
from routebridge.models.orders import DeliveryJob, Order, Stop
from routebridge.config.settings import get_settings
from routebridge.models.plans import JobPlan, StopCorrection, TrackingToken
from routebridge.providers import get_geocoder
from routebridge.routes.operations import assign_driver, get_job, require_tenant
from routebridge.routes.orders import to_order_reads
from routebridge.services.events import record_event
from routebridge.services.dispatch import auto_assign_job
from routebridge.services.geo import nearby_drivers
from routebridge.services.location import is_valid_plus_code
from routebridge.services.notifications import dispatch_pending
from routebridge.services.routing import sequence_stops

OPS_ROLES = ("tenant_owner", "tenant_admin", "dispatcher", "operations_manager")
ADMIN_ROLES = ("tenant_owner", "tenant_admin")
router = APIRouter(prefix="/tenants/{tenant_id}", tags=["planning"], dependencies=[Depends(tenant_member)])


# ---- zones & rate cards ------------------------------------------------------------------------------------------


@router.get("/zones", response_model=list[ServiceZone])
def list_zones(tenant_id: UUID, session: Session = Depends(get_session)) -> list[ServiceZone]:
    require_tenant(session, tenant_id)
    return list(session.exec(select(ServiceZone).where(ServiceZone.tenant_id == tenant_id).order_by(ServiceZone.name)).all())


class RateCardCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    service_zone_id: UUID
    name: str = Field(min_length=2, max_length=120)
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    base_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    cod_fee: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2)


@router.get("/rate-cards", response_model=list[RateCard])
def list_rate_cards(tenant_id: UUID, session: Session = Depends(get_session)) -> list[RateCard]:
    require_tenant(session, tenant_id)
    return list(session.exec(select(RateCard).where(RateCard.tenant_id == tenant_id).order_by(RateCard.name)).all())


@router.post("/rate-cards", response_model=RateCard, status_code=201, dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def create_rate_card(tenant_id: UUID, payload: RateCardCreate, session: Session = Depends(get_session)) -> RateCard:
    require_tenant(session, tenant_id)
    zone = session.get(ServiceZone, payload.service_zone_id)
    if zone is None or zone.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Service zone not found for tenant")
    card = RateCard(tenant_id=tenant_id, **{**payload.model_dump(), "currency": payload.currency.upper()})
    session.add(card)
    session.flush()
    record_event(session, tenant_id, "rate_card.created", "rate_card", card.id, {"service_zone_id": str(zone.id), "base_amount": str(card.base_amount)})
    session.commit()
    session.refresh(card)
    return card


# ---- driver roster -----------------------------------------------------------------------------------------------


class DriverUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, min_length=5, max_length=30)
    fleet_type: Optional[Literal["owned", "contracted", "partner"]] = None
    status: Optional[Literal["available", "offline"]] = None


@router.get("/drivers/nearby", dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def drivers_near(
    tenant_id: UUID,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=10, gt=0, le=100),
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Available drivers near a point, nearest first (PostGIS ST_DWithin when available, haversine otherwise)."""
    require_tenant(session, tenant_id)
    return [{"driver_id": d.id, "name": d.name, "fleet_type": d.fleet_type, "distance_m": round(meters)} for d, meters in nearby_drivers(session, tenant_id, lat, lng, radius_km * 1000, limit)]


class AutoAssignOut(SQLModel):
    job_id: UUID
    assigned: bool
    driver_id: Optional[UUID] = None
    driver_name: Optional[str] = None
    method: Optional[str] = None
    distance_m: Optional[int] = None
    reason: Optional[str] = None


class AutoAssignAllOut(SQLModel):
    assigned: int
    waiting: int
    results: list[AutoAssignOut]


class DispatchSettings(SQLModel):
    model_config = ConfigDict(extra="forbid")
    auto_assign: bool


@router.post("/delivery-jobs/{job_id}/auto-assign", response_model=AutoAssignOut, dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def auto_assign_one(tenant_id: UUID, job_id: UUID, session: Session = Depends(get_session)) -> AutoAssignOut:
    """Give one waiting job to the nearest available driver (or the one idle longest if there is no map position)."""
    job = session.get(DeliveryJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Delivery job not found")
    result = auto_assign_job(session, job)
    session.commit()
    return AutoAssignOut(**result.__dict__)


@router.post("/dispatch/auto-assign", response_model=AutoAssignAllOut, dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def auto_assign_all(tenant_id: UUID, session: Session = Depends(get_session)) -> AutoAssignAllOut:
    """Work through every waiting job, oldest first, until drivers run out. Each driver takes one job at a time."""
    jobs = list(session.exec(select(DeliveryJob).where(DeliveryJob.tenant_id == tenant_id, DeliveryJob.status.in_(["pending", "rescheduled"])).order_by(DeliveryJob.created_at).limit(100)).all())
    results = []
    for job in jobs:
        result = auto_assign_job(session, job)
        results.append(AutoAssignOut(**result.__dict__))
        if result.reason == "no_available_driver":
            break  # nobody left: the rest simply keep waiting
    session.commit()
    return AutoAssignAllOut(assigned=sum(1 for r in results if r.assigned), waiting=len(jobs) - sum(1 for r in results if r.assigned), results=results)


@router.get("/dispatch/settings", response_model=DispatchSettings, dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def dispatch_settings(tenant_id: UUID, session: Session = Depends(get_session)) -> DispatchSettings:
    tenant = session.get(Tenant, tenant_id)
    return DispatchSettings(auto_assign=bool(tenant and tenant.auto_assign))


@router.patch("/dispatch/settings", response_model=DispatchSettings, dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def update_dispatch_settings(tenant_id: UUID, payload: DispatchSettings, session: Session = Depends(get_session)) -> DispatchSettings:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    tenant.auto_assign = payload.auto_assign
    session.add(tenant)
    record_event(session, tenant_id, "dispatch.auto_assign_changed", "tenant", tenant_id, {"auto_assign": payload.auto_assign})
    session.commit()
    return DispatchSettings(auto_assign=tenant.auto_assign)


@router.patch("/drivers/{driver_id}", response_model=Driver, dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def update_driver(tenant_id: UUID, driver_id: UUID, payload: DriverUpdate, session: Session = Depends(get_session)) -> Driver:
    driver = session.get(Driver, driver_id)
    if driver is None or driver.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Driver not found for tenant")
    changes = payload.model_dump(exclude_none=True)
    if changes.get("status") == "offline" and driver.status == "busy":
        raise HTTPException(status_code=409, detail="Driver has active jobs; reassign or complete them first")
    if changes.get("status") == "available" and driver.status == "busy":
        changes.pop("status")  # busy is derived from active assignments, not set by hand
    for key, value in changes.items():
        setattr(driver, key, value)
    driver.updated_at = utc_now()
    record_event(session, tenant_id, "driver.updated", "driver", driver.id, {"fields": sorted(changes)})
    session.commit()
    session.refresh(driver)
    return driver


# ---- delivery windows / zone (plan) ------------------------------------------------------------------------------


class PlanUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    service_zone_id: Optional[UUID] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None


@router.patch("/delivery-jobs/{job_id}/plan", dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def update_plan(tenant_id: UUID, job_id: UUID, payload: PlanUpdate, session: Session = Depends(get_session)) -> dict:
    job = get_job(session, tenant_id, job_id)
    plan = session.exec(select(JobPlan).where(JobPlan.delivery_job_id == job.id)).first() or JobPlan(tenant_id=tenant_id, delivery_job_id=job.id)
    if payload.service_zone_id is not None:
        zone = session.get(ServiceZone, payload.service_zone_id)
        if zone is None or zone.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Service zone not found for tenant")
        plan.service_zone_id = zone.id
    start = payload.window_start or plan.window_start
    end = payload.window_end or plan.window_end
    if start and end and end.replace(tzinfo=None) <= start.replace(tzinfo=None):
        raise HTTPException(status_code=422, detail="window_end must be after window_start")
    plan.window_start, plan.window_end = start, end
    session.add(plan)
    session.flush()
    record_event(session, tenant_id, "delivery.plan.updated", "delivery_job", job.id, {"service_zone_id": str(plan.service_zone_id) if plan.service_zone_id else None})
    session.commit()
    return {"delivery_job_id": str(job.id), "service_zone_id": plan.service_zone_id, "window_start": plan.window_start, "window_end": plan.window_end}


# ---- location corrections (append-only; original stop untouched) -------------------------------------------------


class CorrectionCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    address_text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    landmark: Optional[str] = Field(default=None, max_length=300)
    delivery_notes: Optional[str] = Field(default=None, max_length=1000)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    plus_code: Optional[str] = Field(default=None, max_length=20)
    recipient_available: Optional[bool] = None
    reason: Optional[str] = Field(default=None, max_length=300)


def build_correction(session: Session, tenant_id: UUID, job: DeliveryJob, source: str, payload: CorrectionCreate) -> StopCorrection:
    """Validate and store a correction. Shared by operator/driver (authenticated) and customer (tokenized) flows."""
    fields = payload.model_dump(exclude_none=True, exclude={"reason"})
    if not fields:
        raise HTTPException(status_code=422, detail="Provide at least one field to correct")
    if (payload.latitude is None) != (payload.longitude is None):
        raise HTTPException(status_code=422, detail="latitude and longitude must be given together")
    if payload.plus_code is not None and not is_valid_plus_code(payload.plus_code):
        raise HTTPException(status_code=422, detail="plus_code is not a valid Open Location Code")
    stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id)).first()
    if stop is None:
        raise HTTPException(status_code=409, detail="Job has no stop to correct")
    pins = payload.latitude is not None or bool(payload.plus_code)
    confidence = {"driver": "driver_confirmed", "customer": "customer_confirmed"}.get(source) if pins else None
    correction = StopCorrection(
        tenant_id=tenant_id,
        stop_id=stop.id,
        delivery_job_id=job.id,
        source=source,
        location_confidence=confidence,
        reason=payload.reason,
        **{k: (v.upper() if k == "plus_code" else v) for k, v in fields.items()},
    )
    session.add(correction)
    session.flush()
    record_event(session, tenant_id, "location.corrected", "delivery_job", job.id, {"source": source, "fields": sorted(fields), "correction_id": str(correction.id)})
    return correction


@router.post("/delivery-jobs/{job_id}/location-corrections", response_model=StopCorrection, status_code=201)
def correct_location(
    tenant_id: UUID,
    job_id: UUID,
    payload: CorrectionCreate,
    principal: TenantPrincipal = Depends(tenant_roles(*OPS_ROLES, "driver")),
    session: Session = Depends(get_session),
) -> StopCorrection:
    job = get_job(session, tenant_id, job_id)
    source = "driver" if principal.role == "driver" else "operator"
    correction = build_correction(session, tenant_id, job, source, payload)
    session.commit()
    session.refresh(correction)
    return correction


@router.get("/delivery-jobs/{job_id}/location-corrections", response_model=list[StopCorrection])
def list_corrections(tenant_id: UUID, job_id: UUID, session: Session = Depends(get_session)) -> list[StopCorrection]:
    job = get_job(session, tenant_id, job_id)
    return list(session.exec(select(StopCorrection).where(StopCorrection.delivery_job_id == job.id).order_by(StopCorrection.created_at)).all())


class GeocodeRequest(SQLModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=3, max_length=500)
    landmark: Optional[str] = Field(default=None, max_length=300)


@router.post("/geocode", dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def geocode(payload: GeocodeRequest) -> dict:
    """Best-effort geocode through the configured provider. Returns `result: null` when none is configured or it is
    down, so callers fall back to manual coordinates / plus codes."""
    provider = get_geocoder()
    found = provider.geocode(payload.address, payload.landmark) if provider else None
    return {"provider": "nominatim" if provider else "none", "result": None if found is None else {"latitude": found.latitude, "longitude": found.longitude, "confidence": found.confidence}}


# ---- batching & sequencing ---------------------------------------------------------------------------------------


@router.get("/dispatch/batches", dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def dispatch_batches(tenant_id: UUID, session: Session = Depends(get_session)) -> list[dict]:
    """Unassigned jobs grouped by (zone, delivery window) with a suggested stop sequence per group."""
    require_tenant(session, tenant_id)
    jobs = session.exec(select(DeliveryJob).where(DeliveryJob.tenant_id == tenant_id, DeliveryJob.status.in_(("pending", "rescheduled")))).all()
    if not jobs:
        return []
    orders = {o.id: o for o in session.exec(select(Order).where(Order.id.in_([j.order_id for j in jobs]))).all()}
    reads = {r.delivery_job_id: r for r in to_order_reads(session, list(orders.values()))}
    zones = {z.id: z.name for z in session.exec(select(ServiceZone).where(ServiceZone.tenant_id == tenant_id)).all()}
    stops = {s.delivery_job_id: s for s in session.exec(select(Stop).where(Stop.delivery_job_id.in_([j.id for j in jobs]))).all()}
    groups: dict[tuple, list[DeliveryJob]] = {}
    for job in jobs:
        read = reads.get(job.id)
        key = (read.service_zone_id if read else None, read.window_start if read else None, read.window_end if read else None)
        groups.setdefault(key, []).append(job)
    result = []
    for (zone_id, start, end), members in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        rows, points = [], []
        for job in members:
            read, stop = reads.get(job.id), stops.get(job.id)
            lat = stop.latitude if stop else None
            lng = stop.longitude if stop else None
            rows.append({"job_id": job.id, "order_id": job.order_id, "external_ref": read.external_ref if read else None, "address_text": read.address_text if read else None, "latitude": lat, "longitude": lng, "location_score": read.location_score if read else None})
            points.append((lat, lng))
        located = [i for i, p in enumerate(points) if p[0] is not None and p[1] is not None]
        order = [located[i] for i in sequence_stops([points[i] for i in located])] + [i for i in range(len(points)) if i not in located]
        result.append({"service_zone_id": zone_id, "zone_name": zones.get(zone_id), "window_start": start, "window_end": end, "jobs": rows, "suggested_sequence": [rows[i]["job_id"] for i in order]})
    return result


class BatchAssign(SQLModel):
    model_config = ConfigDict(extra="forbid")

    job_ids: list[UUID] = Field(min_length=1, max_length=100)
    driver_id: UUID


@router.post("/dispatch/batches/assign", dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def assign_batch(tenant_id: UUID, payload: BatchAssign, session: Session = Depends(get_session)) -> dict:
    """Assign one driver to several jobs; each job is reported individually so one failure does not block the rest."""
    driver = session.get(Driver, payload.driver_id)
    if driver is None or driver.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Driver not found for tenant")
    assigned, failed = [], []
    for job_id in payload.job_ids:
        try:
            assign_driver(tenant_id, job_id, AssignmentCreate(driver_id=payload.driver_id), session)
            assigned.append(job_id)
        except HTTPException as exc:
            session.rollback()
            failed.append({"job_id": job_id, "reason": exc.detail})
    return {"assigned": assigned, "failed": failed}


@router.post("/delivery-jobs/{job_id}/tracking-link/reissue", dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def reissue_tracking_link(tenant_id: UUID, job_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Revoke every existing public tracking link for the job and issue a fresh one (e.g. after a leak)."""
    job = get_job(session, tenant_id, job_id)
    for old in session.exec(select(TrackingToken).where(TrackingToken.delivery_job_id == job.id, TrackingToken.revoked.is_(False))).all():
        old.revoked = True
    token = TrackingToken(tenant_id=tenant_id, delivery_job_id=job.id, token=secrets.token_urlsafe(24), expires_at=utc_now() + timedelta(days=get_settings().tracking_token_ttl_days))
    session.add(token)
    session.flush()
    record_event(session, tenant_id, "tracking.link_reissued", "delivery_job", job.id, {})
    session.commit()
    return {"tracking_token": token.token, "expires_at": token.expires_at}


@router.get("/media/{key:path}")
def get_media(tenant_id: UUID, key: str):
    """Staff access to delivery photos/signatures: streams local files or redirects to a short-lived presigned URL."""
    from fastapi.responses import RedirectResponse, Response

    from routebridge.services import storage

    if not key.startswith(f"{tenant_id}/") or not storage.valid_key(key):
        raise HTTPException(status_code=404, detail="Not found")
    settings = get_settings()
    if storage.s3_enabled(settings):
        return RedirectResponse(storage.presign_for(settings, "GET", key), status_code=302)
    try:
        data, content_type = storage.local_storage().get(key)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    return Response(data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@router.post("/notifications/dispatch", dependencies=[Depends(tenant_roles(*OPS_ROLES))])
def dispatch_notifications(tenant_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Send this tenant's due notifications now (the background worker does this continuously)."""
    return dispatch_pending(session, tenant_id=tenant_id)
