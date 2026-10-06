"""Platform console: what RouteBridge staff use to run the whole system (companies, people, admins, health, audit).

Everything here requires a platform administrator. It deliberately exposes counts and ownership, not a company's orders or
customers, so platform staff do not see customer data by default.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ConfigDict
from redis import Redis
from sqlalchemy import func, text
from sqlmodel import Field, Session, SQLModel, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.integrations.clerk import ClerkUser
from routebridge.models.access import ROLES, TenantMembership, User
from routebridge.models.core import Tenant, utc_now
from routebridge.models.events import OutboxEvent
from routebridge.models.operations import Driver
from routebridge.models.orders import Order
from routebridge.models.plans import NotificationDelivery
from routebridge.models.platform import PlatformAdmin, PlatformAuditEvent
from routebridge.models.reliability import AuditEvent
from routebridge.models.workflows import Notification
from routebridge.routes.admin import require_platform_admin
from routebridge.services.platform import admin_count, record_platform_event

router = APIRouter(prefix="/platform", tags=["platform"], dependencies=[Depends(require_platform_admin)])


def _actor(clerk_user: ClerkUser | None) -> str:
    return clerk_user.subject if clerk_user else "local-dev"


def _counts(session: Session, model, column) -> dict:
    return {key: count for key, count in session.exec(select(column, func.count()).select_from(model).group_by(column)).all()}


# ---- companies (workspaces) --------------------------------------------------------------------------------------


class CompanyRead(SQLModel):
    tenant_id: UUID
    name: str
    status: str
    created_at: datetime
    owners: list[str]
    members: int
    drivers: int
    orders: int


@router.get("/tenants", response_model=list[CompanyRead])
def list_companies(session: Session = Depends(get_session)) -> list[CompanyRead]:
    members = _counts(session, TenantMembership, TenantMembership.tenant_id)
    drivers = _counts(session, Driver, Driver.tenant_id)
    orders = _counts(session, Order, Order.tenant_id)
    owners: dict[UUID, list[str]] = {}
    for membership, user in session.exec(
        select(TenantMembership, User).join(User, User.id == TenantMembership.user_id).where(TenantMembership.role == "tenant_owner", TenantMembership.status == "active")
    ).all():
        owners.setdefault(membership.tenant_id, []).append(user.email or user.full_name or user.clerk_user_id)
    rows = session.exec(select(Tenant).order_by(Tenant.created_at.desc())).all()
    return [
        CompanyRead(tenant_id=t.id, name=t.name, status=t.status, created_at=t.created_at, owners=owners.get(t.id, []), members=members.get(t.id, 0), drivers=drivers.get(t.id, 0), orders=orders.get(t.id, 0))
        for t in rows
    ]


class CompanyStatus(SQLModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "suspended"]


@router.post("/tenants/{tenant_id}/status", response_model=CompanyRead)
def set_company_status(tenant_id: UUID, payload: CompanyStatus, session: Session = Depends(get_session), clerk_user: ClerkUser | None = Depends(get_optional_user)) -> CompanyRead:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    previous, tenant.status = tenant.status, payload.status
    session.add(tenant)
    record_platform_event(session, _actor(clerk_user), "tenant.status_changed", "tenant", str(tenant_id), {"from": previous, "to": payload.status, "name": tenant.name})
    session.commit()
    return next(c for c in list_companies(session) if c.tenant_id == tenant_id)


class OwnerAssign(SQLModel):
    model_config = ConfigDict(extra="forbid")
    clerk_user_id: str = Field(min_length=3, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)
    full_name: Optional[str] = Field(default=None, max_length=200)
    replace_existing: bool = False


def _upsert_user(session: Session, clerk_user_id: str, email: str | None, full_name: str | None) -> User:
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user_id)).first()
    if user is None:
        user = User(clerk_user_id=clerk_user_id, email=email, full_name=full_name)
    else:
        user.email = email or user.email
        user.full_name = full_name or user.full_name
        user.status = "active"
        user.updated_at = utc_now()
    session.add(user)
    session.flush()
    return user


def _set_membership(session: Session, tenant_id: UUID, user: User, role: str) -> TenantMembership:
    membership = session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user.id)).first()
    if membership is None:
        membership = TenantMembership(tenant_id=tenant_id, user_id=user.id, role=role)
    membership.role, membership.status = role, "active"
    session.add(membership)
    return membership


@router.post("/tenants/{tenant_id}/owner", response_model=CompanyRead)
def assign_owner(tenant_id: UUID, payload: OwnerAssign, session: Session = Depends(get_session), clerk_user: ClerkUser | None = Depends(get_optional_user)) -> CompanyRead:
    """Make a person the owner of a workspace. With replace_existing, current owners become admins (one clear owner)."""
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    user = _upsert_user(session, payload.clerk_user_id.strip(), payload.email, payload.full_name)
    demoted: list[str] = []
    if payload.replace_existing:
        for membership in session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.role == "tenant_owner", TenantMembership.user_id != user.id)).all():
            membership.role = "tenant_admin"
            session.add(membership)
            demoted.append(str(membership.user_id))
    _set_membership(session, tenant_id, user, "tenant_owner")
    record_platform_event(session, _actor(clerk_user), "tenant.owner_assigned", "tenant", str(tenant_id), {"owner": user.clerk_user_id, "demoted": demoted})
    session.commit()
    return next(c for c in list_companies(session) if c.tenant_id == tenant_id)


# ---- people ------------------------------------------------------------------------------------------------------


class PersonWorkspace(SQLModel):
    tenant_id: UUID
    tenant_name: str
    role: str
    status: str


class PersonRead(SQLModel):
    clerk_user_id: str
    email: Optional[str]
    full_name: Optional[str]
    status: str
    is_platform_admin: bool
    workspaces: list[PersonWorkspace]


@router.get("/users", response_model=list[PersonRead])
def search_people(q: str = "", session: Session = Depends(get_session)) -> list[PersonRead]:
    query = select(User).order_by(User.created_at.desc()).limit(50)
    needle = q.strip().lower()
    if needle:
        like = f"%{needle}%"
        query = select(User).where(func.lower(func.coalesce(User.email, "")).like(like) | func.lower(func.coalesce(User.full_name, "")).like(like) | func.lower(User.clerk_user_id).like(like)).order_by(User.created_at.desc()).limit(50)
    users = session.exec(query).all()
    admins = {a.clerk_user_id for a in session.exec(select(PlatformAdmin)).all()} | set(get_settings().platform_admin_subjects)
    out = []
    for user in users:
        rows = session.exec(select(TenantMembership, Tenant).join(Tenant, Tenant.id == TenantMembership.tenant_id).where(TenantMembership.user_id == user.id)).all()
        out.append(PersonRead(clerk_user_id=user.clerk_user_id, email=user.email, full_name=user.full_name, status=user.status, is_platform_admin=user.clerk_user_id in admins, workspaces=[PersonWorkspace(tenant_id=t.id, tenant_name=t.name, role=m.role, status=m.status) for m, t in rows]))
    return out


class PersonStatus(SQLModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "inactive"]


@router.post("/users/{clerk_user_id}/status", response_model=PersonRead)
def set_person_status(clerk_user_id: str, payload: PersonStatus, session: Session = Depends(get_session), clerk_user: ClerkUser | None = Depends(get_optional_user)) -> PersonRead:
    if clerk_user is not None and clerk_user.subject == clerk_user_id and payload.status == "inactive":
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Person not found")
    user.status, user.updated_at = payload.status, utc_now()
    session.add(user)
    record_platform_event(session, _actor(clerk_user), "user.status_changed", "user", clerk_user_id, {"to": payload.status})
    session.commit()
    return next(p for p in search_people(clerk_user_id, session) if p.clerk_user_id == clerk_user_id)


class WorkspaceMember(SQLModel):
    model_config = ConfigDict(extra="forbid")
    clerk_user_id: str = Field(min_length=3, max_length=200)
    role: str
    email: Optional[str] = Field(default=None, max_length=320)
    full_name: Optional[str] = Field(default=None, max_length=200)


@router.post("/tenants/{tenant_id}/members", response_model=PersonRead, status_code=201)
def add_person_to_company(tenant_id: UUID, payload: WorkspaceMember, session: Session = Depends(get_session), clerk_user: ClerkUser | None = Depends(get_optional_user)) -> PersonRead:
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Unknown role. Choose one of: {', '.join(sorted(ROLES))}")
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    user = _upsert_user(session, payload.clerk_user_id.strip(), payload.email, payload.full_name)
    _set_membership(session, tenant_id, user, payload.role)
    record_platform_event(session, _actor(clerk_user), "tenant.member_added", "tenant", str(tenant_id), {"user": user.clerk_user_id, "role": payload.role})
    session.commit()
    return next(p for p in search_people(user.clerk_user_id, session) if p.clerk_user_id == user.clerk_user_id)


# ---- platform administrators -------------------------------------------------------------------------------------


class AdminRead(SQLModel):
    clerk_user_id: str
    email: Optional[str]
    full_name: Optional[str]
    source: Literal["database", "settings"]
    added_by: Optional[str] = None
    created_at: Optional[datetime] = None


def _admin_rows(session: Session) -> list[AdminRead]:
    rows = [AdminRead(clerk_user_id=a.clerk_user_id, email=a.email, full_name=a.full_name, source="database", added_by=a.added_by, created_at=a.created_at) for a in session.exec(select(PlatformAdmin).order_by(PlatformAdmin.created_at)).all()]
    known = {r.clerk_user_id for r in rows}
    for subject in get_settings().platform_admin_subjects:
        if subject not in known:
            user = session.exec(select(User).where(User.clerk_user_id == subject)).first()
            rows.append(AdminRead(clerk_user_id=subject, email=user.email if user else None, full_name=user.full_name if user else None, source="settings"))
    return rows


@router.get("/admins", response_model=list[AdminRead])
def list_admins(session: Session = Depends(get_session)) -> list[AdminRead]:
    return _admin_rows(session)


class AdminAdd(SQLModel):
    model_config = ConfigDict(extra="forbid")
    clerk_user_id: str = Field(min_length=3, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)
    full_name: Optional[str] = Field(default=None, max_length=200)


@router.post("/admins", response_model=list[AdminRead], status_code=201)
def add_admin(payload: AdminAdd, session: Session = Depends(get_session), clerk_user: ClerkUser | None = Depends(get_optional_user)) -> list[AdminRead]:
    subject = payload.clerk_user_id.strip()
    if any(r.clerk_user_id == subject for r in _admin_rows(session)):
        raise HTTPException(status_code=409, detail="That person is already a platform administrator")
    user = session.exec(select(User).where(User.clerk_user_id == subject)).first()
    session.add(PlatformAdmin(clerk_user_id=subject, email=payload.email or (user.email if user else None), full_name=payload.full_name or (user.full_name if user else None), added_by=_actor(clerk_user)))
    record_platform_event(session, _actor(clerk_user), "platform_admin.added", "user", subject, {})
    session.commit()
    return _admin_rows(session)


@router.delete("/admins/{clerk_user_id}", response_model=list[AdminRead])
def remove_admin(clerk_user_id: str, session: Session = Depends(get_session), clerk_user: ClerkUser | None = Depends(get_optional_user)) -> list[AdminRead]:
    row = session.exec(select(PlatformAdmin).where(PlatformAdmin.clerk_user_id == clerk_user_id)).first()
    if row is None:
        if clerk_user_id in get_settings().platform_admin_subjects:
            raise HTTPException(status_code=409, detail="This administrator is set in the server settings (ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS) and must be removed there.")
        raise HTTPException(status_code=404, detail="Administrator not found")
    if admin_count(session) <= 1:
        raise HTTPException(status_code=409, detail="You cannot remove the last platform administrator")
    session.delete(row)
    record_platform_event(session, _actor(clerk_user), "platform_admin.removed", "user", clerk_user_id, {})
    session.commit()
    return _admin_rows(session)


# ---- system health -----------------------------------------------------------------------------------------------


class HealthItem(SQLModel):
    name: str
    status: Literal["ok", "warning", "down", "off"]
    detail: str


class SystemHealth(SQLModel):
    checked_at: datetime
    items: list[HealthItem]
    totals: dict[str, int]


def _age_minutes(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - value).total_seconds() // 60))


@router.get("/health", response_model=SystemHealth)
def system_health(session: Session = Depends(get_session)) -> SystemHealth:
    settings = get_settings()
    items: list[HealthItem] = []
    try:
        session.exec(text("SELECT 1"))
        items.append(HealthItem(name="Database", status="ok", detail=session.bind.dialect.name))
    except Exception as exc:  # report, do not crash the console
        items.append(HealthItem(name="Database", status="down", detail=type(exc).__name__))
    if settings.redis_url:
        try:
            Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
            items.append(HealthItem(name="Redis", status="ok", detail="rate limits and live updates"))
        except Exception as exc:
            items.append(HealthItem(name="Redis", status="down", detail=type(exc).__name__))
    else:
        items.append(HealthItem(name="Redis", status="off", detail="not configured"))
    items.append(HealthItem(name="Sign-in (Clerk)", status="ok" if settings.clerk_jwks_url and settings.require_clerk_auth else "warning", detail="sign-in enforced" if settings.require_clerk_auth else "sign-in not enforced"))
    items.append(HealthItem(name="SMS", status="ok" if settings.sms_provider == "http" else "off", detail="live provider" if settings.sms_provider == "http" else "log only: messages are not sent"))
    items.append(HealthItem(name="Photo storage", status="ok", detail=settings.media_provider))

    pending = session.exec(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "pending")).one()
    oldest = session.exec(select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status == "pending")).one()
    lag = _age_minutes(oldest)
    items.append(HealthItem(name="Event queue", status="warning" if (lag or 0) >= 10 else "ok", detail=f"{pending} waiting" + (f", oldest {lag} min" if lag else "")))
    queued = session.exec(select(func.count()).select_from(Notification).where(Notification.status == "queued")).one()
    failed = session.exec(select(func.count()).select_from(Notification).where(Notification.status == "failed")).one()
    retrying = session.exec(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.attempts > 0)).one()
    items.append(HealthItem(name="Messages", status="warning" if failed else "ok", detail=f"{queued} queued, {retrying} retrying, {failed} failed"))

    totals = {
        "workspaces": session.exec(select(func.count()).select_from(Tenant)).one(),
        "suspended_workspaces": session.exec(select(func.count()).select_from(Tenant).where(Tenant.status != "active")).one(),
        "people": session.exec(select(func.count()).select_from(User)).one(),
        "drivers": session.exec(select(func.count()).select_from(Driver)).one(),
        "orders": session.exec(select(func.count()).select_from(Order)).one(),
    }
    return SystemHealth(checked_at=utc_now(), items=items, totals=totals)


# ---- audit ------------------------------------------------------------------------------------------------------


class AuditRow(SQLModel):
    occurred_at: datetime
    scope: Literal["platform", "workspace"]
    actor: str
    action: str
    target: str
    detail: str = ""


@router.get("/audit", response_model=list[AuditRow])
def platform_audit(limit: int = 100, session: Session = Depends(get_session)) -> list[AuditRow]:
    limit = max(1, min(limit, 300))
    rows = [
        AuditRow(occurred_at=e.occurred_at, scope="platform", actor=e.actor, action=e.action, target=f"{e.target_type} {e.target_id}", detail=", ".join(f"{k}={v}" for k, v in e.payload.items()))
        for e in session.exec(select(PlatformAuditEvent).order_by(PlatformAuditEvent.occurred_at.desc()).limit(limit)).all()
    ]
    names = {t.id: t.name for t in session.exec(select(Tenant)).all()}
    for event in session.exec(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)).all():
        rows.append(AuditRow(occurred_at=event.occurred_at, scope="workspace", actor=event.actor_type, action=event.event_type, target=names.get(event.tenant_id, str(event.tenant_id)), detail=event.aggregate_type))
    rows.sort(key=lambda row: row.occurred_at.replace(tzinfo=timezone.utc) if row.occurred_at.tzinfo is None else row.occurred_at, reverse=True)
    return rows[:limit]
