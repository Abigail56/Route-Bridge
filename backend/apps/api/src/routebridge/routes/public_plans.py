"""The shop plans as the public front page shows them. Read from config/plans.py, so the page always matches what shops are charged."""
from fastapi import APIRouter, Response
from pydantic import BaseModel

from routebridge.config.plans import SHOP_PAID_PLANS, SHOP_PLANS, SHOP_TRIAL_DAYS

router = APIRouter(prefix="/public/plans", tags=["public-plans"])


class PublicPlan(BaseModel):
    key: str
    name: str
    price_ngn: int
    orders_per_month: int | None
    blurb: str


class PublicPlans(BaseModel):
    trial_days: int
    plans: list[PublicPlan]  # the free trial first, then the paid plans from smallest to largest


@router.get("/shops", response_model=PublicPlans)
def shop_plans(response: Response) -> PublicPlans:
    response.headers["Cache-Control"] = "public, max-age=300"
    keys = ("trial", *SHOP_PAID_PLANS)
    return PublicPlans(trial_days=SHOP_TRIAL_DAYS, plans=[PublicPlan(key=p.key, name=p.name, price_ngn=p.price_ngn, orders_per_month=p.orders_per_month, blurb=p.blurb) for p in (SHOP_PLANS[k] for k in keys)])
