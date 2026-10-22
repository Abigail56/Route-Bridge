"""Join requests: a person who signed up as a shop or a Dispatcher (rider) presses "Send to the Admin" on the "not linked yet"
screen, and the request appears on the Admin's console (with a sound) instead of the person having to copy their user id into
a chat. It only carries the id and what they want to be; the owner still adds them the usual way, and nothing is granted here.

Which company receives it: ROUTEBRIDGE_JOIN_REQUESTS_TENANT_ID when set; otherwise the only active workspace; otherwise the one
workspace owned by a RouteBridge administrator (the Admin, e.g. PLATFORM_ADMIN_EMAILS). If none of these picks exactly one, the
request is refused (409) and the screen falls back to copy / WhatsApp, so a sign-up is never shown to the wrong company.
"""
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from routebridge.auth.authorization import TenantPrincipal, tenant_roles
from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.integrations.sessions import AuthUser
from routebridge.models.access import TenantMembership, User
from routebridge.models.core import Tenant, utc_now
from routebridge.models.join_request import JoinRequest
from routebridge.services.driver_zones import split_zone_names
from routebridge.services.platform import is_platform_admin

me = APIRouter(prefix="/auth/me/join-request", tags=["auth"])
staff = APIRouter(prefix="/tenants/{tenant_id}/join-requests", tags=["administration"])

RESEND_AFTER = timedelta(seconds=60)  # pressing the button again within a minute does not ring the Admin again


class JoinRequestSend(BaseModel):
    role: Literal["merchant_user", "driver"]
    shop_name: str | None = Field(default=None, max_length=120)


class MyJoinRequest(BaseModel):
    sent: bool
    role: str | None = None
    sent_at: datetime | None = None
    company: str | None = None


class JoinRequestRead(BaseModel):
    id: UUID
    clerk_user_id: str
    role: str
    shop_name: str | None
    full_name: str | None
    email: str | None
    phone: str | None
    place: str | None
    zones: list[str]
    rider_registered: bool
    sent_at: datetime


def _me(session: Session, clerk_user: AuthUser | None) -> User:
    from routebridge.routes.auth import _ensure_user

    if clerk_user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return _ensure_user(session, clerk_user)


def _receiving_tenant(session: Session) -> Tenant:
    configured = get_settings().join_requests_tenant_id
    if configured is not None:
        tenant = session.get(Tenant, configured)
        if tenant is not None and tenant.status == "active":
            return tenant
    else:
        active = session.exec(select(Tenant).where(Tenant.status == "active").limit(2)).all()
        if len(active) == 1:
            return active[0]
        owned = session.exec(
            select(Tenant, User.clerk_user_id).join(TenantMembership, TenantMembership.tenant_id == Tenant.id).join(User, User.id == TenantMembership.user_id)
            .where(Tenant.status == "active", TenantMembership.role == "tenant_owner", TenantMembership.status == "active")
        ).all()
        admins_own = {tenant.id: tenant for tenant, subject in owned if is_platform_admin(session, subject)}
        if len(admins_own) == 1:
            return next(iter(admins_own.values()))
    raise HTTPException(status_code=409, detail="Sending is not available right now. Copy your ID and send it to the Admin on WhatsApp.")


def _rider_registered(user: User) -> bool:
    return bool(user.full_name and user.phone and user.photo and split_zone_names(user.rider_zones))


@me.get("", response_model=MyJoinRequest)
def my_join_request(session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[AuthUser | None, Depends(get_optional_user)]) -> MyJoinRequest:
    user = _me(session, clerk_user)
    row = session.exec(select(JoinRequest).where(JoinRequest.user_id == user.id, JoinRequest.status == "open").order_by(JoinRequest.sent_at.desc())).first()
    if row is None:
        return MyJoinRequest(sent=False)
    tenant = session.get(Tenant, row.tenant_id)
    return MyJoinRequest(sent=True, role=row.role, sent_at=row.sent_at, company=tenant.name if tenant else None)


@me.post("", response_model=MyJoinRequest)
def send_join_request(payload: JoinRequestSend, session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[AuthUser | None, Depends(get_optional_user)]) -> MyJoinRequest:
    user = _me(session, clerk_user)
    if payload.role == "driver" and not _rider_registered(user):
        raise HTTPException(status_code=422, detail="Save your driver details (name, phone, picture and zones) first, then send.")
    tenant = _receiving_tenant(session)
    linked = session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant.id, TenantMembership.user_id == user.id, TenantMembership.status == "active")).first()
    if linked is not None:
        raise HTTPException(status_code=409, detail="You have already been added. Press “check again”.")
    shop_name = " ".join((payload.shop_name or "").split())[:120] or None
    row = session.exec(select(JoinRequest).where(JoinRequest.tenant_id == tenant.id, JoinRequest.user_id == user.id)).first()
    now = utc_now()
    if row is None:
        row = JoinRequest(tenant_id=tenant.id, user_id=user.id, role=payload.role, shop_name=shop_name, sent_at=now)
    else:
        sent_at = row.sent_at if row.sent_at.tzinfo else row.sent_at.replace(tzinfo=now.tzinfo)
        fresh = row.status == "open" and row.role == payload.role and now - sent_at < RESEND_AFTER
        row.role, row.shop_name, row.status = payload.role, shop_name, "open"
        if not fresh:
            row.sent_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return MyJoinRequest(sent=True, role=row.role, sent_at=row.sent_at, company=tenant.name)


@staff.get("", response_model=list[JoinRequestRead])
def list_join_requests(tenant_id: UUID, _: Annotated[TenantPrincipal, Depends(tenant_roles("tenant_owner", "tenant_admin"))], session: Annotated[Session, Depends(get_session)]) -> list[JoinRequestRead]:
    """Open requests from people not yet added to this company, newest first. Someone the owner has since added drops out by itself."""
    members = select(TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id, TenantMembership.status == "active")
    rows = session.exec(
        select(JoinRequest, User)
        .join(User, User.id == JoinRequest.user_id)
        .where(JoinRequest.tenant_id == tenant_id, JoinRequest.status == "open", User.status == "active", JoinRequest.user_id.not_in(members))
        .order_by(JoinRequest.sent_at.desc())
        .limit(100)
    ).all()
    return [JoinRequestRead(
        id=row.id, clerk_user_id=user.clerk_user_id, role=row.role, shop_name=row.shop_name, full_name=user.full_name, email=user.email,
        phone=user.phone, place=", ".join(part for part in (user.region, user.state) if part) or None, zones=split_zone_names(user.rider_zones),
        rider_registered=_rider_registered(user), sent_at=row.sent_at,
    ) for row, user in rows]


@staff.post("/{request_id}/dismiss")
def dismiss_join_request(tenant_id: UUID, request_id: UUID, _: Annotated[TenantPrincipal, Depends(tenant_roles("tenant_owner"))], session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    row = session.get(JoinRequest, request_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Request not found")
    row.status = "dismissed"
    session.add(row)
    session.commit()
    return {"status": "dismissed"}
