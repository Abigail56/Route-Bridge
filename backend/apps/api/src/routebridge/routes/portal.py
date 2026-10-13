"""Merchant portal: what a shop's own staff may see and do.

Every route here is fenced to ONE merchant: the one their membership is linked to. A merchant user can never reach another
shop's orders, the riders, reports, members or settings (the general routes refuse the merchant_user role outright).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import ConfigDict, field_validator
from sqlmodel import Field, Session, SQLModel, select

from routebridge.auth.authorization import TenantPrincipal, merchant_portal
from routebridge.db.session import get_session
from routebridge.models.catalog import ServiceZone, _check_email, _check_phone
from routebridge.models.core import OperatingArea, Tenant
from routebridge.models.merchant_profile import MerchantProfile, is_complete
from routebridge.services import order_extras
from routebridge.services.billing import enforce_shop
from routebridge.services.events import record_event
from routebridge.models.orders import Merchant, Order, OrderCreate, OrderRead
from routebridge.routes.orders import create_order, to_order_read, to_order_reads
from routebridge.services.statements import build_statement, statement_csv

router = APIRouter(prefix="/tenants/{tenant_id}/portal", tags=["merchant-portal"])

IN_PROGRESS = {"pending", "assigned", "accepted", "en_route", "arrived"}
PROBLEMS = {"failed_attempt", "rescheduled", "returned", "cancelled"}


class PortalMe(SQLModel):
    merchant_id: UUID
    merchant_name: str
    workspace_name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    profile_complete: bool = False


class PortalOrder(SQLModel):
    """What a merchant sees about one of its own orders. No rider details, no other shop's data."""

    id: UUID
    external_ref: str
    status: str
    customer_name: Optional[str] = None
    address_text: Optional[str] = None
    landmark: Optional[str] = None
    total_amount: Decimal
    cod_amount: Decimal
    currency: str
    created_at: datetime
    tracking_token: Optional[str] = None
    rider_assigned: bool = False
    code_verified: bool = False
    zone_name: Optional[str] = None


class PortalOrderCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str = Field(min_length=5, max_length=30)
    external_ref: Optional[str] = Field(default=None, max_length=100)
    total_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2)
    cod_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2)
    address_text: str = Field(min_length=1, max_length=500)
    landmark: Optional[str] = Field(default=None, max_length=300)
    delivery_notes: Optional[str] = Field(default=None, max_length=1000)
    # every order says which delivery zone it goes to (Lagos or one of the others the company serves)
    service_zone_id: UUID


class PortalZone(SQLModel):
    id: UUID
    name: str


class PortalSummary(SQLModel):
    orders_total: int
    in_progress: int
    delivered: int
    problems: int
    cod_to_collect: Decimal
    cod_collected: Decimal


def _zone_names(session: Session, tenant_id: UUID) -> dict[UUID, str]:
    return {z.id: z.name for z in session.exec(select(ServiceZone).where(ServiceZone.tenant_id == tenant_id)).all()}


def _portal_order(read: OrderRead, zones: dict[UUID, str] | None = None) -> PortalOrder:
    return PortalOrder(zone_name=(zones or {}).get(read.service_zone_id) if read.service_zone_id else None, 
        id=read.id, external_ref=read.external_ref, status=read.job_status or "pending", customer_name=read.customer_name,
        address_text=read.address_text, landmark=read.landmark, total_amount=read.total_amount, cod_amount=read.cod_amount,
        currency=read.currency, created_at=read.created_at, tracking_token=read.tracking_token, rider_assigned=read.driver_id is not None, code_verified=read.code_verified,
    )


def _own_orders(session: Session, principal: TenantPrincipal, tenant_id: UUID):
    return select(Order).where(Order.tenant_id == tenant_id, Order.merchant_id == principal.merchant_id)


