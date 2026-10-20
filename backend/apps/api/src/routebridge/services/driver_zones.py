"""Which zones a Dispatcher (rider) works in, and whether they may take a job.

The rule, used by automatic and manual assignment alike:
- a job with no zone can go to anyone;
- a Dispatcher with no zones set can take a job in any zone (riders added before zones existed keep working);
- otherwise the job's zone must be one of the Dispatcher's zones.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from routebridge.models.catalog import ServiceZone
from routebridge.models.operations import Driver, DriverZone
from routebridge.models.orders import DeliveryJob
from routebridge.models.plans import JobPlan

MAX_ZONES = 10


def clean_zone_names(names: list[str]) -> list[str]:
    """What a rider typed, tidied: spaces squeezed, duplicates (any case) dropped, order kept."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in names:
        name = " ".join(raw.replace(",", " ").split())
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def split_zone_names(stored: str | None) -> list[str]:
    return clean_zone_names(stored.split(",")) if stored else []


def match_zones(session: Session, tenant_id: UUID, names: list[str]) -> tuple[list[UUID], list[str]]:
    """The company's active zones whose name or code matches what the rider typed (ignoring case and spaces), and the names that matched nothing."""
    zones = session.exec(select(ServiceZone).where(ServiceZone.tenant_id == tenant_id, ServiceZone.status == "active")).all()
    index: dict[str, UUID] = {}
    for zone in zones:
        index.setdefault(" ".join(zone.name.split()).lower(), zone.id)
        index.setdefault(zone.code.strip().lower(), zone.id)
    matched: list[UUID] = []
    unmatched: list[str] = []
    for name in names:
        zone_id = index.get(name.lower())
        if zone_id is None:
            unmatched.append(name)
        elif zone_id not in matched:
            matched.append(zone_id)
    return matched, unmatched


def zones_of(session: Session, driver_id: UUID) -> list[UUID]:
    return list(session.exec(select(DriverZone.service_zone_id).where(DriverZone.driver_id == driver_id)).all())


def zones_by_driver(session: Session, tenant_id: UUID) -> dict[UUID, list[UUID]]:
    out: dict[UUID, list[UUID]] = {}
    for row in session.exec(select(DriverZone).where(DriverZone.tenant_id == tenant_id)).all():
        out.setdefault(row.driver_id, []).append(row.service_zone_id)
    return out


def set_zones(session: Session, tenant_id: UUID, driver_id: UUID, zone_ids: list[UUID]) -> list[UUID]:
    """Replace a Dispatcher's zones. Every zone must be an active zone of this company."""
    wanted = list(dict.fromkeys(zone_ids))
    if len(wanted) > MAX_ZONES:
        raise HTTPException(status_code=422, detail=f"A Dispatcher can work in at most {MAX_ZONES} zones.")
    if wanted:
        found = {z.id for z in session.exec(select(ServiceZone).where(ServiceZone.id.in_(wanted), ServiceZone.tenant_id == tenant_id, ServiceZone.status == "active")).all()}
        if len(found) != len(wanted):
            raise HTTPException(status_code=404, detail="Zone not found for this company")
    for row in session.exec(select(DriverZone).where(DriverZone.driver_id == driver_id)).all():
        if row.service_zone_id not in wanted:
            session.delete(row)
    have = set(zones_of(session, driver_id))
    for zone_id in wanted:
        if zone_id not in have:
            session.add(DriverZone(tenant_id=tenant_id, driver_id=driver_id, service_zone_id=zone_id))
    session.flush()
    return wanted


def job_zone(session: Session, job: DeliveryJob) -> UUID | None:
    plan = session.exec(select(JobPlan).where(JobPlan.delivery_job_id == job.id)).first()
    return plan.service_zone_id if plan else None


def covers(driver_zones: list[UUID], zone_id: UUID | None) -> bool:
    return zone_id is None or not driver_zones or zone_id in driver_zones


def check_covers(session: Session, driver: Driver, job: DeliveryJob) -> None:
    """Refuse (409) a manual assignment outside the rider's zones, saying which zones they do cover."""
    zone_id = job_zone(session, job)
    mine = zones_of(session, driver.id)
    if covers(mine, zone_id):
        return
    names = {z.id: z.name for z in session.exec(select(ServiceZone).where(ServiceZone.id.in_([zone_id, *mine]))).all()}
    theirs = ", ".join(sorted(names.get(z, "?") for z in mine))
    raise HTTPException(status_code=409, detail=f"{driver.name} does not work in {names.get(zone_id, 'this zone')} (their zones: {theirs}). Choose a Dispatcher who covers it, or change their zones on the Dispatchers screen.")
