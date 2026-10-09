"""Plans, usage and limits.

Limits are only enforced when ROUTEBRIDGE_BILLING_ENFORCED=true, so nothing changes until you decide to start charging. Even then, a plan that
has ended never stops deliveries that are already under way: it only blocks creating NEW riders, people, merchants and orders, and only after a
grace period.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, func, select

from routebridge.config.plans import GRACE_DAYS, PERIOD_DAYS, Plan, get_plan
from routebridge.config.settings import get_settings
from routebridge.models.access import TenantMembership
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
