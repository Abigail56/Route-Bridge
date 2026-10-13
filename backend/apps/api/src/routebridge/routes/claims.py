"""Claims: a shop reports a problem (dispute, refund, damaged or lost goods) and the company's staff investigate and decide.

Staff routes are under /tenants/{id}/claims. A shop uses /tenants/{id}/portal/claims and only ever sees its own claims, and never the staff-only note.
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict
from sqlmodel import Field, Session, SQLModel, select

from routebridge.auth.authorization import TenantPrincipal, merchant_portal, tenant_member, tenant_roles
from routebridge.db.session import get_session
from routebridge.models.claims import NEXT_STATUS, Claim
from routebridge.models.core import utc_now
from routebridge.models.orders import Merchant, Order
from routebridge.routes.operations import require_tenant
from routebridge.services.events import record_event
from routebridge.services.notifications import queue_merchant_message

READ_ROLES = ("tenant_owner", "tenant_admin", "operations_manager", "finance", "dispatcher")
DECIDE_ROLES = ("tenant_owner", "tenant_admin", "operations_manager", "finance")
staff = APIRouter(prefix="/tenants/{tenant_id}/claims", tags=["claims"], dependencies=[Depends(tenant_member)])
portal = APIRouter(prefix="/tenants/{tenant_id}/portal/claims", tags=["merchant-portal"])


class ClaimRead(SQLModel):
    id: UUID
    merchant_id: UUID
    merchant_name: Optional[str] = None
    order_id: Optional[UUID] = None
    order_ref: Optional[str] = None
    kind: str
    status: str
    raised_by: str
    description: str
    amount_claimed: Decimal
    amount_approved: Optional[Decimal] = None
    resolution_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    decided_at: Optional[datetime] = None


class StaffClaimRead(ClaimRead):
    internal_note: Optional[str] = None


class PortalClaimCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["dispute", "refund", "damage", "loss"]
    order_id: Optional[UUID] = None
    description: str = Field(min_length=5, max_length=2000)
    amount_claimed: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2)


class StaffClaimCreate(PortalClaimCreate):
    merchant_id: UUID


class ClaimUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[Literal["investigating", "approved", "rejected", "paid"]] = None
    amount_approved: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    resolution_note: Optional[str] = Field(default=None, max_length=1000)
    internal_note: Optional[str] = Field(default=None, max_length=1000)


def _reads(session: Session, claims: list[Claim], cls=ClaimRead) -> list:
    merchants = {m.id: m.name for m in session.exec(select(Merchant).where(Merchant.id.in_({c.merchant_id for c in claims}))).all()} if claims else {}
    refs = {o.id: o.external_ref for o in session.exec(select(Order).where(Order.id.in_({c.order_id for c in claims if c.order_id}))).all()} if any(c.order_id for c in claims) else {}
    return [cls(**c.model_dump(), merchant_name=merchants.get(c.merchant_id), order_ref=refs.get(c.order_id)) for c in claims]


def _open_claim(session: Session, tenant_id: UUID, merchant_id: UUID, payload: PortalClaimCreate, raised_by: str) -> Claim:
    if payload.order_id is not None:
        order = session.get(Order, payload.order_id)
        # an order of another shop or company looks exactly like one that does not exist
        if order is None or order.tenant_id != tenant_id or order.merchant_id != merchant_id:
            raise HTTPException(status_code=404, detail="Order not found")
    claim = Claim(tenant_id=tenant_id, merchant_id=merchant_id, order_id=payload.order_id, kind=payload.kind, description=payload.description.strip(), amount_claimed=payload.amount_claimed, raised_by=raised_by)
    session.add(claim)
    session.flush()
    record_event(session, tenant_id, "claim.opened", "claim", claim.id, {"kind": claim.kind, "merchant_id": str(merchant_id), "amount": str(claim.amount_claimed), "raised_by": raised_by})
    session.commit()
    session.refresh(claim)
    return claim


@staff.get("", response_model=list[StaffClaimRead], dependencies=[Depends(tenant_roles(*READ_ROLES))])
def list_claims(tenant_id: UUID, status: Optional[str] = Query(default=None), merchant_id: Optional[UUID] = None, session: Session = Depends(get_session)) -> list[StaffClaimRead]:
    require_tenant(session, tenant_id)
    query = select(Claim).where(Claim.tenant_id == tenant_id)
    if status:
        query = query.where(Claim.status == status)
    if merchant_id:
        query = query.where(Claim.merchant_id == merchant_id)
    return _reads(session, list(session.exec(query.order_by(Claim.created_at.desc()).limit(300)).all()), StaffClaimRead)


@staff.post("", response_model=StaffClaimRead, status_code=201, dependencies=[Depends(tenant_roles(*READ_ROLES))])
def staff_open_claim(tenant_id: UUID, payload: StaffClaimCreate, session: Session = Depends(get_session)) -> StaffClaimRead:
    """Staff can log a claim for a shop (for example one received by phone)."""
    require_tenant(session, tenant_id)
    merchant = session.get(Merchant, payload.merchant_id)
    if merchant is None or merchant.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return _reads(session, [_open_claim(session, tenant_id, merchant.id, payload, "staff")], StaffClaimRead)[0]


@staff.patch("/{claim_id}", response_model=StaffClaimRead, dependencies=[Depends(tenant_roles(*DECIDE_ROLES))])
def update_claim(tenant_id: UUID, claim_id: UUID, payload: ClaimUpdate, session: Session = Depends(get_session)) -> StaffClaimRead:
    claim = session.get(Claim, claim_id)
    if claim is None or claim.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Claim not found")
    if payload.status is not None and payload.status != claim.status:
        if payload.status not in NEXT_STATUS[claim.status]:
            raise HTTPException(status_code=409, detail=f"A claim that is {claim.status} cannot become {payload.status}.")
        if payload.status == "approved":
            approved = payload.amount_approved if payload.amount_approved is not None else claim.amount_claimed
            if approved > claim.amount_claimed and claim.raised_by == "merchant":
                raise HTTPException(status_code=422, detail="The approved amount cannot be more than the shop claimed.")
            claim.amount_approved = approved
        if payload.status in ("approved", "rejected"):
            claim.decided_at = utc_now()
            if payload.status == "rejected":
                claim.amount_approved = None
                if not (payload.resolution_note or claim.resolution_note):
                    raise HTTPException(status_code=422, detail="Give the shop a reason when you reject a claim.")
        claim.status = payload.status
    elif payload.amount_approved is not None:
        raise HTTPException(status_code=422, detail="Set the approved amount when you approve the claim.")
    if payload.resolution_note is not None:
        claim.resolution_note = payload.resolution_note.strip() or None
    if payload.internal_note is not None:
        claim.internal_note = payload.internal_note.strip() or None
    claim.updated_at = utc_now()
    session.add(claim)
    if payload.status in ("approved", "rejected", "paid"):
        shop = session.get(Merchant, claim.merchant_id)
        outcome = {"rejected": "not approved", "paid": "marked as paid"}.get(payload.status) or f"approved for NGN {claim.amount_approved or 0:,.0f}"
        if shop is not None:
            queue_merchant_message(session, tenant_id, shop, "claim_update", f"Your {claim.kind} claim was {outcome}." + (f" {claim.resolution_note}" if claim.resolution_note else ""))
    record_event(session, tenant_id, "claim.updated", "claim", claim.id, {"status": claim.status, "amount_approved": str(claim.amount_approved) if claim.amount_approved is not None else None})
    session.commit()
    session.refresh(claim)
    return _reads(session, [claim], StaffClaimRead)[0]


@portal.get("", response_model=list[ClaimRead])
def portal_claims(tenant_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> list[ClaimRead]:
    rows = session.exec(select(Claim).where(Claim.tenant_id == tenant_id, Claim.merchant_id == principal.merchant_id).order_by(Claim.created_at.desc()).limit(200)).all()
    return _reads(session, list(rows))


@portal.post("", response_model=ClaimRead, status_code=201)
def portal_open_claim(tenant_id: UUID, payload: PortalClaimCreate, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> ClaimRead:
    """The shop comes from the account, never from the request."""
    return _reads(session, [_open_claim(session, tenant_id, principal.merchant_id, payload, "merchant")])[0]
