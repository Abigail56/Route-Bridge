"""Plans, usage and limits.

Limits are only enforced when ROUTEBRIDGE_BILLING_ENFORCED=true, so nothing changes until you decide to start charging. Even then, a plan that
has ended never stops deliveries that are already under way: it only blocks creating NEW riders, people, merchants and orders, and only after a
grace period.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, func, select

from routebridge.config.plans import GRACE_DAYS, PERIOD_DAYS, SHOP_TRIAL_DAYS, Plan, ShopPlan, get_plan, get_shop_plan
from routebridge.config.settings import get_settings
from routebridge.models.access import TenantMembership
from routebridge.models.billing import MerchantPlan
from routebridge.models.core import Tenant, utc_now
from routebridge.models.operations import Driver
from routebridge.models.orders import Merchant, Order

LABELS = {"riders": "riders", "staff": "team members", "merchants": "merchants", "orders": "orders this month"}
NOT_STAFF = ("merchant_user", "driver")


def aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def usage(session: Session, tenant_id: UUID) -> dict[str, int]:
    month_start = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = lambda statement: session.exec(statement).one()  # noqa: E731
    return {
        "riders": count(select(func.count()).select_from(Driver).where(Driver.tenant_id == tenant_id)),
        "staff": count(select(func.count()).select_from(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.status == "active", TenantMembership.role.notin_(NOT_STAFF))),
        "merchants": count(select(func.count()).select_from(Merchant).where(Merchant.tenant_id == tenant_id, Merchant.status == "active")),
        "orders": count(select(func.count()).select_from(Order).where(Order.tenant_id == tenant_id, Order.created_at >= month_start)),
    }


def limit_of(plan: Plan, what: str) -> int | None:
    return {"riders": plan.riders, "staff": plan.staff, "merchants": plan.merchants, "orders": plan.orders_per_month}[what]


def plan_state(tenant: Tenant) -> dict:
    plan = get_plan(tenant.plan)
    valid_until = aware(tenant.plan_valid_until)
    now = utc_now()
    if plan.key == "enterprise" or valid_until is None:
        return {"plan": plan, "valid_until": valid_until, "status": "active", "days_left": None, "blocked": False}
    days_left = (valid_until - now).total_seconds() / 86400
    if days_left > 5:
        status = "active"
    elif days_left >= 0:
        status = "ending"
    elif now <= valid_until + timedelta(days=GRACE_DAYS):
        status = "grace"
    else:
        status = "expired"
    return {"plan": plan, "valid_until": valid_until, "status": status, "days_left": int(days_left) if days_left >= 0 else 0, "blocked": status == "expired"}


def enforce(session: Session, tenant_id: UUID, what: str, adding: int = 1) -> None:
    """Refuse to create more of `what` when the plan is used up or has ended (only if billing is switched on)."""
    if not get_settings().billing_enforced:
        return
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        return
    state = plan_state(tenant)
    if state["blocked"]:
        ended = state["valid_until"].strftime("%d %b %Y")
        raise HTTPException(status_code=402, detail=f"Your {state['plan'].name} plan ended on {ended}. Renew it in Settings, then Plan & billing, to add {LABELS[what]}. Deliveries already under way are not affected.")
    limit = limit_of(state["plan"], what)
    if limit is not None and usage(session, tenant_id)[what] + adding > limit:
        raise HTTPException(status_code=402, detail=f"Your {state['plan'].name} plan allows up to {limit} {LABELS[what]}. Upgrade in Settings, then Plan & billing, to add more.")


def activate_plan(tenant: Tenant, plan_key: str, days: int = PERIOD_DAYS) -> None:
    """Start or extend a plan. A renewal paid early adds to the time left instead of wasting it."""
    now = utc_now()
    current = aware(tenant.plan_valid_until)
    start = current if current and current > now and tenant.plan == plan_key else now
    tenant.plan = plan_key
    tenant.plan_valid_until = start + timedelta(days=days)


# ---- a SHOP's own plan: paid online by the shop, and enforced -------------------------------------------------------------------------------

def shop_billing_enforced() -> bool:
    """Shops must pay online once their trial or plan ends. This can only be on while online payment (a Paystack key) is set, otherwise
    nobody could pay and every shop would be locked out."""
    settings = get_settings()
    return bool(settings.shop_billing_enforced and settings.paystack_secret_key)


def shop_plan_row(session: Session, tenant_id: UUID, merchant_id: UUID) -> MerchantPlan:
    """The shop's plan row. A shop that has none yet starts a free trial now."""
    row = session.get(MerchantPlan, merchant_id)
    if row is None:
        row = MerchantPlan(merchant_id=merchant_id, tenant_id=tenant_id, plan="trial", valid_until=utc_now() + timedelta(days=SHOP_TRIAL_DAYS))
        session.add(row)
        session.flush()
    return row


def shop_orders_this_month(session: Session, merchant_id: UUID) -> int:
    month_start = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return session.exec(select(func.count()).select_from(Order).where(Order.merchant_id == merchant_id, Order.created_at >= month_start)).one()


def shop_state(row: MerchantPlan) -> dict:
    """Same wording as the company plan, but with no grace days: when a shop's time is up, new orders stop until it pays."""
    plan: ShopPlan = get_shop_plan(row.plan)
    valid_until = aware(row.valid_until)
    now = utc_now()
    if valid_until is None:
        return {"plan": plan, "valid_until": None, "status": "active", "days_left": None, "blocked": False}
    days_left = (valid_until - now).total_seconds() / 86400
    status = "expired" if days_left < 0 else ("ending" if days_left <= 5 else "active")
    return {"plan": plan, "valid_until": valid_until, "status": status, "days_left": int(days_left) if days_left >= 0 else 0, "blocked": status == "expired"}


def enforce_shop(session: Session, tenant_id: UUID, merchant_id: UUID) -> None:
    """Refuse a NEW order from a shop whose plan has ended or whose month's orders are used up. Deliveries already under way are untouched."""
    if not shop_billing_enforced():
        return
    state = shop_state(shop_plan_row(session, tenant_id, merchant_id))
    if state["blocked"]:
        ended = state["valid_until"].strftime("%d %b %Y")
        raise HTTPException(status_code=402, detail=f"Your {state['plan'].name} plan ended on {ended}. Pay online on the Plan & billing page to place new orders. Deliveries already under way are not affected.")
    limit = state["plan"].orders_per_month
    if limit is not None and shop_orders_this_month(session, merchant_id) + 1 > limit:
        raise HTTPException(status_code=402, detail=f"Your {state['plan'].name} plan allows {limit} orders a month and you have used them. Upgrade on the Plan & billing page to place more.")


def activate_shop_plan(row: MerchantPlan, plan_key: str, days: int = PERIOD_DAYS) -> None:
    """Start or extend a shop's plan. A renewal paid early adds to the time left."""
    now = utc_now()
    current = aware(row.valid_until)
    start = current if current and current > now and row.plan == plan_key else now
    row.plan = plan_key
    row.valid_until = start + timedelta(days=days)
