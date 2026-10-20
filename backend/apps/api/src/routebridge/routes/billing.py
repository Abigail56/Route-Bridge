"""Plan & billing: what the workspace is on, what it has used, and paying for a plan with Paystack (naira)."""
import json
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import Session, select

from routebridge.auth.authorization import TenantPrincipal, tenant_roles
from routebridge.config.plans import PERIOD_DAYS
from routebridge.config.settings import get_settings
from routebridge.db.session import engine, get_session
from routebridge.integrations.paystack import webhook_signature_ok
from routebridge.models.billing import BillingPayment
from routebridge.models.core import Tenant, utc_now
from routebridge.routes.admin import require_platform_admin
from routebridge.services.billing import activate_plan, activate_shop_plan, shop_plan_row
from routebridge.services.events import record_event

OWNER_ROLES = ("tenant_owner", "tenant_admin", "finance")
router = APIRouter(tags=["billing"])


class PlanSet(BaseModel):
    plan: Literal["trial", "starter", "growth", "business", "enterprise"]
    days: int | None = Field(default=None, ge=1, le=3650)


def _tenant(session: Session, tenant_id: UUID) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return tenant


def settle(session: Session, payment: BillingPayment, paid_kobo: int, paid: bool) -> bool:
    """Mark a payment successful exactly once and switch the plan on. Safe to call again for the same reference."""
    if payment.status == "success":
        return False
    if not paid:
        payment.status = "failed"
        session.add(payment)
        return False
    if paid_kobo != payment.amount_kobo:
        # never give a plan for a different amount than the plan costs
        payment.status = "failed"
        session.add(payment)
        record_event(session, payment.tenant_id, "billing.amount_mismatch", "billing", payment.id, {"expected": payment.amount_kobo, "paid": paid_kobo})
        return False
    # claim the payment with one conditional UPDATE: of any deliveries racing for it (webhook retries, the shop's own verify), exactly one wins
    claimed = session.exec(update(BillingPayment).where(BillingPayment.id == payment.id, BillingPayment.status != "success").values(status="success", paid_at=utc_now())).rowcount
    if not claimed:
        return False
    session.refresh(payment)
    if payment.merchant_id is not None:  # a shop paid for its own plan
        row = shop_plan_row(session, payment.tenant_id, payment.merchant_id)
        activate_shop_plan(row, payment.plan, PERIOD_DAYS)
        session.add_all([payment, row])
        record_event(session, payment.tenant_id, "billing.shop_paid", "merchant", payment.merchant_id, {"plan": payment.plan, "amount_kobo": payment.amount_kobo, "reference": payment.reference})
        return True
    tenant = _tenant(session, payment.tenant_id)
    activate_plan(tenant, payment.plan, PERIOD_DAYS)
    session.add_all([payment, tenant])
    record_event(session, tenant.id, "billing.paid", "billing", payment.id, {"plan": payment.plan, "amount_kobo": payment.amount_kobo, "reference": payment.reference})
    return True


class ShopPlanRow(BaseModel):
    merchant_id: UUID
    name: str
    plan: str
    plan_name: str
    status: str
    valid_until: datetime | None
    orders_this_month: int
    last_paid_at: datetime | None


@router.get("/tenants/{tenant_id}/billing/shops", response_model=list[ShopPlanRow])
def shops_billing(tenant_id: UUID, _: TenantPrincipal = Depends(tenant_roles(*OWNER_ROLES)), session: Session = Depends(get_session)) -> list[ShopPlanRow]:
    """Every shop's own plan and its last online payment, for the Admin. Read-only: a shop with no plan row yet shows as a trial that starts on first use."""
    from routebridge.models.billing import MerchantPlan
    from routebridge.models.orders import Merchant
    from routebridge.services.billing import shop_orders_this_month, shop_state

    rows = []
    for shop in session.exec(select(Merchant).where(Merchant.tenant_id == tenant_id, Merchant.status == "active").order_by(Merchant.name)).all():
        plan = session.get(MerchantPlan, shop.id) or MerchantPlan(merchant_id=shop.id, tenant_id=tenant_id, plan="trial", valid_until=None)
        state = shop_state(plan)
        paid = session.exec(select(BillingPayment.paid_at).where(BillingPayment.merchant_id == shop.id, BillingPayment.status == "success").order_by(BillingPayment.paid_at.desc())).first()
        rows.append(ShopPlanRow(merchant_id=shop.id, name=shop.name, plan=plan.plan, plan_name=state["plan"].name, status=state["status"], valid_until=state["valid_until"], orders_this_month=shop_orders_this_month(session, shop.id), last_paid_at=paid))
    return rows


def _settle_charge(reference: str, amount: int, paid: bool) -> None:
    """Runs on a worker thread. The payment row is locked (Postgres) so two deliveries of the same charge settle one after the other."""
    with Session(engine) as session:
        payment = session.exec(select(BillingPayment).where(BillingPayment.reference == reference).with_for_update()).first()
        if payment is not None:
            settle(session, payment, amount, paid)
            session.commit()


@router.post("/webhooks/paystack", include_in_schema=False)
async def paystack_webhook(request: Request, x_paystack_signature: str | None = Header(default=None)) -> dict:
    body = await request.body()
    if not webhook_signature_ok(get_settings().paystack_secret_key, body, x_paystack_signature):
        raise HTTPException(status_code=401, detail="Bad signature")
    event = json.loads(body or b"{}")
    data = event.get("data") or {}
    if event.get("event") == "charge.success":
        await run_in_threadpool(_settle_charge, str(data.get("reference")), int(data.get("amount") or 0), data.get("status") == "success")
    return {"ok": True}


@router.put("/platform/tenants/{tenant_id}/plan", dependencies=[Depends(require_platform_admin)], include_in_schema=False)
def set_plan(tenant_id: UUID, payload: PlanSet, session: Session = Depends(get_session)) -> dict:
    """RouteBridge staff can put a company on any plan (a gift, an enterprise deal, a fix). Recorded in the audit trail."""
    tenant = _tenant(session, tenant_id)
    old = tenant.plan
    tenant.plan = payload.plan
    tenant.plan_valid_until = None if payload.plan == "enterprise" else utc_now() + timedelta(days=payload.days or PERIOD_DAYS)
    session.add(tenant)
    record_event(session, tenant_id, "billing.plan_set_by_platform", "tenant", tenant_id, {"from": old, "to": payload.plan, "days": payload.days})
    session.commit()
    return {"plan": tenant.plan, "valid_until": tenant.plan_valid_until}
