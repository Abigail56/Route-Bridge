"""Automatic driver assignment.

Rules, in order:
1. The job has a map position (from the order or a later correction):
   - the nearest AVAILABLE driver within the allowed distance is chosen (PostGIS when present, plain distance otherwise);
   - if drivers have positions but all are too far away, nobody is assigned (a rider 40 km away is worse than a wait);
   - if no driver has shared a position at all, fall back to rule 2.
2. The job has no map position (common for addresses that were only typed in), or nobody can be compared:
   the available driver who has been idle the longest gets it, so work is shared fairly.
A driver who is busy or offline is never chosen. The result says which rule was used, so people are never left guessing.
"""
import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlmodel import Session, func, select

from routebridge.config.settings import get_settings
from routebridge.models.core import Tenant
from routebridge.models.operations import Driver, DriverAssignment
from routebridge.models.orders import DeliveryJob, Stop
from routebridge.models.plans import JobPlan, StopCorrection
from routebridge.services.events import record_event
from routebridge.services.geo import nearby_drivers
from routebridge.services.location import apply_corrections
from routebridge.services.notifications import notify_status_change

log = logging.getLogger("routebridge.dispatch")

Method = Literal["nearest", "next_available"]
Reason = Literal["not_waiting", "no_available_driver", "no_driver_nearby"]


@dataclass
class AutoAssignResult:
    job_id: UUID
    assigned: bool
    driver_id: UUID | None = None
    driver_name: str | None = None
    method: Method | None = None
    distance_m: int | None = None
    reason: Reason | None = None


def _job_position(session: Session, job: DeliveryJob) -> tuple[float, float] | None:
    stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id)).first()
    plan = session.exec(select(JobPlan).where(JobPlan.delivery_job_id == job.id)).first()
    corrections = session.exec(select(StopCorrection).where(StopCorrection.delivery_job_id == job.id).order_by(StopCorrection.created_at)).all()
    where = apply_corrections(stop, plan, list(corrections))
    return (where.latitude, where.longitude) if where.latitude is not None and where.longitude is not None else None


def _longest_idle(session: Session, drivers: list[Driver]) -> Driver:
    last = {driver_id: when for driver_id, when in session.exec(
        select(DriverAssignment.driver_id, func.max(DriverAssignment.assigned_at)).where(DriverAssignment.driver_id.in_([d.id for d in drivers])).group_by(DriverAssignment.driver_id)
    ).all()}
    # never assigned counts as idle the longest; ties go to the earliest name so the choice is predictable
    return sorted(drivers, key=lambda d: (last.get(d.id) is not None, last.get(d.id) or 0, d.name.lower()))[0]


def choose_driver(session: Session, job: DeliveryJob) -> tuple[Driver | None, Method | None, int | None, Reason | None]:
    available = list(session.exec(select(Driver).where(Driver.tenant_id == job.tenant_id, Driver.status == "available")).all())
    if not available:
        return None, None, None, "no_available_driver"
    position = _job_position(session, job)
    located = [d for d in available if d.latitude is not None and d.longitude is not None]
    if position is not None and located:
        radius_m = get_settings().auto_assign_radius_km * 1000
        near = nearby_drivers(session, job.tenant_id, position[0], position[1], radius_m, limit=1)
        if near:
            driver, meters = near[0]
            return driver, "nearest", round(meters), None
        return None, None, None, "no_driver_nearby"
    return _longest_idle(session, available), "next_available", None, None


def auto_assign_job(session: Session, job: DeliveryJob) -> AutoAssignResult:
    """Pick and assign a driver. The caller commits."""
    if job.status not in {"pending", "rescheduled"}:
        return AutoAssignResult(job.id, False, reason="not_waiting")
    driver, method, distance, reason = choose_driver(session, job)
    if driver is None:
        return AutoAssignResult(job.id, False, reason=reason)
    job.status = "assigned"
    driver.status = "busy"
    session.add(DriverAssignment(tenant_id=job.tenant_id, delivery_job_id=job.id, driver_id=driver.id))
    record_event(session, job.tenant_id, "delivery.assignment.created", "delivery_job", job.id,
                 {"job_id": str(job.id), "driver_id": str(driver.id), "status": job.status, "automatic": True, "method": method, "distance_m": distance})
    notify_status_change(session, job, "assigned")
    session.flush()
    return AutoAssignResult(job.id, True, driver.id, driver.name, method, distance)


def auto_assign_quietly(session: Session, tenant: Tenant | None, job: DeliveryJob) -> None:
    """Used when an order is created: a failure here must never lose the order, it just stays waiting for a manual assignment."""
    if tenant is None or not tenant.auto_assign:
        return
    try:
        auto_assign_job(session, job)
    except Exception:  # noqa: BLE001 - the order matters more than the automation
        log.exception("automatic assignment failed for job %s", job.id)
