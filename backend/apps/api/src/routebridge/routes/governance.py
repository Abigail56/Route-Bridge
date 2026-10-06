"""Audit history, user/role administration and data-subject (NDPA) workflows."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict
from sqlmodel import Field, Session, SQLModel, select

from routebridge.auth.authorization import tenant_member, tenant_roles
from routebridge.db.session import get_session
from routebridge.models.access import ROLES, TenantMembership, User
from routebridge.models.core import Tenant, utc_now
from routebridge.models.orders import Customer, DeliveryJob, Order, Stop
from routebridge.models.plans import ConsentRecord, StopCorrection, TrackingToken, NotificationDelivery
from routebridge.models.reliability import AuditEvent
from routebridge.models.workflows import Notification
from routebridge.routes.operations import require_tenant
from routebridge.services.events import record_event

ADMIN_ROLES = ("tenant_owner", "tenant_admin")
AUDIT_ROLES = ("tenant_owner", "tenant_admin", "operations_manager")
router = APIRouter(prefix="/tenants/{tenant_id}", tags=["governance"], dependencies=[Depends(tenant_member)])


# ---- audit history -----------------------------------------------------------------------------------------------


@router.get("/audit", response_model=list[AuditEvent], dependencies=[Depends(tenant_roles(*AUDIT_ROLES))])
def list_audit(
    tenant_id: UUID,
    aggregate_type: Optional[str] = None,
    aggregate_id: Optional[UUID] = None,
    event_type: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[AuditEvent]:
    require_tenant(session, tenant_id)
    query = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
    if aggregate_type:
        query = query.where(AuditEvent.aggregate_type == aggregate_type)
    if aggregate_id:
        query = query.where(AuditEvent.aggregate_id == aggregate_id)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    return list(session.exec(query.order_by(AuditEvent.occurred_at.desc()).offset(offset).limit(limit)).all())


# ---- workspace name ----------------------------------------------------------------------------------------------


class WorkspaceRename(SQLModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)


class WorkspaceRead(SQLModel):
    id: UUID
    name: str


@router.patch("/workspace", response_model=WorkspaceRead, dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def rename_workspace(tenant_id: UUID, payload: WorkspaceRename, session: Session = Depends(get_session)) -> WorkspaceRead:
    """Owners and admins can rename their own workspace."""
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    name = " ".join(payload.name.split())
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Enter a name of at least 2 characters")
    previous, tenant.name = tenant.name, name
    session.add(tenant)
    record_event(session, tenant_id, "tenant.renamed", "tenant", tenant_id, {"from": previous, "to": name})
    session.commit()
    return WorkspaceRead(id=tenant.id, name=tenant.name)


# ---- members & roles ---------------------------------------------------------------------------------------------


class MemberRead(SQLModel):
    membership_id: UUID
    user_id: UUID
    clerk_user_id: str
    email: Optional[str]
    full_name: Optional[str]
    role: str
    status: str


class MemberCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    clerk_user_id: str = Field(min_length=3, max_length=200)
    role: str
    email: Optional[str] = Field(default=None, max_length=320)
    full_name: Optional[str] = Field(default=None, max_length=200)


class MemberUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    role: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


def _member_read(user: User, membership: TenantMembership) -> MemberRead:
    return MemberRead(membership_id=membership.id, user_id=user.id, clerk_user_id=user.clerk_user_id, email=user.email, full_name=user.full_name, role=membership.role, status=membership.status)


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Unknown role. Choose one of: {', '.join(sorted(ROLES))}")


def _active_owner_count(session: Session, tenant_id: UUID) -> int:
    return len(session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.role == "tenant_owner", TenantMembership.status == "active")).all())


@router.get("/members", response_model=list[MemberRead], dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def list_members(tenant_id: UUID, session: Session = Depends(get_session)) -> list[MemberRead]:
    require_tenant(session, tenant_id)
    rows = session.exec(select(TenantMembership, User).join(User, User.id == TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id).order_by(User.full_name)).all()
    return [_member_read(u, m) for m, u in rows]


@router.post("/members", response_model=MemberRead, status_code=201, dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def add_member(tenant_id: UUID, payload: MemberCreate, session: Session = Depends(get_session)) -> MemberRead:
    """Link an existing Clerk identity to this tenant with a role (the user signs in through Clerk as usual)."""
    require_tenant(session, tenant_id)
    _check_role(payload.role)
    user = session.exec(select(User).where(User.clerk_user_id == payload.clerk_user_id)).first()
    if user is None:
        user = User(clerk_user_id=payload.clerk_user_id, email=payload.email, full_name=payload.full_name)
        session.add(user)
        session.flush()
    existing = session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user.id)).first()
    if existing is not None and existing.status == "active":
        raise HTTPException(status_code=409, detail="User is already a member of this tenant")
    membership = existing or TenantMembership(tenant_id=tenant_id, user_id=user.id, role=payload.role)
    membership.role, membership.status, membership.updated_at = payload.role, "active", utc_now()
    session.add(membership)
    session.flush()
    record_event(session, tenant_id, "member.added", "membership", membership.id, {"role": payload.role})
    session.commit()
    return _member_read(user, membership)


@router.patch("/members/{membership_id}", response_model=MemberRead, dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def update_member(tenant_id: UUID, membership_id: UUID, payload: MemberUpdate, session: Session = Depends(get_session)) -> MemberRead:
    membership = session.get(TenantMembership, membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    if payload.role is not None:
        _check_role(payload.role)
    leaving_owner = membership.role == "tenant_owner" and membership.status == "active" and (
        (payload.role is not None and payload.role != "tenant_owner") or payload.status == "inactive"
    )
    if leaving_owner and _active_owner_count(session, tenant_id) <= 1:
        raise HTTPException(status_code=409, detail="A tenant must keep at least one active owner")
    if payload.role is not None:
        membership.role = payload.role
    if payload.status is not None:
        membership.status = payload.status
    membership.updated_at = utc_now()
    record_event(session, tenant_id, "member.updated", "membership", membership.id, {"role": membership.role, "status": membership.status})
    session.commit()
    user = session.get(User, membership.user_id)
    return _member_read(user, membership)


# ---- data-subject workflows (NDPA) -------------------------------------------------------------------------------


def _customer_or_404(session: Session, tenant_id: UUID, customer_id: UUID) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("/customers/{customer_id}/export", dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def export_customer_data(tenant_id: UUID, customer_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Subject-access export: everything held about one customer."""
    customer = _customer_or_404(session, tenant_id, customer_id)
    orders = session.exec(select(Order).where(Order.customer_id == customer.id)).all()
    jobs = session.exec(select(DeliveryJob).where(DeliveryJob.order_id.in_([o.id for o in orders]))).all() if orders else []
    stops = session.exec(select(Stop).where(Stop.delivery_job_id.in_([j.id for j in jobs]))).all() if jobs else []
    consents = session.exec(select(ConsentRecord).where(ConsentRecord.customer_id == customer.id)).all()
    record_event(session, tenant_id, "privacy.export", "customer", customer.id, {})
    session.commit()
    return {
        "customer": {"id": customer.id, "name": customer.name, "phone": customer.phone, "status": customer.status, "created_at": customer.created_at},
        "orders": [{"id": o.id, "external_ref": o.external_ref, "status": o.status, "total_amount": str(o.total_amount), "cod_amount": str(o.cod_amount), "created_at": o.created_at} for o in orders],
        "delivery_locations": [{"address_text": s.address_text, "landmark": s.landmark, "delivery_notes": s.delivery_notes, "latitude": s.latitude, "longitude": s.longitude} for s in stops],
        "consents": [{"purpose": c.purpose, "granted": c.granted, "lawful_basis": c.lawful_basis, "recorded_at": c.recorded_at} for c in consents],
    }


