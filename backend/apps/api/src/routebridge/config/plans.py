"""The subscription plans. Edit the numbers here (prices are in naira, per month) once you have learned what customers will pay.

A limit of None means "no limit". `days` is only used by the free trial.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_ngn: int
    riders: int | None
    staff: int | None
    merchants: int | None
    orders_per_month: int | None
    days: int | None = None
    blurb: str = ""


PLANS: dict[str, Plan] = {
    "trial": Plan("trial", "Free trial", 0, riders=3, staff=3, merchants=2, orders_per_month=100, days=14, blurb="Try everything with a small team for 14 days."),
    "starter": Plan("starter", "Starter", 25_000, riders=10, staff=5, merchants=5, orders_per_month=600, blurb="A small delivery team or one busy shop."),
    "growth": Plan("growth", "Growth", 75_000, riders=40, staff=15, merchants=25, orders_per_month=3_000, blurb="A growing courier or several shops."),
    "business": Plan("business", "Business", 200_000, riders=150, staff=50, merchants=100, orders_per_month=15_000, blurb="A large fleet with many clients."),
    "enterprise": Plan("enterprise", "Enterprise", 0, riders=None, staff=None, merchants=None, orders_per_month=None, blurb="Custom terms. Set by RouteBridge."),
}

PAID_PLANS = ("starter", "growth", "business")
PERIOD_DAYS = 30           # one payment buys this many days
GRACE_DAYS = 7             # after a plan ends, new work is blocked only after this many days


def get_plan(key: str | None) -> Plan:
    return PLANS.get((key or "trial").lower(), PLANS["trial"])
