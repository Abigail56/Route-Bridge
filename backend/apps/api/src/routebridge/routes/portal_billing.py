"""A shop's own plan and billing: what it is on, choosing a plan and paying for it online with Paystack (naira).

Everything here is fenced to the ONE shop the signed-in account belongs to. The shop never sees another shop's plan or payments.
"""
import secrets
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from routebridge.auth.authorization import TenantPrincipal, merchant_portal
from routebridge.config.plans import SHOP_PAID_PLANS, SHOP_PLANS, ShopPlan, get_shop_plan
from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.integrations.paystack import PaystackError, get_paystack
from routebridge.models.billing import BillingPayment
from routebridge.models.orders import Merchant
from routebridge.routes.billing import settle
from routebridge.services.billing import shop_billing_enforced, shop_orders_this_month, shop_plan_row, shop_state

router = APIRouter(prefix="/tenants/{tenant_id}/portal/billing", tags=["merchant-portal"])


class ShopPlanRead(BaseModel):
    key: str
    name: str
    price_ngn: int
    orders_per_month: int | None
    blurb: str


class ShopPaymentRead(BaseModel):
    reference: str
    plan: str
    amount_ngn: int
    status: str
    created_at: datetime
    paid_at: datetime | None


class ShopBillingRead(BaseModel):
    plan: ShopPlanRead
    status: str
    valid_until: datetime | None
    days_left: int | None
    enforced: bool
    payments_enabled: bool
    orders_this_month: int
    plans: list[ShopPlanRead]
    payments: list[ShopPaymentRead]


class ShopCheckoutIn(BaseModel):
    plan: Literal["basic", "standard", "pro"]
    # Paystack needs an email for the receipt. A real sign-in token does not carry one, so the shop types it on the page.
    email: str | None = Field(default=None, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ShopCheckoutOut(BaseModel):
    authorization_url: str
    reference: str


class ShopVerifyIn(BaseModel):
    reference: str


def _plan_read(plan: ShopPlan) -> ShopPlanRead:
    return ShopPlanRead(key=plan.key, name=plan.name, price_ngn=plan.price_ngn, orders_per_month=plan.orders_per_month, blurb=plan.blurb)


def _callback_url() -> str:
    """Paystack sends the shop back to its own Plan & billing page (same site as the company's callback, different page)."""
    settings = get_settings()
    base = settings.paystack_callback_url or (settings.allowed_origins[0] if settings.allowed_origins else "")
    parts = urlsplit(base)
    return f"{parts.scheme}://{parts.netloc}/billing" if parts.scheme and parts.netloc else ""


def _view(session: Session, tenant_id: UUID, merchant_id: UUID) -> ShopBillingRead:
    row = shop_plan_row(session, tenant_id, merchant_id)
    session.commit()  # keeps the trial start the first time the shop looks
    state = shop_state(row)
    payments = session.exec(select(BillingPayment).where(BillingPayment.merchant_id == merchant_id).order_by(BillingPayment.created_at.desc()).limit(12)).all()
    return ShopBillingRead(
        plan=_plan_read(state["plan"]), status=state["status"], valid_until=state["valid_until"], days_left=state["days_left"],
        enforced=shop_billing_enforced(), payments_enabled=bool(get_settings().paystack_secret_key),
        orders_this_month=shop_orders_this_month(session, merchant_id), plans=[_plan_read(SHOP_PLANS[k]) for k in ("trial", *SHOP_PAID_PLANS)],
        payments=[ShopPaymentRead(reference=p.reference, plan=p.plan, amount_ngn=p.amount_kobo // 100, status=p.status, created_at=p.created_at, paid_at=p.paid_at) for p in payments],
    )


@router.get("", response_model=ShopBillingRead)
def get_shop_billing(tenant_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> ShopBillingRead:
    return _view(session, tenant_id, principal.merchant_id)


@router.post("/checkout", response_model=ShopCheckoutOut)
def shop_checkout(tenant_id: UUID, payload: ShopCheckoutIn, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> ShopCheckoutOut:
    paystack = get_paystack()
    if paystack is None:
        raise HTTPException(status_code=503, detail="Online payment is not switched on yet. Contact RouteBridge.")
    shop = session.get(Merchant, principal.merchant_id)
    email = payload.email or (principal.user.email if principal.user else None) or (principal.clerk_user.claims.get("email") if principal.clerk_user else None) or (shop.contact_email if shop else None)
    if not email:
        raise HTTPException(status_code=400, detail="Enter an email address for the payment receipt.")
    plan = get_shop_plan(payload.plan)
    reference = "rbs_" + secrets.token_hex(12)
    payment = BillingPayment(tenant_id=tenant_id, merchant_id=principal.merchant_id, reference=reference, plan=plan.key, amount_kobo=plan.price_ngn * 100, payer_email=email)
    session.add(payment)
    session.commit()
    try:
        data = paystack.initialize(email=email, amount_kobo=payment.amount_kobo, reference=reference, callback_url=_callback_url(), metadata={"tenant_id": str(tenant_id), "merchant_id": str(principal.merchant_id), "plan": plan.key})
    except PaystackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ShopCheckoutOut(authorization_url=data["authorization_url"], reference=reference)


@router.post("/verify", response_model=ShopBillingRead)
def verify_shop_payment(tenant_id: UUID, payload: ShopVerifyIn, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> ShopBillingRead:
    """Called when the shop comes back from the payment page: ask Paystack, never trust the browser."""
    payment = session.exec(select(BillingPayment).where(BillingPayment.reference == payload.reference, BillingPayment.merchant_id == principal.merchant_id).with_for_update()).first()
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    paystack = get_paystack()
    if paystack is None:
        raise HTTPException(status_code=503, detail="Online payment is not switched on.")
    try:
        data = paystack.verify(payment.reference)
    except PaystackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if data.get("status") in ("success", "failed", "reversed"):
        settle(session, payment, int(data.get("amount") or 0), data.get("status") == "success")
        session.commit()
    return _view(session, tenant_id, principal.merchant_id)
