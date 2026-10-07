"""Where are my drivers? Live positions for dispatchers, and a careful, small slice of it for the customer waiting at the door.

The driver app already reports its GPS position; the server keeps the latest one on the driver. This module only READS it.
Customers are shown a rider's position only while their own parcel is on the way (en route or arrived) and only if the position
is fresh, never before assignment and never after delivery.
"""
import math
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.core import utc_now
from routebridge.models.operations import Driver, DriverAssignment
from routebridge.models.orders import DeliveryJob, Order, Stop
from routebridge.models.plans import JobPlan, StopCorrection
from routebridge.services.location import apply_corrections
from routebridge.services.route_eta import provider_enabled, travel_minutes
from routebridge.services.routing import haversine_km

ACTIVE_JOB_STATUSES = ("assigned", "accepted", "en_route", "arrived")
STALE_AFTER_SECONDS = 10 * 60       # a position older than this is shown as "last seen", not as live
CUSTOMER_FRESH_SECONDS = 15 * 60    # the customer only sees a rider whose position is newer than this


def seconds_since(moment: datetime | None) -> int | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, int((utc_now() - moment).total_seconds()))


def eta_minutes(distance_km: float) -> int:
    """A deliberately plain estimate: straight-line distance at an average city speed (ROUTEBRIDGE_ETA_SPEED_KMH). Shown as 'about'."""
    speed = max(get_settings().eta_speed_kmh, 5.0)
    return max(1, math.ceil(distance_km * 1.3 / speed * 60))  # x1.3: roads are longer than the straight line


def best_eta(origin: tuple[float, float], drop: tuple[float, float]) -> int:
    """Minutes by road (with traffic when the provider has it); the straight-line estimate when there is no provider or it cannot answer."""
    return travel_minutes(origin, drop) or eta_minutes(haversine_km(origin, drop))


def dropoff_position(session: Session, job: DeliveryJob) -> tuple[float, float] | None:
    stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id)).first()
    plan = session.exec(select(JobPlan).where(JobPlan.delivery_job_id == job.id)).first()
    corrections = session.exec(select(StopCorrection).where(StopCorrection.delivery_job_id == job.id).order_by(StopCorrection.created_at)).all()
    where = apply_corrections(stop, plan, list(corrections))
    return (where.latitude, where.longitude) if where.latitude is not None and where.longitude is not None else None


def live_drivers(session: Session, tenant_id: UUID) -> dict:
    """Everything the dispatcher's live map needs in one call."""
    drivers = list(session.exec(select(Driver).where(Driver.tenant_id == tenant_id).order_by(Driver.name)).all())
    active = {
        a.driver_id: a for a in session.exec(select(DriverAssignment).where(DriverAssignment.tenant_id == tenant_id, DriverAssignment.status == "active")).all()
    }
    jobs = {j.id: j for j in session.exec(select(DeliveryJob).where(DeliveryJob.id.in_([a.delivery_job_id for a in active.values()]))).all()} if active else {}
    orders = {o.id: o for o in session.exec(select(Order).where(Order.id.in_([j.order_id for j in jobs.values()]))).all()} if jobs else {}

    road_lookups_left = 25  # keeps one refresh of the map from making dozens of paid routing calls
    rows = []
    for driver in drivers:
        assignment = active.get(driver.id)
        job = jobs.get(assignment.delivery_job_id) if assignment else None
        job_info = None
        if job is not None and job.status in ACTIVE_JOB_STATUSES:
            drop = dropoff_position(session, job)
            eta = None
            if drop and driver.latitude is not None and driver.longitude is not None and job.status != "arrived":
                here = (driver.latitude, driver.longitude)
                if road_lookups_left > 0 and provider_enabled():
                    road_lookups_left -= 1
                    eta = best_eta(here, drop)
                else:
                    eta = eta_minutes(haversine_km(here, drop))
            stop = session.exec(select(Stop).where(Stop.delivery_job_id == job.id)).first()
            order = orders.get(job.order_id)
            job_info = {
                "job_id": str(job.id), "order_ref": order.external_ref if order else None, "status": job.status,
                "address_text": stop.address_text if stop else None,
                "dropoff_latitude": drop[0] if drop else None, "dropoff_longitude": drop[1] if drop else None, "eta_minutes": eta,
            }
        age = seconds_since(driver.last_location_at)
        rows.append({
            "driver_id": str(driver.id), "name": driver.name, "phone": driver.phone, "fleet_type": driver.fleet_type, "status": driver.status,
            "latitude": driver.latitude, "longitude": driver.longitude, "last_seen_seconds": age,
            "stale": age is None or age > STALE_AFTER_SECONDS, "job": job_info,
        })

    waiting = []
    for job in session.exec(select(DeliveryJob).where(DeliveryJob.tenant_id == tenant_id, DeliveryJob.status.in_(["pending", "rescheduled"])).order_by(DeliveryJob.created_at).limit(100)).all():
        drop = dropoff_position(session, job)
        if drop:
            order = session.get(Order, job.order_id)
            waiting.append({"job_id": str(job.id), "order_ref": order.external_ref if order else None, "latitude": drop[0], "longitude": drop[1]})
    return {"drivers": rows, "waiting": waiting}


def rider_for_customer(session: Session, job: DeliveryJob, driver: Driver | None) -> dict | None:
    """What the customer may see: only while the parcel is on its way, only a fresh position, only the rider's first name elsewhere."""
    if driver is None or job.status not in ("en_route", "arrived"):
        return None
    age = seconds_since(driver.last_location_at)
    if driver.latitude is None or driver.longitude is None or age is None or age > CUSTOMER_FRESH_SECONDS:
        return None
    drop = dropoff_position(session, job)
    eta = best_eta((driver.latitude, driver.longitude), drop) if drop and job.status == "en_route" else None
    return {
        "latitude": driver.latitude, "longitude": driver.longitude, "updated_seconds_ago": age, "eta_minutes": eta,
        "dropoff": {"latitude": drop[0], "longitude": drop[1]} if drop else None,
        "photo": driver.photo,
    }