@router.get("/me", response_model=PortalMe)
def portal_me(tenant_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> PortalMe:
    merchant = session.get(Merchant, principal.merchant_id)
    tenant = session.get(Tenant, tenant_id)
    if merchant is None or merchant.tenant_id != tenant_id or tenant is None:
        raise HTTPException(status_code=403, detail="Your account is linked to a merchant that no longer exists. Ask the company owner.")
    profile = session.exec(select(MerchantProfile).where(MerchantProfile.merchant_id == merchant.id)).first()
    return PortalMe(merchant_id=merchant.id, merchant_name=merchant.name, workspace_name=tenant.name, contact_phone=merchant.contact_phone, contact_email=merchant.contact_email, profile_complete=is_complete(merchant.contact_phone, profile))


class PortalPhone(SQLModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=7, max_length=30)
    email: Optional[str] = Field(default=None, max_length=320)  # left out = unchanged, empty = remove

    @field_validator("email")
    @classmethod
    def _email(cls, value: Optional[str]) -> Optional[str]:
        return _check_email(value) if value is not None else None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        cleaned = _check_phone(value)
        if cleaned is None:
            raise ValueError("Enter a phone number such as +2348012345678")
        return cleaned


@router.put("/phone", response_model=PortalMe)
def portal_set_phone(tenant_id: UUID, payload: PortalPhone, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> PortalMe:
    """The shop's own phone number, set from its dashboard. The shop comes from the account, never from the request."""
    merchant = session.get(Merchant, principal.merchant_id)
    if merchant is None or merchant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Your account is linked to a merchant that no longer exists. Ask the company owner.")
    merchant.contact_phone = payload.phone
    if "email" in payload.model_fields_set:
        merchant.contact_email = payload.email
    session.add(merchant)
    record_event(session, tenant_id, "merchant.updated", "merchant", merchant.id, {"fields": ["contact_phone", "contact_email"] if "email" in payload.model_fields_set else ["contact_phone"], "by": "merchant"})
    session.commit()
    return portal_me(tenant_id, principal, session)


@router.get("/orders", response_model=list[PortalOrder])
def portal_orders(
    tenant_id: UUID,
    limit: int = Query(default=100, ge=1, le=300),
    principal: TenantPrincipal = Depends(merchant_portal),
    session: Session = Depends(get_session),
) -> list[PortalOrder]:
    orders = session.exec(_own_orders(session, principal, tenant_id).order_by(Order.created_at.desc()).limit(limit)).all()
    zones = _zone_names(session, tenant_id)
    return [_portal_order(read, zones) for read in to_order_reads(session, list(orders))]


@router.get("/orders/{order_id}", response_model=PortalOrder)
def portal_order(tenant_id: UUID, order_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> PortalOrder:
    order = session.exec(_own_orders(session, principal, tenant_id).where(Order.id == order_id)).first()
    if order is None:  # another shop's order looks exactly like one that does not exist
        raise HTTPException(status_code=404, detail="Order not found")
    return _portal_order(to_order_read(session, order), _zone_names(session, tenant_id))


@router.get("/zones", response_model=list[PortalZone])
def portal_zones(tenant_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> list[PortalZone]:
    """The delivery zones a shop can pick for an order (names only: rates and settings stay with the company)."""
    return [PortalZone(id=zone_id, name=name) for zone_id, name in sorted(_zone_names(session, tenant_id).items(), key=lambda item: item[1].lower())]


class PortalZoneCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)


@router.post("/zones", response_model=PortalZone, status_code=201)
def portal_add_zone(tenant_id: UUID, payload: PortalZoneCreate, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> PortalZone:
    """A shop adds the zone (city or area) it is in when it is not on the list yet. The same name is never made twice."""
    name = " ".join(payload.name.split())
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Type the name of your zone, for example Lagos")
    existing = next((z for z in session.exec(select(ServiceZone).where(ServiceZone.tenant_id == tenant_id)).all() if z.name.lower() == name.lower()), None)
    if existing is not None:
        return PortalZone(id=existing.id, name=existing.name)
    area = session.exec(select(OperatingArea).where(OperatingArea.name.ilike(name))).first() or session.exec(select(OperatingArea).order_by(OperatingArea.name)).first()
    if area is None:
        raise HTTPException(status_code=409, detail="No delivery regions are set up on this platform yet. Ask the Admin.")
    code = "".join(ch for ch in name.upper() if ch.isalnum())[:20] or "ZONE"
    zone = ServiceZone(tenant_id=tenant_id, operating_area_id=area.id, code=code, name=name)
    session.add(zone)
    session.flush()
    record_event(session, tenant_id, "service_zone.created", "service_zone", zone.id, {"name": name, "by": "merchant"})
    session.commit()
    return PortalZone(id=zone.id, name=zone.name)


@router.post("/orders", response_model=PortalOrder, status_code=201)
def portal_create_order(
    tenant_id: UUID,
    payload: PortalOrderCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: TenantPrincipal = Depends(merchant_portal),
    session: Session = Depends(get_session),
) -> PortalOrder:
    """Create an order for this merchant only: the merchant is taken from the account, never from the request."""
    shop = session.get(Merchant, principal.merchant_id)
    if shop is None or not shop.contact_phone:
        # the shop's number is how it is reached about its orders: it comes first
        raise HTTPException(status_code=422, detail="Finish registering your shop first: your phone number, address and the bank account you are paid into. Then you can create orders.")
    if not is_complete(shop.contact_phone, session.exec(select(MerchantProfile).where(MerchantProfile.merchant_id == shop.id)).first()):
        raise HTTPException(status_code=422, detail="Finish registering your shop first: your address and the bank account you are paid into. Then you can create orders.")
    enforce_shop(session, tenant_id, shop.id)  # a shop whose plan has ended must pay online first
    reference = (payload.external_ref or "").strip() or f"M-{datetime.now():%y%m%d}-{uuid4().hex[:6].upper()}"
    full = OrderCreate(
        merchant_id=principal.merchant_id, customer_name=payload.customer_name, customer_phone=payload.customer_phone, external_ref=reference,
        total_amount=payload.total_amount, cod_amount=payload.cod_amount, address_text=payload.address_text, landmark=payload.landmark,
        delivery_notes=payload.delivery_notes, service_zone_id=payload.service_zone_id,
    )
    return _portal_order(create_order(tenant_id, full, idempotency_key, session), _zone_names(session, tenant_id))


@router.get("/orders/{order_id}/tracking-share")
def portal_tracking_share(tenant_id: UUID, order_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> dict:
    order = session.exec(_own_orders(session, principal, tenant_id).where(Order.id == order_id)).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_extras.tracking_share(session, order)


@router.post("/orders/{order_id}/tracking-share/send", status_code=201)
def portal_send_tracking_share(tenant_id: UUID, order_id: UUID, channel: str, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> dict:
    order = session.exec(_own_orders(session, principal, tenant_id).where(Order.id == order_id)).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order_extras.send_tracking_link(session, order, channel, by="merchant")
    return order_extras.tracking_share(session, order)


@router.get("/orders/{order_id}/evidence")
def portal_evidence(tenant_id: UUID, order_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> dict:
    order = session.exec(_own_orders(session, principal, tenant_id).where(Order.id == order_id)).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_extras.evidence(session, order, staff=False)


@router.get("/summary", response_model=PortalSummary)
def portal_summary(tenant_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> PortalSummary:
    orders = list(session.exec(_own_orders(session, principal, tenant_id)).all())
    reads = to_order_reads(session, orders)
    in_progress = [r for r in reads if (r.job_status or "pending") in IN_PROGRESS]
    delivered = [r for r in reads if r.job_status == "delivered"]
    return PortalSummary(
        orders_total=len(reads), in_progress=len(in_progress), delivered=len(delivered), problems=sum(1 for r in reads if r.job_status in PROBLEMS),
        cod_to_collect=sum((r.cod_amount for r in in_progress), Decimal("0.00")), cod_collected=sum((r.cod_amount for r in delivered), Decimal("0.00")),
    )


@router.get("/statement")
def portal_statement(tenant_id: UUID, start: datetime = Query(alias="from"), end: datetime = Query(alias="to"), principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> dict:
    """The shop's own payout statement. The merchant comes from the account, never from the request."""
    return jsonable_encoder(_own_statement(session, principal, tenant_id, start, end))


@router.get("/statement.csv")
def portal_statement_csv(tenant_id: UUID, start: datetime = Query(alias="from"), end: datetime = Query(alias="to"), principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> Response:
    statement = _own_statement(session, principal, tenant_id, start, end)
    return Response(statement_csv(statement), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=statement.csv"})


def _own_statement(session: Session, principal: TenantPrincipal, tenant_id: UUID, start: datetime, end: datetime) -> dict:
    merchant = session.get(Merchant, principal.merchant_id)
    if merchant is None or merchant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Your account is linked to a merchant that no longer exists. Ask the company owner.")
    if end <= start:
        raise HTTPException(status_code=422, detail="'to' must be after 'from'")
    return build_statement(session, tenant_id, merchant, start, end)