@router.post("/customers/{customer_id}/erase", dependencies=[Depends(tenant_roles(*ADMIN_ROLES))])
def erase_customer_data(tenant_id: UUID, customer_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Right to erasure: anonymise personal data while keeping order/payment rows needed for financial records.
    The audit trail is append-only and holds no personal data (events carry ids and status only)."""
    customer = _customer_or_404(session, tenant_id, customer_id)
    if customer.status == "erased":
        return {"erased": True, "already": True}
    orders = session.exec(select(Order).where(Order.customer_id == customer.id)).all()
    job_ids = [j.id for j in session.exec(select(DeliveryJob).where(DeliveryJob.order_id.in_([o.id for o in orders]))).all()] if orders else []
    if job_ids:
        for stop in session.exec(select(Stop).where(Stop.delivery_job_id.in_(job_ids))).all():
            stop.address_text, stop.landmark, stop.delivery_notes, stop.latitude, stop.longitude = "[erased]", None, None, None, None
        for corr in session.exec(select(StopCorrection).where(StopCorrection.delivery_job_id.in_(job_ids))).all():
            corr.address_text, corr.landmark, corr.delivery_notes, corr.latitude, corr.longitude, corr.plus_code = None, None, None, None, None, None
        for tok in session.exec(select(TrackingToken).where(TrackingToken.delivery_job_id.in_(job_ids))).all():
            tok.revoked = True
    for n in session.exec(select(Notification).where(Notification.order_id.in_([o.id for o in orders]), Notification.status == "queued")).all() if orders else []:
        n.status = "cancelled"
        delivery = session.get(NotificationDelivery, n.id)
        if delivery:
            delivery.body = "[erased]"
    customer.name, customer.phone, customer.status = "Erased customer", f"erased-{str(customer.id)[:8]}", "erased"
    record_event(session, tenant_id, "privacy.erased", "customer", customer.id, {"orders": len(orders)})
    session.commit()
    return {"erased": True, "orders_anonymised": len(orders)}


class ConsentCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["sms", "whatsapp", "location"]
    granted: bool
    lawful_basis: Literal["consent", "contract", "legal_obligation", "legitimate_interest"] = "consent"


@router.post("/customers/{customer_id}/consent", status_code=201, dependencies=[Depends(tenant_roles(*ADMIN_ROLES, "dispatcher", "operations_manager"))])
def record_consent(tenant_id: UUID, customer_id: UUID, payload: ConsentCreate, session: Session = Depends(get_session)) -> dict:
    customer = _customer_or_404(session, tenant_id, customer_id)
    record = ConsentRecord(tenant_id=tenant_id, customer_id=customer.id, **payload.model_dump())
    session.add(record)
    record_event(session, tenant_id, "privacy.consent_recorded", "customer", customer.id, {"purpose": payload.purpose, "granted": payload.granted})
    session.commit()
    return {"id": record.id, "purpose": payload.purpose, "granted": payload.granted, "recorded_at": record.recorded_at}
